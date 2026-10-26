from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.enums import (
    ChecklistItemStatus,
    DocumentStatus,
    DocumentType,
    RuleOutcome,
    RuleSeverity,
    RuleSetStatus,
    ValidationStatus,
)
from app.db.models import (
    Application,
    ApplicationChecklistItem,
    ApplicationDeclaration,
    Document,
    DocumentVersion,
    ExtractedField,
    Extraction,
    Finding,
    FindingEvidence,
    RecordSnapshot,
    Rule,
    RuleSet,
    User,
    ValidationRun,
)
from app.services.audit import record_audit
from app.services.records import get_record_bundle

logger = logging.getLogger(__name__)

ENGINE_VERSION = "rules-phase5-1.1"


@dataclass
class Evidence:
    evidence_type: str
    label: str
    entity_id: uuid.UUID | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class RuleResult:
    outcome: RuleOutcome
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)


def active_rule_set(db: Session, application: Application) -> RuleSet | None:
    return db.scalar(
        select(RuleSet)
        .where(
            RuleSet.category_id == application.category_id,
            RuleSet.status == RuleSetStatus.ACTIVE,
        )
        .order_by(RuleSet.version.desc())
        .limit(1)
    )


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _current_documents(db: Session, application_id: uuid.UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.created_at.desc())
        )
    )


