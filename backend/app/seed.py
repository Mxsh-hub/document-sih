from __future__ import annotations

import argparse
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import Base, SessionLocal, engine
from app.db.enums import (
    ChecklistTemplateStatus,
    Role,
    RuleSeverity,
    RuleSetStatus,
    RuleType,
)
from app.db.models import (
    AccreditationRecord,
    ApplicationCategory,
    ApprovalHistory,
    ChecklistTemplate,
    ChecklistTemplateItem,
    ComplianceDeficiency,
    FacultyRecord,
    Institution,
    IssuerKey,
    NocPermission,
    Programme,
    Rule,
    RuleSet,
    TerPayment,
    User,
)
from app.services.auth import hash_password, normalize_email
from app.services.records import SYNTHETIC_SOURCE

SEED_PASSWORD_ENV = "SEED_PASSWORD"
DEFAULT_SEED_PASSWORD = "ChangeMe123!"


def _password() -> str:
    return os.getenv(SEED_PASSWORD_ENV, DEFAULT_SEED_PASSWORD)


def _get_or_create_institution(db: Session, **values) -> Institution:
    institution = db.scalar(
        select(Institution).where(Institution.aicte_permanent_id == values["aicte_permanent_id"])
    )
    if institution:
        return institution
    institution = Institution(**values)
    db.add(institution)
    db.flush()
    return institution


def _upsert_user(
    db: Session, *, email: str, full_name: str, role: Role, institution_id: uuid.UUID | None
) -> User:
    email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            role=role,
            institution_id=institution_id,
            password_hash=hash_password(_password()),
            is_active=True,
        )
        db.add(user)
    else:
        user.full_name = full_name
        user.role = role
        user.institution_id = institution_id
        user.is_active = True
        user.password_hash = hash_password(_password())
    db.flush()
    return user


def _seed_checklist(db: Session, category: ApplicationCategory, admin: User) -> ChecklistTemplate:
    active = db.scalar(
        select(ChecklistTemplate).where(
            ChecklistTemplate.category_id == category.id,
            ChecklistTemplate.status == ChecklistTemplateStatus.ACTIVE,
        )
    )
    if active:
        return active
    template = ChecklistTemplate(
        category_id=category.id,
        version=1,
        status=ChecklistTemplateStatus.ACTIVE,
        effective_from=date(2026, 1, 1),
        source_citation="Synthetic demo checklist; replace with the applicable AICTE Approval Process Handbook citation.",
        created_by=admin.id,
    )
    items = [
        (
            "AFFILIATION_CERTIFICATE",
            "Affiliation/recognition certificate",
            "Current university affiliation or recognition certificate.",
            True,
            ["AFFILIATION_CERTIFICATE"],
            ["REQ_AFFILIATION", "AFFILIATION_EXPIRY"],
        ),
        (
            "LAND_LEASE_DOCUMENT",
            "Land ownership or lease document",
            "Registered land document or lease deed for the institute campus.",
            True,
            ["LAND_LEASE_DOCUMENT"],
            ["REQ_LAND", "LAND_VALIDITY"],
        ),
        (
            "FACULTY_DEGREE_CERTIFICATE",
            "Faculty degree certificate",
            "Degree certificate supporting faculty eligibility.",
            True,
            ["FACULTY_DEGREE_CERTIFICATE"],
            ["REQ_FACULTY", "FACULTY_QUALIFICATION"],
        ),
        (
            "INSTITUTIONAL_UNDERTAKING",
            "Institutional undertaking",
            "Signed undertaking covering the declarations required for the application.",
            True,
            ["INSTITUTIONAL_UNDERTAKING"],
            ["REQ_UNDERTAKING", "UNDERTAKING_SIGNATURE"],
        ),
        (
            "ACCREDITATION_EVIDENCE",
            "Accreditation evidence (optional)",
            "Accreditation or programme approval evidence, where applicable.",
            False,
            ["OTHER"],
            ["ACCREDITATION_STATUS"],
        ),
        (
            "TER_PAYMENT_PROOF",
            "TER payment proof (optional)",
            "Evidence of the applicable TER payment.",
            False,
            ["OTHER"],
            ["TER_PAYMENT"],
        ),
    ]
    for order, (code, title, description, required, accepted, rules) in enumerate(items):
        template.items.append(
            ChecklistTemplateItem(
                code=code,
                title=title,
                description=description,
                required=required,
                accepted_document_types=accepted,
                rule_codes=rules,
                sort_order=order,
                record_requirement={"record_type": "accreditations"}
                if code == "ACCREDITATION_EVIDENCE"
                else {"record_type": "ter"}
                if code == "TER_PAYMENT_PROOF"
                else None,
            )
        )
    db.add(template)
    db.flush()
    return template


