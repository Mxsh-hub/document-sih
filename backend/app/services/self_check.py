"""Pre-submission self-check for applicants (M5).

This module answers one narrow question: *if the applicant pressed submit now,
would the submission be accepted, and what should they fix first?*

It is deliberately read-only and deterministic:

* it performs no writes, no validation run, and no audit event;
* its only blocking checks are the missing checklist items returned by the same
  ``missing_required_items`` helper that ``submit_application`` uses, so the
  self-check cannot disagree with the actual submission gate;
* everything else is advisory guidance about likely findings, never a
  prediction of approval or a statement about authenticity.

Findings stay advisory. A clean self-check means "submission is possible", not
"the application will be approved" and not "the declaration is true".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DocumentStatus, ExtractionStatus, RuleOutcome
from app.db.models import Application, Document, Extraction
from app.services.applications import missing_required_items
from app.services.assurance import list_anomalies
from app.services.declarations import get_declaration
from app.services.issuers import list_verifications
from app.services.technical_verification import latest_technical_verifications
from app.services.validation import latest_run_for_application

SELF_CHECK_VERSION = "self-check-1.0"
EXTRACTION_ATTENTION = {
    ExtractionStatus.PENDING,
    ExtractionStatus.FAILED,
    ExtractionStatus.UNREADABLE,
}
DECLARATION_REQUIRED_HINTS = (
    ("affiliation_number", "affiliation number"),
    ("affiliation_valid_until", "affiliation validity date"),
    ("programmes", "at least one programme"),
    ("faculty_count", "faculty count"),
)


def _check(
    code: str,
    level: str,
    title: str,
    message: str,
    *,
    remediation: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "level": level,
        "title": title,
        "message": message,
        "remediation": remediation,
        "details": details or {},
    }


def _document_extractions(db: Session, documents: list[Document]) -> dict[str, Extraction]:
    version_ids = [document.current_version_id for document in documents if document.current_version_id]
    if not version_ids:
        return {}
    rows = db.scalars(select(Extraction).where(Extraction.document_version_id.in_(version_ids)))
    by_version = {str(row.document_version_id): row for row in rows}
    return {
        str(document.current_version_id): by_version[str(document.current_version_id)]
        for document in documents
        if document.current_version_id and str(document.current_version_id) in by_version
    }


def _declaration_check(db: Session, application: Application) -> list[dict[str, Any]]:
    declaration = get_declaration(db, application.id)
    if declaration is None:
        return [
            _check(
                "DECLARATION_MISSING",
                "WARNING",
                "No structured declaration saved",
                "Three consistency checks will return NOT_AVAILABLE without a declaration. "
                "The declaration is applicant-supplied and is never treated as verified.",
                remediation="Save the declaration with affiliation, programme, and faculty details.",
            )
        ]
    missing = [
        label
        for field, label in DECLARATION_REQUIRED_HINTS
        if not getattr(declaration, field, None)
    ]
    if missing:
        return [
            _check(
                "DECLARATION_INCOMPLETE",
                "WARNING",
                "Structured declaration is incomplete",
                "Missing: " + ", ".join(missing) + ". Affected consistency checks may return "
                "NOT_AVAILABLE or compare against partial declared data.",
                remediation="Complete the declaration. Declared values are never verified by the system.",
                details={"missing": missing},
            )
        ]
    return [
        _check(
            "DECLARATION_PRESENT",
            "OK",
            "Structured declaration is complete",
            "Declared values are saved and will be compared with extracted fields and synthetic "
            "records. A match only means two sources agree; it does not verify the declaration.",
        )
    ]


def build_self_check(db: Session, application: Application) -> dict[str, Any]:
    """Return advisory submission-readiness checks for a draft application."""
    checks: list[dict[str, Any]] = []

    missing_codes = missing_required_items(db, application)
    by_code = {item.code: item for item in application.checklist_items}
    for code in missing_codes:
        item = by_code.get(code)
        checks.append(
            _check(
                f"CHECKLIST_MISSING:{code}",
                "BLOCKING",
                item.title if item else code,
                "This required checklist item has no accepted document and no justification. "
                "Submission is blocked while it is incomplete.",
                remediation="Upload an accepted document for this item, or record a justification.",
                details={
                    "checklist_code": code,
                    "accepted_document_types": item.accepted_document_types if item else [],
                },
            )
        )
    if not missing_codes:
        checks.append(
            _check(
                "CHECKLIST_COMPLETE",
                "OK",
                "Required checklist items have evidence",
                "Every required item has an accepted document or a justification.",
            )
        )

    documents = list(db.scalars(select(Document).where(Document.application_id == application.id)))
    extractions = _document_extractions(db, documents)
    for document in documents:
        version = document.current_version
        label = version.original_filename if version else document.document_type.value
        if document.status in {DocumentStatus.FAILED, DocumentStatus.QUARANTINED}:
            checks.append(
                _check(
                    f"DOCUMENT_REJECTED:{document.id}",
                    "WARNING",
                    f"Document {label} is not usable",
                    f"The document status is {document.status.value}; it cannot stand as evidence. "
                    "If it covers a required item, that item is already reported as blocking.",
                    remediation="Replace the document with a readable accepted file.",
                    details={"document_id": str(document.id)},
                )
            )
            continue
        if not document.current_version_id:
            checks.append(
                _check(
                    f"DOCUMENT_UNVERSIONED:{document.id}",
                    "WARNING",
                    f"Document {label} has no stored version",
                    "The checklist item still points at a document without a current version. "
                    "If it covers a required item, that item is already reported as blocking.",
                    remediation="Re-upload the document.",
                    details={"document_id": str(document.id)},
                )
            )
            continue
        extraction = extractions.get(str(document.current_version_id))
        if extraction is None or extraction.status in EXTRACTION_ATTENTION:
            status = extraction.status.value if extraction else "NOT_STARTED"
            checks.append(
                _check(
                    f"EXTRACTION_ATTENTION:{document.id}",
                    "WARNING",
                    f"Text extraction needs attention: {label}",
                    f"Extraction status is {status}. Rules that depend on extracted fields may be "
                    "INCONCLUSIVE or NOT_AVAILABLE. This is advisory and does not block submission.",
                    remediation="Reprocess the document or upload a clearer copy if the text is missing.",
                    details={"document_id": str(document.id), "extraction_status": status},
                )
            )

    checks.extend(_declaration_check(db, application))

    run = latest_run_for_application(db, application.id)
    if run is None:
        checks.append(
            _check(
                "VALIDATION_NOT_RUN",
                "INFO",
                "No validation run exists yet",
                "A validation run is created when the application is submitted. The self-check "
                "does not run the rule engine.",
            )
        )
    else:
        counts = (run.summary or {}).get("counts", {})
        failing = int(counts.get(RuleOutcome.FAIL.value, 0))
        inconclusive = int(counts.get(RuleOutcome.INCONCLUSIVE.value, 0))
        if failing or inconclusive:
            codes = [
                finding.code
                for finding in run.findings
                if finding.outcome in {RuleOutcome.FAIL, RuleOutcome.INCONCLUSIVE}
            ]
            checks.append(
                _check(
                    "VALIDATION_ATTENTION",
                    "WARNING",
                    "Latest validation run has findings to review",
                    f"{failing} FAIL and {inconclusive} INCONCLUSIVE finding(s) in the latest run. "
                    "Findings are advisory and never auto-reject.",
                    remediation="Open the findings and inspect the linked evidence before submitting.",
                    details={"fail": failing, "inconclusive": inconclusive, "rule_codes": codes},
                )
            )
        else:
            checks.append(
                _check(
                    "VALIDATION_CLEAN",
                    "OK",
                    "Latest validation run has no failing findings",
                    "No FAIL or INCONCLUSIVE findings in the latest validation run. This is not an "
                    "approval and does not prove the documents are authentic.",
                )
            )

    signals = list_anomalies(db, application.id)
    if signals:
        checks.append(
            _check(
                "ANOMALY_SIGNALS",
                "WARNING",
                "Advisory anomaly signals are present",
                f"{len(signals)} advisory signal(s) were raised. They are heuristics, not findings "
                "of forgery or fraud.",
                remediation="Review the signals with their evidence; no automatic action is taken.",
                details={"signal_codes": [signal.signal_code for signal in signals]},
            )
        )

    verifications: list = []
    for document in documents:
        if document.current_version_id:
            verifications.extend(list_verifications(db, document.current_version_id))
    inspected = {
        str(item.document_version_id)
        for item in latest_technical_verifications(verifications)
    }
    own_versions = {
        str(document.current_version_id)
        for document in documents
        if document.current_version_id
        and (
            document.current_version.mime_type == "application/pdf"
            or document.current_version.mime_type.startswith("image/")
        )
    }
    if own_versions - inspected:
        checks.append(
            _check(
                "TECHNICAL_INSPECTION_AVAILABLE",
                "INFO",
                "QR/signature inspection has not been run on every document",
                "Technical inspection is optional and advisory. It can record QR payloads and PDF "
                "signature structure, but it never fetches payloads or verifies cryptography.",
                remediation="Staff can run technical inspection from the review console.",
            )
        )

    counts = {"BLOCKING": 0, "WARNING": 0, "INFO": 0, "OK": 0}
    for check in checks:
        counts[check["level"]] = counts.get(check["level"], 0) + 1

    return {
        "application_id": application.id,
        "reference_no": application.reference_no,
        "status": application.status,
        "check_version": SELF_CHECK_VERSION,
        "generated_at": datetime.now(timezone.utc),
        # Only the checklist gate can block submission; this is the same list
        # ``submit_application`` rejects on, so the preview cannot be stricter.
        "can_submit": not missing_codes,
        "counts": counts,
        "checks": checks,
        "advisory_note": (
            "This self-check previews whether submission would be accepted and highlights likely "
            "findings. It does not run the validation rules, does not predict approval, and cannot "
            "verify any applicant-declared value."
        ),
    }
