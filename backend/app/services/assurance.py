from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ApiError
from app.db.enums import (
    AnomalySeverity,
    DocumentStatus,
    InfrastructureEvidenceType,
)
from app.db.models import (
    AnomalySignal,
    Application,
    Document,
    DocumentVersion,
    ExtractedField,
    Extraction,
    InfrastructureEvidence,
    User,
)
from app.services.authorization import require_application_owner
from app.services.object_store import get_object_store

logger = logging.getLogger(__name__)

SUSPICIOUS_PDF_TOOLS = ("photoshop", "gimp", "canva", "pdfedit", "illustrator", "foxit")


def _signal(
    db: Session,
    application: Application,
    *,
    code: str,
    severity: AnomalySeverity,
    score: float | None,
    message: str,
    evidence: dict[str, Any],
    source: str,
) -> AnomalySignal:
    signal = AnomalySignal(
        application_id=application.id,
        signal_code=code,
        severity=severity,
        score=score,
        advisory=True,
        message=message,
        evidence=evidence,
        source=source,
    )
    db.add(signal)
    return signal


def _current_versions(db: Session, application: Application) -> list[DocumentVersion]:
    documents = db.scalars(select(Document).where(Document.application_id == application.id))
    versions: list[DocumentVersion] = []
    for document in documents:
        if document.current_version_id:
            version = db.get(DocumentVersion, document.current_version_id)
            if version:
                versions.append(version)
    return versions


def _cross_application_hash_signals(db: Session, application: Application) -> list[AnomalySignal]:
    signals: list[AnomalySignal] = []
    for version in _current_versions(db, application):
        other = db.scalar(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentVersion.sha256 == version.sha256,
                Document.application_id != application.id,
            )
            .limit(1)
        )
        if other:
            signals.append(
                _signal(
                    db,
                    application,
                    code="CROSS_APPLICATION_FILE_REUSE",
                    severity=AnomalySeverity.MEDIUM,
                    score=0.5,
                    message="The same file hash appears in another application. This is an advisory reuse indicator, not proof of misconduct.",
                    evidence={
                        "sha256": version.sha256,
                        "other_document_version_id": str(other.id),
                        "advisory_only": True,
                    },
                    source="hash-reuse-heuristic",
                )
            )
    return signals


def _shared_identifier_signals(db: Session, application: Application) -> list[AnomalySignal]:
    signals: list[AnomalySignal] = []
    for version in _current_versions(db, application):
        extraction = db.scalar(
            select(Extraction).where(Extraction.document_version_id == version.id)
        )
        if not extraction:
            continue
        for field in extraction.fields:
            if field.name not in {"affiliation_number", "reference_number"} or not field.normalized_value:
                continue
            other = db.scalar(
                select(ExtractedField)
                .join(Extraction, Extraction.id == ExtractedField.extraction_id)
                .join(DocumentVersion, DocumentVersion.id == Extraction.document_version_id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    ExtractedField.name == field.name,
                    ExtractedField.normalized_value == field.normalized_value,
                    Document.application_id != application.id,
                )
                .limit(1)
            )
            if other:
                signals.append(
                    _signal(
                        db,
                        application,
                        code="SHARED_REFERENCE_IDENTIFIER",
                        severity=AnomalySeverity.MEDIUM,
                        score=0.55,
                        message="The same extracted reference identifier appears in another application. This is an advisory signal; human review is required to interpret it.",
                        evidence={
                            "field": field.name,
                            "normalized_value": field.normalized_value,
                            "other_extracted_field_id": str(other.id),
                            "advisory_only": True,
                        },
                        source="identifier-reuse-heuristic",
                    )
                )
    return signals