def _latest_document(db: Session, application_id: uuid.UUID, document_type: DocumentType) -> Document | None:
    return db.scalar(
        select(Document)
        .where(
            Document.application_id == application_id,
            Document.document_type == document_type,
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )


def _extraction_for_document(db: Session, document: Document) -> Extraction | None:
    if document.current_version_id is None:
        return None
    return db.scalar(
        select(Extraction).where(Extraction.document_version_id == document.current_version_id)
    )


def _field_values(extraction: Extraction | None, name: str) -> list[ExtractedField]:
    if not extraction:
        return []
    return [item for item in extraction.fields if item.name == name]


def _evidence_for_field(document: Document, item: ExtractedField) -> Evidence:
    return Evidence(
        evidence_type="EXTRACTED_FIELD",
        entity_id=item.id,
        label=f"{item.name} from {document.document_type.value}",
        metadata={
            "document_id": str(document.id),
            "document_version_id": str(document.current_version_id),
            "field": item.name,
            "raw_value": item.raw_value,
            "normalized_value": item.normalized_value,
            "page": item.page,
            "bbox": item.bbox,
            "page_width": float(item.page_width) if item.page_width is not None else None,
            "page_height": float(item.page_height) if item.page_height is not None else None,
            "confidence": float(item.confidence) if item.confidence is not None else None,
        },
    )


def _evidence_for_document(document: Document, label: str) -> Evidence:
    return Evidence(
        evidence_type="DOCUMENT",
        entity_id=document.id,
        label=label,
        metadata={
            "document_type": document.document_type.value,
            "document_version_id": str(document.current_version_id) if document.current_version_id else None,
            "status": document.status.value,
        },
    )


def _date_value(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _name_matches(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        value = value.casefold()
        value = re.sub(r"\(synthetic\)", "", value)
        value = re.sub(r"[^a-z0-9 ]", " ", value)
        stop = {"the", "of", "and", "institute", "college", "university", "technology", "engineering"}
        tokens = [token for token in value.split() if token and token not in stop]
        return " ".join(tokens)

    left_norm = normalize(left)
    right_norm = normalize(right)
    if not left_norm or not right_norm:
        return False
    if left_norm in right_norm or right_norm in left_norm:
        return True
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens)) >= 0.6


def _checklist_result(db: Session, application: Application, rule: Rule) -> RuleResult:
    accepted = {
        ChecklistItemStatus(value)
        for value in rule.config.get("accepted_statuses", ["SATISFIED", "WAIVED"])
    }
    missing: list[ApplicationChecklistItem] = []
    for item in application.checklist_items:
        if item.required and item.status not in accepted:
            missing.append(item)
    if not missing:
        return RuleResult(
            outcome=RuleOutcome.PASS,
            message="Every required checklist item has evidence or an authorised waiver.",
            details={"missing": []},
        )
    return RuleResult(
        outcome=RuleOutcome.FAIL,
        message="One or more required checklist items are not yet satisfied.",
        details={"missing": [item.code for item in missing]},
        evidence=[
            Evidence(
                evidence_type="CHECKLIST_ITEM",
                entity_id=item.id,
                label=item.title,
                metadata={"code": item.code, "status": item.status.value},
            )
            for item in missing
        ],
    )


def _extraction_result(db: Session, application: Application, rule: Rule) -> RuleResult:
    minimum = float(rule.config.get("min_confidence", 0.45))
    documents = _current_documents(db, application.id)
    if not documents:
        return RuleResult(outcome=RuleOutcome.NOT_AVAILABLE, message="No documents were available for extraction review.")
    failed: list[Document] = []
    inconclusive: list[Document] = []
    evidence: list[Evidence] = []
    for document in documents:
        extraction = _extraction_for_document(db, document)
        if document.status is DocumentStatus.FAILED or extraction is None:
            failed.append(document)
            evidence.append(_evidence_for_document(document, "Document text could not be processed"))
            continue
        confidence = float(extraction.confidence or 0)
        if extraction.status.value != "COMPLETED" or confidence < minimum:
            inconclusive.append(document)
            evidence.append(
                Evidence(
                    evidence_type="DOCUMENT",
                    entity_id=document.id,
                    label="Extraction confidence is below the configured review threshold",
                    metadata={
                        "document_type": document.document_type.value,
                        "status": extraction.status.value,
                        "confidence": confidence,
                        "threshold": minimum,
                    },
                )
            )
    if failed:
        return RuleResult(
            outcome=RuleOutcome.FAIL,
            message="At least one document could not be read well enough for automated checks.",
            details={"failed_document_ids": [str(item.id) for item in failed]},
            evidence=evidence,
        )
    if inconclusive:
        return RuleResult(
            outcome=RuleOutcome.INCONCLUSIVE,
            message="Some documents need manual review because extraction confidence is low.",
            details={"inconclusive_document_ids": [str(item.id) for item in inconclusive]},
            evidence=evidence,
        )
    return RuleResult(
        outcome=RuleOutcome.PASS,
        message="All current documents were processed with sufficient extraction confidence.",
        details={"document_count": len(documents)},
    )


def _date_validity_result(db: Session, application: Application, rule: Rule) -> RuleResult:
    document_type = DocumentType(rule.config.get("document_type", "AFFILIATION_CERTIFICATE"))
    field_name = rule.config.get("date_field", "valid_until")
    document = _latest_document(db, application.id, document_type)
    if not document:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message=f"No {document_type.value} document was available for the date check.",
        )
    extraction = _extraction_for_document(db, document)
    fields = _field_values(extraction, field_name)
    if not fields:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message=f"The {field_name} field could not be extracted from the {document_type.value} document.",
            evidence=[_evidence_for_document(document, "Document available but required date field missing")],
        )
    parsed = _date_value(fields[0].normalized_value)
    if not parsed:
        return RuleResult(
            outcome=RuleOutcome.INCONCLUSIVE,
            message=f"The extracted {field_name} value could not be interpreted as a date.",
            evidence=[_evidence_for_field(document, fields[0])],
        )
    if parsed < date.today():
        return RuleResult(
            outcome=RuleOutcome.FAIL,
            message=f"The extracted {field_name} date ({parsed.isoformat()}) is earlier than the validation date.",
            details={"date": parsed.isoformat(), "validation_date": date.today().isoformat()},
            evidence=[_evidence_for_field(document, fields[0])],
        )
    return RuleResult(
        outcome=RuleOutcome.PASS,
        message=f"The extracted {field_name} date ({parsed.isoformat()}) is not expired at the validation date.",
        details={"date": parsed.isoformat(), "validation_date": date.today().isoformat()},
        evidence=[_evidence_for_field(document, fields[0])],
    )


