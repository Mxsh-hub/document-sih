from __future__ import annotations

"""Advisory technical inspection of uploaded documents.

This module answers two narrow questions about a document:

* Does it contain a QR payload, and what does that payload say?
* Does it contain an embedded PDF signature structure, and do the declared
  byte ranges cover the document?

It deliberately does **not** resolve QR payloads against an authorised issuer
source and does **not** verify PDF signature cryptography, the signer
certificate, revocation state, or a trust chain. Every result is advisory and
is stored as an :class:`~app.db.models.IssuerVerification` row so that the
review console can show what was inspected, when, and with which engine version.

Nothing here proves authenticity. A QR payload can be printed by anyone and a
PDF signature structure can be placed by anyone; only source resolution and
signature verification (not implemented, no authorised source configured) would
support an authenticity claim.
"""

import hashlib
import logging
import re
import uuid
from io import BytesIO
from typing import Any, Iterable
from urllib.parse import urlsplit

from PIL import Image
from sqlalchemy.orm import Session

from app.db.enums import IssuerVerificationStatus
from app.db.models import DocumentVersion, IssuerVerification, User
from app.services.issuers import record_verification
from app.services.object_store import get_object_store

logger = logging.getLogger(__name__)

INSPECTION_VERSION = "technical-inspection-1.0"
QR_ADAPTER_CODE = "qr-payload"
PDF_SIGNATURE_ADAPTER_CODE = "pdf-signature"

MAX_QR_PAGES = 10
QR_RENDER_DPI = 150
MAX_RECORDED_PAYLOADS = 10
PAYLOAD_PREVIEW_CHARS = 256
# A detached PDF signature normally excludes only the /Contents hex string.
# Anything larger than this is treated as an unsupported/incomplete layout
# rather than silently assumed to be the signature placeholder.
MAX_SIGNATURE_GAP_BYTES = 65536

_QR_DETECTOR: Any = None
_QR_DETECTOR_LOADED = False

_SIGNATURE_TYPE_RE = re.compile(rb"/Type\s*/Sig\b")
_BYTE_RANGE_RE = re.compile(rb"/ByteRange\s*\[\s*([0-9\s]+?)\s*\]", re.DOTALL)
_SIGNATURE_NAME_RE = re.compile(rb"/Name\s*\(([^()]{1,200})\)")
_SIGNATURE_TIME_RE = re.compile(rb"/M\s*\(([^()]{1,100})\)")
_SIGNATURE_FILTER_RE = re.compile(rb"/(?:Filter|SubFilter)\s*/([A-Za-z0-9._+-]{1,60})")
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class QrDecoderUnavailable(RuntimeError):
    """No QR decoding backend is installed on this host."""


def _is_pdf(version: DocumentVersion) -> bool:
    return version.mime_type == "application/pdf"


def _is_image(version: DocumentVersion) -> bool:
    return version.mime_type.startswith("image/")


def _get_qr_detector() -> Any:
    global _QR_DETECTOR, _QR_DETECTOR_LOADED
    if _QR_DETECTOR_LOADED:
        return _QR_DETECTOR
    _QR_DETECTOR_LOADED = True
    try:
        import cv2

        _QR_DETECTOR = cv2.QRCodeDetector()
    except Exception:  # pragma: no cover - depends on deployment image
        logger.warning("OpenCV QR decoder is unavailable; QR inspection is limited.")
        _QR_DETECTOR = None
    return _QR_DETECTOR


def _page_images(content: bytes, version: DocumentVersion) -> list[tuple[int, Image.Image]]:
    """Render PDF pages (bounded) or open the uploaded image for QR scanning."""
    if not _is_pdf(version):
        image = Image.open(BytesIO(content))
        try:
            return [(1, image.convert("RGB"))]
        finally:
            image.close()

    import pymupdf

    document = pymupdf.open(stream=content, filetype="pdf")
    images: list[tuple[int, Image.Image]] = []
    try:
        for index, page in enumerate(document, start=1):
            if index > MAX_QR_PAGES:
                break
            pixmap = page.get_pixmap(dpi=QR_RENDER_DPI, colorspace=pymupdf.csRGB)
            images.append(
                (
                    index,
                    Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples),
                )
            )
    finally:
        document.close()
    return images


