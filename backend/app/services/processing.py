from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from typing import Iterable

import pytesseract
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.enums import ChecklistItemStatus, DocumentStatus, DocumentType, ExtractionStatus
from app.db.models import ApplicationChecklistItem, Document, DocumentVersion, ExtractedField, Extraction
from app.services.object_store import get_object_store

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "ocr-phase4-1.0"


@dataclass
class TextEvidence:
    text: str
    page: int
    bbox: list[float] | None
    confidence: float
    page_width: float | None = None
    page_height: float | None = None


class OcrEngineUnavailable(RuntimeError):
    """The Tesseract binary is not installed or not on PATH.

    This is a deployment problem, not a defect in the uploaded document, so it
    must not be reported as an unreadable document.
    """

    def __init__(self, page_count: int = 0):
        super().__init__("Tesseract OCR engine is not available on this host.")
        self.page_count = page_count


def _ocr_image(image: Image.Image, page: int) -> list[TextEvidence]:
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrEngineUnavailable() from exc
    grouped: dict[tuple[int, int, int], list[dict]] = {}
    for index, word in enumerate(data.get("text", [])):
        if not word or not str(word).strip():
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence < 0:
            continue
        key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
        grouped.setdefault(key, []).append(
            {
                "text": str(word),
                "conf": confidence,
                "left": data["left"][index],
                "top": data["top"][index],
                "width": data["width"][index],
                "height": data["height"][index],
            }
        )
    results: list[TextEvidence] = []
    width, height = float(image.width), float(image.height)
    for words in grouped.values():
        words.sort(key=lambda item: item["left"])
        text = " ".join(item["text"] for item in words).strip()
        if not text:
            continue
        left = min(item["left"] for item in words)
        top = min(item["top"] for item in words)
        right = max(item["left"] + item["width"] for item in words)
        bottom = max(item["top"] + item["height"] for item in words)
        confidence = sum(item["conf"] for item in words) / len(words) / 100.0
        results.append(
            TextEvidence(
                text=text,
                page=page,
                bbox=[left, top, right, bottom],
                confidence=confidence,
                page_width=width,
                page_height=height,
            )
        )
    return results


def _extract_pdf(content: bytes) -> tuple[list[TextEvidence], int, float]:
    import pymupdf

    document = pymupdf.open(stream=content, filetype="pdf")
    evidence: list[TextEvidence] = []
    page_count = 0
    try:
        page_count = document.page_count
        for page_index, page in enumerate(document, start=1):
            page_lines: list[TextEvidence] = []
            page_width, page_height = float(page.rect.width), float(page.rect.height)
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                    if text:
                        page_lines.append(
                            TextEvidence(
                                text=text,
                                page=page_index,
                                bbox=list(line.get("bbox", [])) or None,
                                confidence=0.9,
                                page_width=page_width,
                                page_height=page_height,
                            )
                        )
            page_text = " ".join(item.text for item in page_lines).strip()
            if len(page_text) < 20:
                pixmap = page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB)
                image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                try:
                    page_lines = _ocr_image(image, page_index)
                except OcrEngineUnavailable as exc:
                    raise OcrEngineUnavailable(page_count) from exc
            evidence.extend(page_lines)
    finally:
        document.close()
    confidence = (
        sum(item.confidence for item in evidence) / len(evidence) if evidence else 0.0
    )
    return evidence, page_count, confidence


def _extract_image(content: bytes) -> tuple[list[TextEvidence], int, float]:
    image = Image.open(BytesIO(content))
    try:
        try:
            evidence = _ocr_image(image, 1)
        except OcrEngineUnavailable as exc:
            raise OcrEngineUnavailable(1) from exc
    finally:
        image.close()
    confidence = sum(item.confidence for item in evidence) / len(evidence) if evidence else 0.0
    return evidence, 1, confidence


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_DATE_PATTERN = re.compile(
    rf"\b(\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}}|"
    rf"\d{{1,2}}\s+(?:{_MONTHS})[a-z]*\s+\d{{4}}|(?:{_MONTHS})[a-z]*\s+\d{{1,2}},?\s+\d{{4}})\b",
    re.IGNORECASE,
)