def _seed_demo_issuer(db: Session) -> IssuerKey:
    from app.services.issuers import get_or_create_demo_issuer

    key = get_or_create_demo_issuer(db)
    return key


EOA_RULE_SET_CODE = "EOA-SYNTHETIC-RULES"


def _eoa_rule_definitions() -> list[dict]:
    """Rule definitions for the synthetic EoA rule set.

    Kept as data so the seed can detect an older version (fewer rules) and
    publish a new active version instead of mutating a rule set that historical
    validation runs still reference.
    """

    return [
        dict(
            code="CHECKLIST_REQUIRED",
            title="Required checklist evidence",
            description="Every required checklist item must have accepted evidence or an authorised waiver.",
            rule_type=RuleType.CHECKLIST_COMPLETENESS,
            severity=RuleSeverity.BLOCKING,
            config={"accepted_statuses": ["SATISFIED", "WAIVED"]},
            required=True,
            sort_order=1,
            source_citation="Synthetic checklist policy.",
        ),
        dict(
            code="DOCUMENT_TEXT_EXTRACTED",
            title="Document text extraction quality",
            description="Current documents should be machine-readable with sufficient confidence for automated checks.",
            rule_type=RuleType.DOCUMENT_EXTRACTION,
            severity=RuleSeverity.ADVISORY,
            config={"min_confidence": 0.45},
            required=True,
            sort_order=2,
            source_citation="Synthetic extraction quality policy.",
        ),
        dict(
            code="AFFILIATION_VALIDITY",
            title="Affiliation certificate validity",
            description="The affiliation certificate's extracted validity date must not be expired.",
            rule_type=RuleType.DATE_VALIDITY,
            severity=RuleSeverity.BLOCKING,
            config={"document_type": "AFFILIATION_CERTIFICATE", "date_field": "valid_until"},
            required=True,
            sort_order=3,
            source_citation="Synthetic EoA document validity policy.",
        ),
        dict(
            code="INSTITUTION_NAME_CONSISTENCY",
            title="Institution name consistency",
            description="Extracted institution names are compared with the institution profile.",
            rule_type=RuleType.FIELD_CONSISTENCY,
            severity=RuleSeverity.ADVISORY,
            config={
                "field": "institution_name",
                "document_types": ["AFFILIATION_CERTIFICATE", "INSTITUTIONAL_UNDERTAKING", "LAND_LEASE_DOCUMENT"],
            },
            required=True,
            sort_order=4,
            source_citation="Synthetic data consistency policy.",
        ),
        dict(
            code="PREVIOUS_APPROVAL_STATUS",
            title="Previous approval status",
            description="The latest synthetic approval record should be in an accepted status.",
            rule_type=RuleType.INSTITUTION_RECORD,
            severity=RuleSeverity.ADVISORY,
            config={"record_type": "approvals", "statuses": ["APPROVED", "ACTIVE"]},
            required=True,
            sort_order=5,
            source_citation="Synthetic institutional record policy.",
        ),
        dict(
            code="TER_PAYMENT_STATUS",
            title="TER payment status",
            description="The latest synthetic TER record should show the configured accepted status.",
            rule_type=RuleType.INSTITUTION_RECORD,
            severity=RuleSeverity.ADVISORY,
            config={"record_type": "ter", "statuses": ["PAID"]},
            required=True,
            sort_order=6,
            source_citation="Synthetic TER record policy.",
        ),
        dict(
            code="ACCREDITATION_VALIDITY",
            title="Accreditation validity",
            description="Synthetic accreditation records should be active and not expired.",
            rule_type=RuleType.INSTITUTION_RECORD,
            severity=RuleSeverity.ADVISORY,
            config={"record_type": "accreditations"},
            required=True,
            sort_order=7,
            source_citation="Synthetic accreditation record policy.",
        ),
        dict(
            code="OPEN_DEFICIENCIES",
            title="Open compliance deficiencies",
            description="Open synthetic compliance deficiencies require human review.",
            rule_type=RuleType.INSTITUTION_RECORD,
            severity=RuleSeverity.ADVISORY,
            config={"record_type": "deficiencies", "blocking_statuses": ["OPEN", "UNRESOLVED"]},
            required=True,
            sort_order=8,
            source_citation="Synthetic compliance record policy.",
        ),
        dict(
            code="FACULTY_APPROVED_MINIMUM",
            title="Approved faculty minimum",
            description="The count of synthetic approved faculty records is compared with a configurable minimum.",
            rule_type=RuleType.INSTITUTION_RECORD,
            severity=RuleSeverity.ADVISORY,
            config={"record_type": "faculty", "minimum": 2, "statuses": ["APPROVED"]},
            required=True,
            sort_order=9,
            source_citation="Synthetic faculty record policy; threshold is configurable and not an official AICTE rule.",
        ),
        dict(
            code="AFFILIATION_DECLARATION_MATCH",
            title="Declared affiliation matches the certificate",
            description=(
                "The affiliation number and validity date declared by the applicant are compared with "
                "the values extracted from the affiliation certificate."
            ),
            rule_type=RuleType.FIELD_CONSISTENCY,
            severity=RuleSeverity.ADVISORY,
            config={
                "document_type": "AFFILIATION_CERTIFICATE",
                "fields": ["affiliation_number", "valid_until"],
            },
            required=True,
            sort_order=10,
            source_citation="Synthetic three-way consistency policy; advisory only.",
        ),
        dict(
            code="PROGRAMME_DECLARATION_MATCH",
            title="Declared programmes match the synthetic record",
            description=(
                "Declared programme codes, per-programme intake, and total intake are compared with the "
                "synthetic programme records and with each other."
            ),
            rule_type=RuleType.INSTITUTION_RECORD,
            severity=RuleSeverity.ADVISORY,
            config={"record_type": "programmes", "compare_intake": True},
            required=True,
            sort_order=11,
            source_citation="Synthetic programme record policy; advisory only.",
        ),
        dict(
            code="FACULTY_COUNT_DECLARATION_MATCH",
            title="Declared faculty count matches the synthetic record",
            description=(
                "The faculty count declared by the applicant is compared with the number of synthetic "
                "faculty records, within a configurable tolerance."
            ),
            rule_type=RuleType.INSTITUTION_RECORD,
            severity=RuleSeverity.ADVISORY,
            config={"record_type": "faculty", "tolerance": 0},
            required=True,
            sort_order=12,
            source_citation="Synthetic faculty record policy; advisory only.",
        ),
    ]