def _decode_qr(image: Image.Image) -> list[str]:
    """Return every non-empty QR payload decoded from one page image."""
    detector = _get_qr_detector()
    if detector is None:
        raise QrDecoderUnavailable("No QR decoder is available on this host.")
    import numpy as np

    # OpenCV expects BGR; QR detection itself is effectively grayscale.
    pixels = np.asarray(image.convert("RGB"))[:, :, ::-1]
    payloads: list[str] = []
    if hasattr(detector, "detectAndDecodeMulti"):
        try:
            found, decoded, _points, _straight = detector.detectAndDecodeMulti(pixels)
        except Exception:
            found, decoded = False, ()
        if found:
            payloads.extend(str(item) for item in decoded if item)
    if not payloads:
        try:
            data, _points, _straight = detector.detectAndDecode(pixels)
        except Exception:
            data = ""
        if data:
            payloads.append(str(data))
    return payloads


def _describe_payload(raw: str) -> dict[str, Any]:
    payload = raw.strip()
    preview = payload[:PAYLOAD_PREVIEW_CHARS]
    description: dict[str, Any] = {
        "payload_preview": preview,
        "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "payload_length": len(payload),
        "not_fetched": True,
    }
    if _URL_SCHEME_RE.match(payload):
        try:
            parsed = urlsplit(payload)
            scheme = parsed.scheme.lower()
            description.update(
                {
                    "is_url": True,
                    "scheme": scheme,
                    "host": parsed.hostname,
                    # Only https is even potentially an authorised resolver;
                    # the payload is never fetched either way.
                    "scheme_is_http_like": scheme in {"http", "https"},
                }
            )
        except ValueError:
            description.update({"is_url": True, "scheme": None, "host": None})
    else:
        description.update({"is_url": False, "scheme": None, "host": None})
    return description


def _inspect_qr(
    content: bytes, version: DocumentVersion, *, pages: list[tuple[int, Image.Image]] | None = None
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "engine_version": INSPECTION_VERSION,
        "advisory_only": True,
        "cryptographically_verified": False,
        "external_lookup_performed": False,
        "document_sha256": version.sha256,
    }
    try:
        images = pages if pages is not None else _page_images(content, version)
    except Exception:
        logger.exception("QR inspection could not open document version_id=%s", version.id)
        return {
            **evidence,
            "state": "QR_DECODE_FAILED",
            "message": "The document could not be opened for QR inspection. This is not a finding about its authenticity.",
            "status": IssuerVerificationStatus.ERROR,
            "pages_scanned": 0,
            "payloads": [],
        }

    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    scanned = 0
    try:
        for page_number, image in images:
            scanned = page_number
            for raw in _decode_qr(image):
                if raw in seen:
                    continue
                seen.add(raw)
                description = _describe_payload(raw)
                description["page"] = page_number
                payloads.append(description)
                if len(payloads) >= MAX_RECORDED_PAYLOADS:
                    break
            if len(payloads) >= MAX_RECORDED_PAYLOADS:
                break
    except QrDecoderUnavailable:
        return {
            **evidence,
            "state": "QR_DECODER_UNAVAILABLE",
            "message": (
                "A QR decoder is not installed on this server, so QR payloads could not be read. "
                "This is a deployment limitation, not a document finding."
            ),
            "status": IssuerVerificationStatus.SOURCE_UNAVAILABLE,
            "pages_scanned": scanned,
            "payloads": payloads,
        }
    except Exception:
        logger.exception("QR inspection failed version_id=%s", version.id)
        return {
            **evidence,
            "state": "QR_DECODE_FAILED",
            "message": "QR payload decoding failed. This is an inspection error, not a finding about authenticity.",
            "status": IssuerVerificationStatus.ERROR,
            "pages_scanned": scanned,
            "payloads": payloads,
        }

    if payloads:
        return {
            **evidence,
            "state": "QR_PAYLOAD_DETECTED_UNVERIFIED",
            "message": (
                "A QR payload was detected but was not resolved against any authorised source. "
                "The payload is recorded for human review only; no URL was fetched and no authenticity claim is made."
            ),
            "status": IssuerVerificationStatus.SOURCE_UNAVAILABLE,
            "pages_scanned": scanned,
            "payload_count": len(payloads),
            "payloads": payloads,
        }
    return {
        **evidence,
        "state": "NO_QR_DETECTED",
        "message": (
            "No QR code was detected in the inspected pages. Absence of a QR code is not evidence that a document is unauthorised."
        ),
        "status": IssuerVerificationStatus.NOT_FOUND,
        "pages_scanned": scanned,
        "payload_count": 0,
        "payloads": [],
    }