def _field_consistency_result(db: Session, application: Application, rule: Rule) -> RuleResult:
    field_name = rule.config.get("field", "institution_name")
    document_types = [
        DocumentType(value) for value in rule.config.get("document_types", [])
    ]
    evidence: list[Evidence] = []
    checked = 0
    mismatches: list[str] = []
    for document_type in document_types:
        document = _latest_document(db, application.id, document_type)
        if not document:
            continue
        extraction = _extraction_for_document(db, document)
        for item in _field_values(extraction, field_name):
            checked += 1
            evidence.append(_evidence_for_field(document, item))
            if not _name_matches(item.normalized_value or item.raw_value or "", application.institution.legal_name):
                mismatches.append(item.raw_value or item.normalized_value or "")
    if checked == 0:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message=f"The {field_name} value could not be extracted from the relevant documents.",
        )
    if mismatches:
        return RuleResult(
            outcome=RuleOutcome.FAIL,
            message="An extracted institution name does not match the institution profile and needs review.",
            details={"extracted_values": mismatches, "institution_profile": application.institution.legal_name},
            evidence=evidence,
        )
    return RuleResult(
        outcome=RuleOutcome.PASS,
        message="Extracted institution names are consistent with the institution profile.",
        details={"checked_values": checked},
        evidence=evidence,
    )


def _record_result(rule: Rule, records: dict[str, Any]) -> RuleResult:
    record_type = rule.config.get("record_type", "")
    group = records.get(record_type, {})
    items = group.get("items", [])
    if not items:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message=f"No synthetic {record_type} records were available for this institution.",
        )
    evidence = [
        Evidence(
            evidence_type="RECORD",
            entity_id=uuid.UUID(item["id"]) if item.get("id") else None,
            label=f"Synthetic {record_type} record",
            metadata={"record_type": record_type, "source": group.get("source")},
        )
        for item in items[:5]
    ]
    if rule.code == "PREVIOUS_APPROVAL_STATUS":
        accepted = {str(value).upper() for value in rule.config.get("statuses", ["APPROVED", "ACTIVE"])}
        latest = sorted(items, key=lambda item: item.get("valid_until") or "", reverse=True)[0]
        status = str(latest.get("status", "")).upper()
        if status in accepted:
            return RuleResult(
                outcome=RuleOutcome.PASS,
                message=f"The latest synthetic approval record status is {status}.",
                details={"status": status, "record_id": latest.get("id")},
                evidence=evidence,
            )
        return RuleResult(
            outcome=RuleOutcome.FAIL,
            message=f"The latest synthetic approval record status is {status}; review is required.",
            details={"status": status, "record_id": latest.get("id")},
            evidence=evidence,
        )
    if rule.code == "TER_PAYMENT_STATUS":
        accepted = {str(value).upper() for value in rule.config.get("statuses", ["PAID"])}
        latest = items[0]
        status = str(latest.get("status", "")).upper()
        outcome = RuleOutcome.PASS if status in accepted else RuleOutcome.FAIL
        return RuleResult(
            outcome=outcome,
            message=f"The latest synthetic TER record status is {status}.",
            details={"status": status, "record_id": latest.get("id")},
            evidence=evidence,
        )
    if rule.code == "ACCREDITATION_VALIDITY":
        statuses = {str(item.get("status", "")).upper() for item in items}
        valid_dates = [
            _date_value(item.get("valid_until")) for item in items if item.get("valid_until")
        ]
        if "ACTIVE" not in statuses:
            return RuleResult(
                outcome=RuleOutcome.FAIL,
                message="No active synthetic accreditation record was available.",
                details={"statuses": sorted(statuses)},
                evidence=evidence,
            )
        if not valid_dates:
            return RuleResult(
                outcome=RuleOutcome.INCONCLUSIVE,
                message="An active synthetic accreditation record exists but has no validity date.",
                evidence=evidence,
            )
        if max(valid_dates) < date.today():
            return RuleResult(
                outcome=RuleOutcome.FAIL,
                message="The synthetic accreditation record is expired at the validation date.",
                details={"latest_valid_until": max(valid_dates).isoformat()},
                evidence=evidence,
            )
        return RuleResult(
            outcome=RuleOutcome.PASS,
            message="The synthetic accreditation record is active and not expired.",
            details={"latest_valid_until": max(valid_dates).isoformat()},
            evidence=evidence,
        )
    if rule.code == "OPEN_DEFICIENCIES":
        blocking = {str(value).upper() for value in rule.config.get("blocking_statuses", ["OPEN", "UNRESOLVED"])}
        open_items = [item for item in items if str(item.get("status", "")).upper() in blocking]
        if open_items:
            return RuleResult(
                outcome=RuleOutcome.FAIL,
                message="One or more synthetic compliance deficiencies remain open.",
                details={"open_deficiencies": [item.get("code") for item in open_items]},
                evidence=evidence,
            )
        return RuleResult(
            outcome=RuleOutcome.PASS,
            message="No open synthetic compliance deficiencies were found.",
            evidence=evidence,
        )
    if rule.code == "FACULTY_APPROVED_MINIMUM":
        minimum = int(rule.config.get("minimum", 0))
        accepted = {str(value).upper() for value in rule.config.get("statuses", ["APPROVED"])}
        approved = [
            item for item in items if str(item.get("approved_status", "")).upper() in accepted
        ]
        outcome = RuleOutcome.PASS if len(approved) >= minimum else RuleOutcome.FAIL
        return RuleResult(
            outcome=outcome,
            message=f"{len(approved)} synthetic faculty records meet the configured minimum of {minimum}.",
            details={"approved_faculty": len(approved), "minimum": minimum, "configured_threshold": True},
            evidence=evidence,
        )
    return RuleResult(
        outcome=RuleOutcome.NOT_APPLICABLE,
        message="No evaluator is configured for this synthetic rule.",
    )