def _pdf_metadata_signals(db: Session, application: Application) -> list[AnomalySignal]:
    signals: list[AnomalySignal] = []
    store = get_object_store()
    for version in _current_versions(db, application):
        if version.mime_type != "application/pdf":
            continue
        try:
            import pymupdf

            content = store.get(version.storage_key)
            pdf = pymupdf.open(stream=content, filetype="pdf")
            metadata = pdf.metadata or {}
            fonts: set[str] = set()
            for page in pdf:
                for block in page.get_text("dict").get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if span.get("font"):
                                fonts.add(str(span["font"]))
            pdf.close()
            tool_text = f"{metadata.get('creator', '')} {metadata.get('producer', '')}".lower()
            suspicious = [tool for tool in SUSPICIOUS_PDF_TOOLS if tool in tool_text]
            if suspicious:
                signals.append(
                    _signal(
                        db,
                        application,
                        code="PDF_EDITING_TOOL_METADATA",
                        severity=AnomalySeverity.LOW,
                        score=0.35,
                        message="PDF metadata mentions an editing tool. This is an advisory heuristic and does not establish alteration.",
                        evidence={
                            "document_version_id": str(version.id),
                            "creator": metadata.get("creator"),
                            "producer": metadata.get("producer"),
                            "matched_tools": suspicious,
                            "advisory_only": True,
                        },
                        source="pdf-structure-heuristic",
                    )
                )
            if len(fonts) >= 7:
                signals.append(
                    _signal(
                        db,
                        application,
                        code="MULTIPLE_PDF_FONTS",
                        severity=AnomalySeverity.LOW,
                        score=0.3,
                        message="The document uses several fonts. This is a weak advisory signal, not evidence of tampering.",
                        evidence={
                            "document_version_id": str(version.id),
                            "font_count": len(fonts),
                            "fonts": sorted(fonts)[:20],
                            "advisory_only": True,
                        },
                        source="pdf-structure-heuristic",
                    )
                )
        except Exception:
            logger.exception("PDF heuristic failed version_id=%s", version.id)
    return signals


def scan_anomalies(db: Session, application: Application) -> list[AnomalySignal]:
    # Replace prior advisory signals for this application so repeated scans do not inflate results.
    prior = list(db.scalars(select(AnomalySignal).where(AnomalySignal.application_id == application.id)))
    for item in prior:
        db.delete(item)
    db.flush()
    signals = (
        _cross_application_hash_signals(db, application)
        + _shared_identifier_signals(db, application)
        + _pdf_metadata_signals(db, application)
    )
    db.commit()
    for signal in signals:
        db.refresh(signal)
    return signals


def list_anomalies(db: Session, application_id: uuid.UUID) -> list[AnomalySignal]:
    return list(
        db.scalars(
            select(AnomalySignal)
            .where(AnomalySignal.application_id == application_id)
            .order_by(AnomalySignal.created_at.desc())
        )
    )


def register_infrastructure_evidence(
    db: Session,
    *,
    application: Application,
    actor: User,
    evidence_type: InfrastructureEvidenceType,
    document_version_id: uuid.UUID | None,
    label: str,
    description: str | None,
    captured_at: datetime | None,
    metadata: dict[str, Any] | None,
) -> InfrastructureEvidence:
    require_application_owner(application, actor)
    if document_version_id:
        version = db.get(DocumentVersion, document_version_id)
        if not version:
            raise ApiError(404, "NOT_FOUND", "Document version not found.")
        document = db.get(Document, version.document_id)
        if not document or document.application_id != application.id:
            raise ApiError(404, "NOT_FOUND", "Document version not found for this application.")
    evidence = InfrastructureEvidence(
        application_id=application.id,
        evidence_type=evidence_type,
        document_version_id=document_version_id,
        label=label,
        description=description,
        captured_at=captured_at,
        metadata_json=metadata,
        synthetic=True,
        created_by=actor.id,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


def list_infrastructure_evidence(
    db: Session, application_id: uuid.UUID
) -> list[InfrastructureEvidence]:
    return list(
        db.scalars(
            select(InfrastructureEvidence)
            .where(InfrastructureEvidence.application_id == application_id)
            .order_by(InfrastructureEvidence.created_at.desc())
        )
    )


def infrastructure_assessment(db: Session, application: Application) -> dict[str, Any]:
    required = settings.infrastructure_required_types
    evidence = list_infrastructure_evidence(db, application.id)
    checks = []
    for required_type in required:
        matches = [item for item in evidence if item.evidence_type.value == required_type]
        if not matches:
            checks.append(
                {
                    "evidence_type": required_type,
                    "status": "MISSING",
                    "message": "No evidence of this type is registered.",
                    "evidence_ids": [],
                }
            )
            continue
        needs_review = any(
            item.document_version_id is None and item.evidence_type.value in {"PHOTO", "VIDEO"}
            for item in matches
        )
        checks.append(
            {
                "evidence_type": required_type,
                "status": "NEEDS_REVIEW" if needs_review else "PRESENT",
                "message": (
                    "Evidence is registered but lacks an attached file for completeness review."
                    if needs_review
                    else "Evidence is registered. Presence is not an authenticity finding."
                ),
                "evidence_ids": [str(item.id) for item in matches],
            }
        )
    return {
        "application_id": application.id,
        "required_types": required,
        "checks": checks,
        "complete": all(check["status"] == "PRESENT" for check in checks),
        "synthetic": True,
        "simulated": True,
        "note": "Presence and completeness checks only. No image, video, structural, or authenticity analysis is performed.",
        "assessed_at": datetime.now(timezone.utc),
    }