def _parse_byte_ranges(raw: bytes) -> tuple[list[list[int]] | None, bool]:
    match = _BYTE_RANGE_RE.search(raw)
    if not match:
        return None, False
    try:
        numbers = [int(item) for item in match.group(1).split()]
    except ValueError:
        return None, True
    if len(numbers) < 4 or len(numbers) % 2 != 0:
        return None, True
    pairs = [[numbers[index], numbers[index + 1]] for index in range(0, len(numbers), 2)]
    return pairs, True


def _signature_window(content: bytes, match: re.Match[bytes]) -> bytes:
    return content[max(0, match.start() - 8000) : min(len(content), match.end() + 4000)]


def _first_text(pattern: re.Pattern[bytes], raw: bytes) -> str | None:
    match = pattern.search(raw)
    if not match:
        return None
    try:
        return match.group(1).decode("latin-1", errors="replace").strip() or None
    except Exception:
        return None


def _inspect_pdf_signature(content: bytes, version: DocumentVersion) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "engine_version": INSPECTION_VERSION,
        "advisory_only": True,
        "cryptographically_verified": False,
        "trust_chain_checked": False,
        "revocation_checked": False,
        "document_sha256": version.sha256,
        "file_size": len(content),
    }
    type_matches = list(_SIGNATURE_TYPE_RE.finditer(content))
    pairs, byte_range_present = _parse_byte_ranges(content)
    signed = bool(type_matches) or byte_range_present

    window = _signature_window(content, type_matches[0]) if type_matches else content
    filters = sorted(
        {
            match.group(1).decode("latin-1", errors="replace")
            for match in _SIGNATURE_FILTER_RE.finditer(window)
        }
    )
    signature_fields = {
        "signer_name": _first_text(_SIGNATURE_NAME_RE, window),
        "signing_time": _first_text(_SIGNATURE_TIME_RE, window),
        "filters": filters,
    }

    if not signed:
        return {
            **evidence,
            "state": "NO_PDF_SIGNATURE",
            "message": (
                "No embedded PDF signature structure was detected. Many legitimate documents are unsigned; "
                "absence of a signature is not a finding about authenticity."
            ),
            "status": IssuerVerificationStatus.NOT_FOUND,
            "signature_count": 0,
            "byte_range_present": False,
            "covers_whole_document": False,
            "coverage_ratio": 0.0,
            "residual_bytes": None,
            "signature_fields": signature_fields,
        }

    if not byte_range_present or pairs is None:
        return {
            **evidence,
            "state": "PDF_SIGNATURE_UNSUPPORTED_STRUCTURE",
            "message": (
                "A PDF signature marker was detected without a usable byte range, so integrity coverage "
                "cannot be established. This is advisory and requires manual review."
            ),
            "status": IssuerVerificationStatus.SOURCE_UNAVAILABLE,
            "signature_count": len(type_matches),
            "byte_range_present": byte_range_present,
            "covers_whole_document": False,
            "coverage_ratio": 0.0,
            "residual_bytes": None,
            "signature_fields": signature_fields,
        }

    file_size = len(content)
    ranges_valid = all(
        start >= 0 and length >= 0 and start + length <= file_size for start, length in pairs
    )
    covered = sum(length for _start, length in pairs) if ranges_valid else 0
    residual = file_size - covered
    contiguous = ranges_valid and bool(pairs) and pairs[0][0] == 0
    if contiguous:
        contiguous = all(
            pairs[index][0] + pairs[index][1] <= pairs[index + 1][0]
            for index in range(len(pairs) - 1)
        )
    coverage_ratio = round(covered / file_size, 4) if file_size else 0.0
    covers_whole_document = bool(
        contiguous and residual >= 0 and residual <= MAX_SIGNATURE_GAP_BYTES
    )

    if not ranges_valid or not contiguous or not covers_whole_document:
        return {
            **evidence,
            "state": "PDF_SIGNATURE_COVERAGE_INCOMPLETE",
            "message": (
                "A PDF signature structure was detected, but its byte ranges do not cover the document "
                "consistently. This may indicate a modification after signing or an unsupported signing layout. "
                "It is an advisory structural observation, not proof of alteration; manual review is required."
            ),
            "status": IssuerVerificationStatus.MISMATCH,
            "signature_count": len(type_matches),
            "byte_range_present": True,
            "covers_whole_document": False,
            "coverage_ratio": coverage_ratio,
            "residual_bytes": residual,
            "signature_fields": signature_fields,
        }

    return {
        **evidence,
        "state": "PDF_SIGNATURE_PRESENT_UNVERIFIED",
        "message": (
            "An embedded PDF signature structure was detected and its byte ranges cover the document apart "
            "from the signature placeholder. The cryptographic signature, signer certificate, revocation, and "
            "trust chain were NOT verified; this is advisory evidence only."
        ),
        "status": IssuerVerificationStatus.SOURCE_UNAVAILABLE,
        "signature_count": len(type_matches),
        "byte_range_present": True,
        "covers_whole_document": True,
        "coverage_ratio": coverage_ratio,
        "residual_bytes": residual,
        "signature_fields": signature_fields,
    }