def _parse_date(value: str) -> date | None:
    cleaned = value.replace(".", "/").replace("-", "/").strip()
    for fmt in (
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y/%m/%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    ):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    try:
        from dateutil import parser as date_parser

        parsed = date_parser.parse(value, dayfirst=True, fuzzy=False).date()
        if 1900 <= parsed.year <= 2100:
            return parsed
    except (ValueError, OverflowError):
        return None
    return None


def _line_for_pattern(evidence: Iterable[TextEvidence], pattern: re.Pattern) -> tuple[str, TextEvidence] | None:
    for item in evidence:
        match = pattern.search(item.text)
        if match:
            return match.group(1).strip(" :-\t"), item
    return None


def _extract_fields(evidence: list[TextEvidence], document_type: DocumentType) -> list[dict]:
    patterns = [
        ("institution_name", re.compile(r"(?:name of (?:the )?institution|institution name|college name)\s*[:\-]\s*(.+)", re.I), "TEXT"),
        ("affiliation_number", re.compile(r"(?:affiliation|recognition)\s*(?:no\.?|number)?\s*[:\-]\s*([A-Z0-9][A-Z0-9./-]{3,})", re.I), "IDENTIFIER"),
        ("reference_number", re.compile(r"(?:reference|ref|application|file|registration)\s*(?:no\.?|number)?\s*[:\-]\s*([A-Z0-9][A-Z0-9./-]{3,})", re.I), "IDENTIFIER"),
        ("issuing_authority", re.compile(r"(?:issued by|issuing authority|authority)\s*[:\-]\s*(.+)", re.I), "TEXT"),
        ("programme", re.compile(r"(?:programme|program|course)\s*[:\-]\s*(.+)", re.I), "TEXT"),
        ("holder_name", re.compile(r"(?:name|certify that|awarded to)\s*[:\-]?\s*([A-Z][A-Za-z .'\-]{2,80})", re.I), "TEXT"),
        ("degree", re.compile(r"\b(Bachelor of Technology|B\.?\s*Tech|Bachelor of Engineering|B\.?\s*E|Master of Technology|M\.?\s*Tech|B\.?\s*Sc|M\.?\s*Sc|MBA|Ph\.?\s*D)\b", re.I), "TEXT"),
        ("faculty_qualification", re.compile(r"(?:qualification)\s*[:\-]\s*(.+)", re.I), "TEXT"),
        ("land_area", re.compile(r"(?:land area|area)\s*[:\-]\s*([\d.,]+\s*(?:sq\.?\s*(?:m|ft)|acres?|hectares?))", re.I), "TEXT"),
    ]
    records: list[dict] = []
    for name, pattern, value_type in patterns:
        found = _line_for_pattern(evidence, pattern)
        if not found:
            continue
        value, source = found
        value = _normalize_text(value)
        if not value or len(value) > 300:
            continue
        records.append(
            {
                "name": name,
                "raw_value": value,
                "normalized_value": value.lower(),
                "value_type": value_type,
                "page": source.page,
                "bbox": source.bbox,
                "page_width": source.page_width,
                "page_height": source.page_height,
                "confidence": min(0.99, max(0.05, source.confidence + 0.03)),
                "extractor": EXTRACTOR_VERSION,
            }
        )

    # Date fields are label-aware so issue and validity dates are not conflated.
    date_labels = [
        ("valid_until", re.compile(r"(?:valid\s*(?:up\s*to|till|until|to)|validity\s*(?:up\s*to|till|until))\s*[:\-]?\s*(.*)", re.I)),
        ("valid_from", re.compile(r"(?:valid\s*from|effective\s*from)\s*[:\-]?\s*(.*)", re.I)),
        ("issued_date", re.compile(r"(?:date of issue|issued on|issue date)\s*[:\-]?\s*(.*)", re.I)),
    ]
    for name, label_pattern in date_labels:
        for item in evidence:
            label = label_pattern.search(item.text)
            if not label:
                continue
            candidate = label.group(1).strip()
            match = _DATE_PATTERN.search(candidate) or _DATE_PATTERN.search(item.text)
            if not match:
                continue
            parsed = _parse_date(match.group(1))
            if not parsed:
                continue
            records.append(
                {
                    "name": name,
                    "raw_value": match.group(1),
                    "normalized_value": parsed.isoformat(),
                    "value_type": "DATE",
                    "page": item.page,
                    "bbox": item.bbox,
                    "page_width": item.page_width,
                    "page_height": item.page_height,
                    "confidence": min(0.99, max(0.05, item.confidence + 0.02)),
                    "extractor": EXTRACTOR_VERSION,
                }
            )
            break

    cgpa_match = re.search(r"(?:cgpa|gpa|grade point average)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)", " ".join(item.text for item in evidence), re.I)
    if cgpa_match:
        records.append(
            {
                "name": "cgpa",
                "raw_value": cgpa_match.group(1),
                "normalized_value": cgpa_match.group(1),
                "value_type": "NUMBER",
                "page": evidence[0].page if evidence else None,
                "bbox": evidence[0].bbox if evidence else None,
                "page_width": evidence[0].page_width if evidence else None,
                "page_height": evidence[0].page_height if evidence else None,
                "confidence": 0.8,
                "extractor": EXTRACTOR_VERSION,
            }
        )
    return records