# --- Structured declaration consistency ------------------------------------
#
# Each rule compares applicant-declared values with either extracted document
# fields or synthetic institutional records. Every outcome is advisory: a
# mismatch means "a human should look at these two sources", never "the
# applicant lied" and never an automatic rejection.


def _declaration_for(db: Session, application: Application) -> ApplicationDeclaration | None:
    return db.scalar(
        select(ApplicationDeclaration).where(
            ApplicationDeclaration.application_id == application.id
        )
    )


def _first_text(fields: list[ExtractedField]) -> str | None:
    if not fields:
        return None
    return fields[0].normalized_value or fields[0].raw_value


def _normalize_identifier(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _evidence_for_declaration(declaration: ApplicationDeclaration) -> Evidence:
    return Evidence(
        evidence_type="DECLARATION",
        entity_id=declaration.id,
        label=f"Applicant declaration v{declaration.version}",
        metadata={
            "affiliation_number": declaration.affiliation_number,
            "affiliation_valid_until": _iso(declaration.affiliation_valid_until),
            "programmes": declaration.programmes,
            "total_intake": declaration.total_intake,
            "faculty_count": declaration.faculty_count,
            "previous_approval_reference": declaration.previous_approval_reference,
            "version": declaration.version,
            "advisory": True,
            "note": "Applicant-supplied declaration; not verified data.",
        },
    )


def _evidence_for_records(
    records: dict[str, Any], record_type: str, label: str
) -> Evidence:
    group = records.get(record_type) or {}
    items = group.get("items") or []
    return Evidence(
        evidence_type="RECORD",
        label=label,
        metadata={
            "record_type": record_type,
            "count": len(items),
            "source": group.get("source"),
            "synthetic": True,
            "items": items[:10],
        },
    )


def _declaration_affiliation_result(
    db: Session, application: Application
) -> RuleResult:
    declaration = _declaration_for(db, application)
    if declaration is None:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="No structured declaration has been saved for this application.",
        )
    if declaration.affiliation_number is None and declaration.affiliation_valid_until is None:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="The declaration does not state affiliation details.",
            evidence=[_evidence_for_declaration(declaration)],
        )
    document = _latest_document(db, application.id, DocumentType.AFFILIATION_CERTIFICATE)
    extraction = _extraction_for_document(db, document) if document else None
    if document is None or extraction is None:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="The affiliation certificate is missing or has not been extracted, so the declaration cannot be compared.",
            evidence=[_evidence_for_declaration(declaration)],
        )
    number_fields = _field_values(extraction, "affiliation_number")
    date_fields = _field_values(extraction, "valid_until")
    extracted_number = _first_text(number_fields)
    extracted_valid = _date_value(_first_text(date_fields))
    if extracted_number is None and extracted_valid is None:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="No comparable affiliation fields were extracted from the certificate.",
            evidence=[_evidence_for_declaration(declaration)],
        )

    mismatches: list[dict[str, Any]] = []
    if declaration.affiliation_number is not None:
        if extracted_number is None:
            mismatches.append({"field": "affiliation_number", "reason": "not_extracted"})
        elif _normalize_identifier(declaration.affiliation_number) != _normalize_identifier(extracted_number):
            mismatches.append({"field": "affiliation_number", "reason": "value_mismatch"})
    if declaration.affiliation_valid_until is not None:
        if extracted_valid is None:
            mismatches.append({"field": "valid_until", "reason": "not_extracted"})
        elif declaration.affiliation_valid_until != extracted_valid:
            mismatches.append({"field": "valid_until", "reason": "value_mismatch"})

    evidence = [_evidence_for_declaration(declaration)]
    evidence.extend(_evidence_for_field(document, item) for item in number_fields[:1])
    evidence.extend(_evidence_for_field(document, item) for item in date_fields[:1])
    details = {
        "declared": {
            "affiliation_number": declaration.affiliation_number,
            "affiliation_valid_until": _iso(declaration.affiliation_valid_until),
        },
        "extracted": {
            "document_type": document.document_type.value,
            "affiliation_number": extracted_number,
            "valid_until": _iso(extracted_valid),
        },
        "mismatches": mismatches,
        "advisory": True,
    }
    if mismatches:
        return RuleResult(
            outcome=RuleOutcome.FAIL,
            message="Declared affiliation details differ from the extracted certificate; review both sources.",
            details=details,
            evidence=evidence,
        )
    return RuleResult(
        outcome=RuleOutcome.PASS,
        message="Declared affiliation details agree with the extracted certificate.",
        details=details,
        evidence=evidence,
    )