def _seed_rules(db: Session, category: ApplicationCategory, admin: User) -> RuleSet:
    definitions = _eoa_rule_definitions()
    existing = list(
        db.scalars(
            select(RuleSet).where(RuleSet.code == EOA_RULE_SET_CODE).order_by(RuleSet.version)
        )
    )
    current = next(
        (item for item in reversed(existing) if len(item.rules) == len(definitions)), None
    )
    if current is not None:
        return current
    # An older rule set has fewer rules: archive it (never mutate in place) and
    # publish a new active version so historical validation runs stay readable.
    for item in existing:
        if item.status is RuleSetStatus.ACTIVE:
            item.status = RuleSetStatus.ARCHIVED
    version = max((item.version for item in existing), default=0) + 1
    rule_set = RuleSet(
        code=EOA_RULE_SET_CODE,
        name="Synthetic EoA validation rules",
        category_id=category.id,
        version=version,
        status=RuleSetStatus.ACTIVE,
        effective_from=date(2026, 1, 1),
        source_citation="Synthetic demonstration rules; replace configurations with the applicable AICTE Approval Process Handbook clauses.",
        synthetic=True,
        created_by=admin.id,
        activated_at=datetime.now(timezone.utc),
    )
    rule_set.rules = [Rule(**definition) for definition in definitions]
    db.add(rule_set)
    db.flush()
    return rule_set


def _seed_records(db: Session, institution: Institution) -> None:
    existing = db.scalar(
        select(ApprovalHistory.id).where(ApprovalHistory.institution_id == institution.id).limit(1)
    )
    if existing:
        return
    now = datetime.now(timezone.utc)
    common = {"source": SYNTHETIC_SOURCE, "synthetic": True, "retrieved_at": now}
    db.add_all(
        [
            ApprovalHistory(
                institution_id=institution.id,
                application_reference="APP-2025-000421",
                cycle="2025-26",
                approval_type="EOA",
                status="APPROVED",
                valid_from=date(2025, 7, 1),
                valid_until=date(2026, 6, 30),
                programmes_summary={"approved_intake": 360, "programmes": 3},
                **common,
            ),
            Programme(
                institution_id=institution.id,
                code="CSE",
                name="B.Tech Computer Science and Engineering",
                level="UG",
                intake=120,
                accreditation_status="ACCREDITED",
                valid_until=date(2027, 6, 30),
                **common,
            ),
            Programme(
                institution_id=institution.id,
                code="ECE",
                name="B.Tech Electronics and Communication Engineering",
                level="UG",
                intake=60,
                accreditation_status="ACCREDITED",
                valid_until=date(2027, 6, 30),
                **common,
            ),
            FacultyRecord(
                institution_id=institution.id,
                faculty_ref="FAC-001",
                full_name="Dr. A. Sharma",
                designation="Professor",
                qualification="Ph.D. (Computer Science)",
                experience_months=144,
                programme_code="CSE",
                approved_status="APPROVED",
                **common,
            ),
            FacultyRecord(
                institution_id=institution.id,
                faculty_ref="FAC-002",
                full_name="Dr. R. Iyer",
                designation="Associate Professor",
                qualification="Ph.D. (Electronics)",
                experience_months=96,
                programme_code="ECE",
                approved_status="APPROVED",
                **common,
            ),
            ComplianceDeficiency(
                institution_id=institution.id,
                code="DEF-2025-03",
                description="Fire-safety certificate renewal was pending at the previous review.",
                severity="MEDIUM",
                status="RESOLVED",
                cycle="2025-26",
                resolved_at=now,
                **common,
            ),
            TerPayment(
                institution_id=institution.id,
                cycle="2025-26",
                reference="TER-2025-8891",
                amount=Decimal("125000.00"),
                currency="INR",
                status="PAID",
                paid_at=now,
                **common,
            ),
            AccreditationRecord(
                institution_id=institution.id,
                body="NBA",
                grade="A",
                reference="NBA/2025/0091",
                valid_until=date(2027, 6, 30),
                status="ACTIVE",
                **common,
            ),
            NocPermission(
                institution_id=institution.id,
                authority="State Government",
                reference="NOC/2024/778",
                valid_until=date(2028, 3, 31),
                status="ACTIVE",
                **common,
            ),
        ]
    )