_CLASSIFICATION_KEYWORDS = {
    DocumentType.AFFILIATION_CERTIFICATE: ("affiliation", "recognition", "university", "affiliated"),
    DocumentType.LAND_LEASE_DOCUMENT: ("land", "lease", "deed", "property", "area"),
    DocumentType.FACULTY_DEGREE_CERTIFICATE: ("degree", "qualification", "university", "faculty", "holder"),
    DocumentType.INSTITUTIONAL_UNDERTAKING: ("undertaking", "declaration", "affidavit", "hereby"),
    DocumentType.OTHER: (),
}


def _classification_confidence(text: str, expected: DocumentType) -> Decimal:
    lowered = text.lower()
    keywords = _CLASSIFICATION_KEYWORDS.get(expected, ())
    if not keywords:
        return Decimal("0.600")
    hits = sum(1 for keyword in keywords if keyword in lowered)
    if hits >= 2:
        return Decimal("0.900")
    if hits == 1:
        return Decimal("0.750")
    return Decimal("0.500")


def _build_extraction(content: bytes, mime_type: str, document_type: DocumentType):
    ocr_unavailable = False
    try:
        if mime_type == "application/pdf":
            evidence, page_count, ocr_confidence = _extract_pdf(content)
        else:
            evidence, page_count, ocr_confidence = _extract_image(content)
    except OcrEngineUnavailable as exc:
        evidence, page_count, ocr_confidence = [], exc.page_count, 0.0
        ocr_unavailable = True
    raw_text = "\n".join(item.text for item in evidence).strip()
    fields = _extract_fields(evidence, document_type) if raw_text else []
    confidence = Decimal(str(round(ocr_confidence, 3))) if evidence else Decimal("0.000")
    if ocr_unavailable:
        status = ExtractionStatus.FAILED
        error_code = "OCR_ENGINE_UNAVAILABLE"
        error_detail = (
            "The OCR engine (Tesseract) is not installed on this server, so scanned or "
            "image-only pages could not be read. This is a deployment issue, not a defect "
            "in the uploaded document. Manual review is required."
        )
    elif not raw_text:
        status = ExtractionStatus.UNREADABLE
        error_code = "NO_TEXT"
        error_detail = "No machine-readable text could be extracted. Manual review is required."
    elif len(fields) < 2 or ocr_confidence < 0.45:
        status = ExtractionStatus.LOW_CONFIDENCE
        error_code = None
        error_detail = None
    else:
        status = ExtractionStatus.COMPLETED
        error_code = None
        error_detail = None
    return {
        "raw_text": raw_text[:200000],
        "fields": fields,
        "page_count": page_count,
        "confidence": confidence,
        "classification_confidence": _classification_confidence(raw_text, document_type),
        "status": status,
        "error_code": error_code,
        "error_detail": error_detail,
    }