def _declaration_programme_result(
    records: dict[str, Any], declaration: ApplicationDeclaration | None
) -> RuleResult:
    if declaration is None:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="No structured declaration has been saved for this application.",
        )
    declared = [item for item in (declaration.programmes or []) if item.get("code")]
    if not declared:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="The declaration does not list any programmes.",
            evidence=[_evidence_for_declaration(declaration)],
        )
    record_items = (records.get("programmes") or {}).get("items") or []
    if not record_items:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="No synthetic programme records are available for comparison.",
            evidence=[_evidence_for_declaration(declaration)],
        )

    record_by_code = {str(item.get("code", "")).upper(): item for item in record_items}
    declared_codes = [str(item["code"]).upper() for item in declared]
    missing_in_records = sorted(set(declared_codes) - set(record_by_code))
    unlisted_in_declaration = sorted(set(record_by_code) - set(declared_codes))
    intake_mismatches: list[dict[str, Any]] = []
    for item in declared:
        record = record_by_code.get(str(item["code"]).upper())
        if not record:
            continue
        declared_intake = item.get("intake")
        record_intake = record.get("intake")
        if declared_intake is not None and record_intake is not None:
            if int(declared_intake) != int(record_intake):
                intake_mismatches.append(
                    {
                        "code": str(item["code"]).upper(),
                        "declared": int(declared_intake),
                        "record": int(record_intake),
                    }
                )

    declared_intakes = [int(item["intake"]) for item in declared if item.get("intake") is not None]
    declared_intake_sum = sum(declared_intakes)
    total_intake_mismatch = (
        declaration.total_intake is not None
        and bool(declared_intakes)
        and declaration.total_intake != declared_intake_sum
    )

    problems = bool(missing_in_records or intake_mismatches or total_intake_mismatch)
    details = {
        "declared_codes": declared_codes,
        "record_codes": sorted(record_by_code),
        "missing_in_records": missing_in_records,
        "unlisted_in_declaration": unlisted_in_declaration,
        "intake_mismatches": intake_mismatches,
        "declared_total_intake": declaration.total_intake,
        "declared_intake_sum": declared_intake_sum if declared_intakes else None,
        "total_intake_mismatch": total_intake_mismatch,
        "advisory": True,
    }
    evidence = [
        _evidence_for_declaration(declaration),
        _evidence_for_records(records, "programmes", "Synthetic programme records"),
    ]
    if problems:
        return RuleResult(
            outcome=RuleOutcome.FAIL,
            message="Declared programmes or intake differ from the synthetic programme records.",
            details=details,
            evidence=evidence,
        )
    return RuleResult(
        outcome=RuleOutcome.PASS,
        message="Declared programmes and intake agree with the synthetic programme records.",
        details=details,
        evidence=evidence,
    )