def seed() -> None:
    db = SessionLocal()
    try:
        institution_a = _get_or_create_institution(
            db,
            legal_name="Sunrise Institute of Technology (Synthetic)",
            short_name="SIT",
            aicte_permanent_id="SYN-1-1000001",
            institute_type="Private unaided",
            address={"line1": "Sector 21", "city": "Pune", "postal_code": "411001"},
            state="Maharashtra",
            status="ACTIVE",
            synthetic=True,
        )
        institution_b = _get_or_create_institution(
            db,
            legal_name="Greenfield College of Engineering (Synthetic)",
            short_name="GCE",
            aicte_permanent_id="SYN-1-1000002",
            institute_type="Private unaided",
            address={"line1": "College Road", "city": "Nashik", "postal_code": "422001"},
            state="Maharashtra",
            status="ACTIVE",
            synthetic=True,
        )
        admin = _upsert_user(
            db, email="admin@example.test", full_name="Demo Administrator", role=Role.ADMIN, institution_id=None
        )
        _upsert_user(
            db, email="reviewer@example.test", full_name="Demo Reviewer", role=Role.REVIEWER, institution_id=None
        )
        _upsert_user(
            db, email="approver@example.test", full_name="Demo Approver", role=Role.APPROVER, institution_id=None
        )
        _upsert_user(
            db, email="auditor@example.test", full_name="Demo Auditor", role=Role.AUDITOR, institution_id=None
        )
        _upsert_user(
            db,
            email="applicant@example.test",
            full_name="Demo Applicant",
            role=Role.APPLICANT,
            institution_id=institution_a.id,
        )
        _upsert_user(
            db,
            email="applicant2@example.test",
            full_name="Second Institution Applicant",
            role=Role.APPLICANT,
            institution_id=institution_b.id,
        )
        category = db.scalar(select(ApplicationCategory).where(ApplicationCategory.code == "EOA"))
        if category is None:
            category = ApplicationCategory(
                code="EOA",
                name="Extension of Approval",
                description="Synthetic MVP category for AICTE Extension of Approval workflows.",
                active=True,
            )
            db.add(category)
            db.flush()
        _seed_checklist(db, category, admin)
        _seed_rules(db, category, admin)
        _seed_demo_issuer(db)
        _seed_records(db, institution_a)
        _seed_records(db, institution_b)
        db.commit()
        if settings.STORAGE_BACKEND.lower() == "s3":
            from app.services.object_store import get_object_store

            store = get_object_store()
            if hasattr(store, "ensure_bucket"):
                store.ensure_bucket()
        print("Seed complete. Demo accounts (development only):")
        for email in (
            "admin@example.test",
            "reviewer@example.test",
            "approver@example.test",
            "auditor@example.test",
            "applicant@example.test",
            "applicant2@example.test",
        ):
            print(f"  {email} / {_password()}")
        print("All seeded institution records are synthetic and must not be treated as official AICTE data.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic AstraVerify Phase 3 data.")
    parser.add_argument(
        "--create-schema",
        action="store_true",
        help="Create tables directly (development only; use Alembic in shared environments).",
    )
    args = parser.parse_args()
    if args.create_schema:
        Base.metadata.create_all(engine)
    seed()


if __name__ == "__main__":
    main()