def _sync_checklist_after_processing(db: Session, document: Document, *, satisfied: bool) -> None:
    items = db.scalars(
        select(ApplicationChecklistItem).where(ApplicationChecklistItem.document_id == document.id)
    )
    for item in items:
        if satisfied and item.status is ChecklistItemStatus.PENDING:
            item.status = ChecklistItemStatus.SATISFIED
        elif not satisfied and item.status is ChecklistItemStatus.SATISFIED:
            item.status = ChecklistItemStatus.PENDING


def process_document_version(db: Session, version: DocumentVersion, *, force: bool = False) -> Extraction:
    document = db.get(Document, version.document_id)
    if not document:
        raise ValueError("document not found")
    existing = db.scalar(select(Extraction).where(Extraction.document_version_id == version.id))
    if existing and not force:
        return existing
    if existing and force:
        db.delete(existing)
        db.flush()

    document.status = DocumentStatus.PROCESSING
    db.commit()

    extraction = Extraction(
        document_version_id=version.id,
        document_type=document.document_type,
        status=ExtractionStatus.PENDING,
        extractor_version=EXTRACTOR_VERSION,
        page_count=version.page_count,
    )
    db.add(extraction)
    db.flush()
    try:
        content = get_object_store().get(version.storage_key)
        result = _build_extraction(content, version.mime_type, document.document_type)
        extraction.document_type = document.document_type
        extraction.classification_confidence = result["classification_confidence"]
        extraction.status = result["status"]
        extraction.confidence = result["confidence"]
        extraction.page_count = result["page_count"]
        extraction.error_code = result["error_code"]
        extraction.error_detail = result["error_detail"]
        extraction.raw_text = result["raw_text"]
        extraction.completed_at = datetime.now(timezone.utc)
        for field in result["fields"]:
            db.add(
                ExtractedField(
                    extraction_id=extraction.id,
                    name=field["name"],
                    raw_value=field["raw_value"],
                    normalized_value=field["normalized_value"],
                    value_type=field["value_type"],
                    page=field["page"],
                    bbox=field["bbox"],
                    page_width=field["page_width"],
                    page_height=field["page_height"],
                    confidence=Decimal(str(round(field["confidence"], 3))),
                    extractor=field["extractor"],
                )
            )
        if result["status"] in {ExtractionStatus.COMPLETED, ExtractionStatus.LOW_CONFIDENCE}:
            document.status = DocumentStatus.PROCESSED
            _sync_checklist_after_processing(db, document, satisfied=True)
        else:
            document.status = DocumentStatus.FAILED
            _sync_checklist_after_processing(db, document, satisfied=False)
        db.commit()
    except Exception:
        logger.exception("document extraction failed version_id=%s", version.id)
        db.rollback()
        failed_document = db.get(Document, version.document_id)
        extractor_failure = db.scalar(
            select(Extraction).where(Extraction.document_version_id == version.id)
        )
        if extractor_failure is None:
            extractor_failure = Extraction(
                document_version_id=version.id,
                document_type=failed_document.document_type if failed_document else None,
                status=ExtractionStatus.FAILED,
                extractor_version=EXTRACTOR_VERSION,
                page_count=version.page_count,
                error_code="PROCESSING_FAILED",
                error_detail="The document could not be processed. Manual review is required.",
                completed_at=datetime.now(timezone.utc),
            )
            db.add(extractor_failure)
        else:
            extractor_failure.status = ExtractionStatus.FAILED
            extractor_failure.error_code = "PROCESSING_FAILED"
            extractor_failure.error_detail = "The document could not be processed. Manual review is required."
            extractor_failure.completed_at = datetime.now(timezone.utc)
        document = db.get(Document, version.document_id)
        if document:
            document.status = DocumentStatus.FAILED
            _sync_checklist_after_processing(db, document, satisfied=False)
        db.commit()
        extraction = extractor_failure
    db.refresh(extraction)
    return extraction


def process_document_version_by_id(version_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        version = db.get(DocumentVersion, version_id)
        if version:
            process_document_version(db, version)
    finally:
        db.close()