def _declaration_faculty_result(
    records: dict[str, Any], rule: Rule, declaration: ApplicationDeclaration | None
) -> RuleResult:
    if declaration is None:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="No structured declaration has been saved for this application.",
        )
    if declaration.faculty_count is None:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="The declaration does not state a faculty count.",
            evidence=[_evidence_for_declaration(declaration)],
        )
    items = (records.get("faculty") or {}).get("items") or []
    if not items:
        return RuleResult(
            outcome=RuleOutcome.NOT_AVAILABLE,
            message="No synthetic faculty records are available for comparison.",
            evidence=[_evidence_for_declaration(declaration)],
        )
    tolerance = int(rule.config.get("tolerance", 0))
    approved = [
        item for item in items if str(item.get("approved_status", "")).upper() == "APPROVED"
    ]
    difference = declaration.faculty_count - len(items)
    details = {
        "declared_faculty_count": declaration.faculty_count,
        "record_faculty_count": len(items),
        "record_approved_count": len(approved),
        "difference": difference,
        "tolerance": tolerance,
        "advisory": True,
    }
    evidence = [
        _evidence_for_declaration(declaration),
        _evidence_for_records(records, "faculty", "Synthetic faculty records"),
    ]
    if abs(difference) > tolerance:
        return RuleResult(
            outcome=RuleOutcome.FAIL,
            message=(
                f"Declared faculty count ({declaration.faculty_count}) differs from the "
                f"synthetic faculty records ({len(items)}) beyond the tolerance of {tolerance}."
            ),
            details=details,
            evidence=evidence,
        )
    return RuleResult(
        outcome=RuleOutcome.PASS,
        message="Declared faculty count agrees with the synthetic faculty records.",
        details=details,
        evidence=evidence,
    )