def _record(
    db: Session,
    *,
    version: DocumentVersion,
    actor: User,
    adapter_code: str,
    result: dict[str, Any],
) -> IssuerVerification:
    evidence = {key: value for key, value in result.items() if key not in {"status", "message"}}
    return record_verification(
        db,
        version=version,
        adapter_code=adapter_code,
        status=result["status"],
        message=result["message"],
        evidence=evidence,
        simulated_source=False,
        credential=None,
        actor=actor,
    )


def inspect_document_version(
    db: Session, *, version: DocumentVersion, actor: User
) -> list[IssuerVerification]:
    """Run advisory QR and (for PDFs) signature-structure inspection."""
    content = get_object_store().get(version.storage_key)
    results: list[IssuerVerification] = []

    qr_result = _inspect_qr(content, version)
    results.append(
        _record(db, version=version, actor=actor, adapter_code=QR_ADAPTER_CODE, result=qr_result)
    )

    if _is_pdf(version):
        try:
            signature_result = _inspect_pdf_signature(content, version)
        except Exception:
            logger.exception("PDF signature inspection failed version_id=%s", version.id)
            signature_result = {
                "engine_version": INSPECTION_VERSION,
                "advisory_only": True,
                "cryptographically_verified": False,
                "trust_chain_checked": False,
                "document_sha256": version.sha256,
                "state": "PDF_PARSE_FAILED",
                "message": "The PDF signature structure could not be parsed. This is not a finding about authenticity.",
                "status": IssuerVerificationStatus.ERROR,
            }
        results.append(
            _record(
                db,
                version=version,
                actor=actor,
                adapter_code=PDF_SIGNATURE_ADAPTER_CODE,
                result=signature_result,
            )
        )
    return results


def supports_inspection(version: DocumentVersion) -> bool:
    return _is_pdf(version) or _is_image(version)


def is_technical_adapter(adapter_code: str) -> bool:
    return adapter_code in {QR_ADAPTER_CODE, PDF_SIGNATURE_ADAPTER_CODE}


def latest_technical_verifications(
    verifications: Iterable[IssuerVerification],
) -> list[IssuerVerification]:
    """Keep the newest technical inspection per document version and adapter."""
    latest: dict[tuple[uuid.UUID, str], IssuerVerification] = {}
    for item in verifications:
        if not is_technical_adapter(item.adapter_code):
            continue
        key = (item.document_version_id, item.adapter_code)
        current = latest.get(key)
        if current is None or item.created_at > current.created_at:
            latest[key] = item
    return sorted(latest.values(), key=lambda item: (str(item.document_version_id), item.adapter_code))