def _evaluate(
    db: Session, application: Application, rule: Rule, records: dict[str, Any]
) -> RuleResult:
    if rule.code == "CHECKLIST_REQUIRED":
        return _checklist_result(db, application, rule)
    if rule.code == "DOCUMENT_TEXT_EXTRACTED":
        return _extraction_result(db, application, rule)
    if rule.code == "AFFILIATION_VALIDITY":
        return _date_validity_result(db, application, rule)
    if rule.code == "INSTITUTION_NAME_CONSISTENCY":
        return _field_consistency_result(db, application, rule)
    if rule.code == "AFFILIATION_DECLARATION_MATCH":
        return _declaration_affiliation_result(db, application)
    if rule.code == "PROGRAMME_DECLARATION_MATCH":
        return _declaration_programme_result(records, _declaration_for(db, application))
    if rule.code == "FACULTY_COUNT_DECLARATION_MATCH":
        return _declaration_faculty_result(records, rule, _declaration_for(db, application))
    if rule.code in {
        "PREVIOUS_APPROVAL_STATUS",
        "TER_PAYMENT_STATUS",
        "ACCREDITATION_VALIDITY",
        "OPEN_DEFICIENCIES",
        "FACULTY_APPROVED_MINIMUM",
    }:
        return _record_result(rule, records)
    return RuleResult(
        outcome=RuleOutcome.NOT_APPLICABLE,
        message="This rule is not implemented by the current validation engine.",
    )


def _create_finding(
    db: Session, run: ValidationRun, rule: Rule, result: RuleResult
) -> None:
    finding = Finding(
        validation_run_id=run.id,
        rule_id=rule.id,
        code=rule.code,
        title=rule.title,
        outcome=result.outcome,
        severity=rule.severity,
        message=result.message,
        details=result.details,
    )
    db.add(finding)
    db.flush()
    for evidence in result.evidence:
        db.add(
            FindingEvidence(
                finding_id=finding.id,
                evidence_type=evidence.evidence_type,
                entity_id=evidence.entity_id,
                label=evidence.label,
                metadata_json=evidence.metadata,
            )
        )


def run_validation(
    db: Session, application: Application, *, actor: User | None = None
) -> ValidationRun:
    rule_set = active_rule_set(db, application)
    if not rule_set:
        raise ApiError(
            409,
            "RULE_SET_NOT_CONFIGURED",
            "No active validation rule set is configured for this application category.",
        )
    run = ValidationRun(
        application_id=application.id,
        rule_set_id=rule_set.id,
        status=ValidationStatus.RUNNING,
        initiated_by=actor.id if actor else None,
        engine_version=ENGINE_VERSION,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    bundle = get_record_bundle(db, application.institution_id)
    for record_type, group in bundle["records"].items():
        snapshot = RecordSnapshot(
            validation_run_id=run.id,
            institution_id=application.institution_id,
            record_type=record_type,
            payload=group,
            sha256=_canonical_hash(group),
        )
        db.add(snapshot)

    counts = {outcome.value: 0 for outcome in RuleOutcome}
    for rule in rule_set.rules:
        try:
            result = _evaluate(db, application, rule, bundle["records"])
        except Exception:
            logger.exception("validation rule failed code=%s run_id=%s", rule.code, run.id)
            result = RuleResult(
                outcome=RuleOutcome.INCONCLUSIVE,
                message="This check could not be completed and requires manual review.",
                details={"error": "rule_evaluation_failed"},
            )
        counts[result.outcome.value] += 1
        _create_finding(db, run, rule, result)

    run.summary = {
        "counts": counts,
        "total": len(rule_set.rules),
        "rule_set_code": rule_set.code,
        "rule_set_version": rule_set.version,
        "synthetic_rules": rule_set.synthetic,
        "records_synthetic": bundle["synthetic"],
    }
    run.status = ValidationStatus.COMPLETED
    run.completed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        event_type="validation.completed",
        actor=actor,
        application_id=application.id,
        entity_type="validation_run",
        entity_id=run.id,
        payload={
            "rule_set_id": str(rule_set.id),
            "rule_set_code": rule_set.code,
            "rule_set_version": rule_set.version,
            "summary": run.summary,
        },
    )
    db.commit()
    db.refresh(run)
    return run


def latest_run_for_application(db: Session, application_id: uuid.UUID) -> ValidationRun | None:
    return db.scalar(
        select(ValidationRun)
        .where(ValidationRun.application_id == application_id)
        .order_by(ValidationRun.created_at.desc())
        .limit(1)
    )
