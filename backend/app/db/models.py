from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.db.enums import (
    AlertStatus,
    AlertType,
    AnomalySeverity,
    ApplicationStatus,
    AuditActorType,
    ChecklistItemStatus,
    ChecklistTemplateStatus,
    CredentialStatus,
    DecisionType,
    DocumentStatus,
    DocumentType,
    ExtractionStatus,
    InfrastructureEvidenceType,
    IssuerVerificationStatus,
    ReviewActionType,
    Role,
    RuleOutcome,
    RuleSeverity,
    RuleSetStatus,
    RuleType,
    ValidationStatus,
    ZkChainStatus,
    ZkProofStatus,
)


def enum_type(enum_cls: type, name: str) -> sa.Enum:
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


role_enum = enum_type(Role, "role")
application_status_enum = enum_type(ApplicationStatus, "application_status")
checklist_item_status_enum = enum_type(ChecklistItemStatus, "checklist_item_status")
checklist_template_status_enum = enum_type(ChecklistTemplateStatus, "checklist_template_status")
document_status_enum = enum_type(DocumentStatus, "document_status")
document_type_enum = enum_type(DocumentType, "document_type")
extraction_status_enum = enum_type(ExtractionStatus, "extraction_status")
rule_set_status_enum = enum_type(RuleSetStatus, "rule_set_status")
rule_type_enum = enum_type(RuleType, "rule_type")
rule_severity_enum = enum_type(RuleSeverity, "rule_severity")
rule_outcome_enum = enum_type(RuleOutcome, "rule_outcome")
validation_status_enum = enum_type(ValidationStatus, "validation_status")
credential_status_enum = enum_type(CredentialStatus, "credential_status")
issuer_verification_status_enum = enum_type(IssuerVerificationStatus, "issuer_verification_status")
anomaly_severity_enum = enum_type(AnomalySeverity, "anomaly_severity")
infrastructure_evidence_type_enum = enum_type(InfrastructureEvidenceType, "infrastructure_evidence_type")
review_action_type_enum = enum_type(ReviewActionType, "review_action_type")
decision_type_enum = enum_type(DecisionType, "decision_type")
alert_type_enum = enum_type(AlertType, "alert_type")
alert_status_enum = enum_type(AlertStatus, "alert_status")
audit_actor_type_enum = enum_type(AuditActorType, "audit_actor_type")
zk_proof_status_enum = enum_type(ZkProofStatus, "zk_proof_status")
zk_chain_status_enum = enum_type(ZkChainStatus, "zk_chain_status")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sa.func.now(),
    )


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    short_name: Mapped[str | None] = mapped_column(Text)
    aicte_permanent_id: Mapped[str | None] = mapped_column(Text, unique=True)
    institute_type: Mapped[str | None] = mapped_column(Text)
    address: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    state: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    users: Mapped[list["User"]] = relationship(back_populates="institution")
    applications: Mapped[list["Application"]] = relationship(back_populates="institution")

    __table_args__ = (
        Index("ix_institutions_legal_name", "legal_name"),
        Index("ix_institutions_state", "state"),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[Role] = mapped_column(role_enum, nullable=False)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="SET NULL")
    )
    wallet_did: Mapped[str | None] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    institution: Mapped[Institution | None] = relationship(back_populates="users")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user")

    __table_args__ = (
        Index("ix_users_institution_id", "institution_id"),
        Index("ix_users_role_is_active", "role", "is_active"),
        CheckConstraint(
            "(role = 'APPLICANT' AND institution_id IS NOT NULL) OR "
            "(role <> 'APPLICANT' AND institution_id IS NULL)",
            name="applicant_institution_scope",
        ),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    jti: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_jti: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_user_expires", "user_id", "expires_at"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )


class ApplicationCategory(Base):
    __tablename__ = "application_categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    templates: Mapped[list["ChecklistTemplate"]] = relationship(back_populates="category")


class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("application_categories.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ChecklistTemplateStatus] = mapped_column(
        checklist_template_status_enum, nullable=False, default=ChecklistTemplateStatus.DRAFT
    )
    effective_from: Mapped[date | None] = mapped_column(Date)
    source_citation: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    category: Mapped[ApplicationCategory] = relationship(back_populates="templates")
    items: Mapped[list["ChecklistTemplateItem"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="ChecklistTemplateItem.sort_order"
    )

    __table_args__ = (
        UniqueConstraint("category_id", "version", name="uq_checklist_templates_category_version"),
        Index("ix_checklist_templates_category_status", "category_id", "status"),
    )


class ChecklistTemplateItem(Base):
    __tablename__ = "checklist_template_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    accepted_document_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    record_requirement: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rule_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template: Mapped[ChecklistTemplate] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("template_id", "code", name="uq_checklist_template_items_template_code"),
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reference_no: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("application_categories.id", ondelete="RESTRICT"), nullable=False
    )
    checklist_template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("checklist_templates.id", ondelete="RESTRICT"), nullable=False
    )
    cycle: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(
        application_status_enum, nullable=False, default=ApplicationStatus.DRAFT
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sa.func.now(),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    institution: Mapped[Institution] = relationship(back_populates="applications")
    category: Mapped[ApplicationCategory] = relationship()
    checklist_template: Mapped[ChecklistTemplate] = relationship()
    checklist_items: Mapped[list["ApplicationChecklistItem"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationChecklistItem.sort_order",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.created_at",
    )
    created_by_user: Mapped[User] = relationship(foreign_keys=[created_by])
    assigned_reviewer: Mapped[User | None] = relationship(foreign_keys=[assigned_reviewer_id])

    __table_args__ = (
        CheckConstraint(
            "status = 'DRAFT' OR submitted_at IS NOT NULL",
            name="submitted_at_required",
        ),
        Index("ix_applications_institution_status", "institution_id", "status"),
        Index("ix_applications_assigned_reviewer_status", "assigned_reviewer_id", "status"),
        Index("ix_applications_cycle", "cycle"),
        Index("ix_applications_status_submitted_at", "status", "submitted_at"),
    )


class ApplicationChecklistItem(Base):
    __tablename__ = "application_checklist_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    template_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("checklist_template_items.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    accepted_document_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    rule_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ChecklistItemStatus] = mapped_column(
        checklist_item_status_enum, nullable=False, default=ChecklistItemStatus.PENDING
    )
    justification: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL", use_alter=True)
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sa.func.now(),
    )

    application: Mapped[Application] = relationship(back_populates="checklist_items")
    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id])

    __table_args__ = (
        UniqueConstraint("application_id", "code", name="uq_application_checklist_items_app_code"),
        CheckConstraint(
            "status <> 'WAIVED' OR (justification IS NOT NULL AND length(trim(justification)) > 0)",
            name="waived_requires_justification",
        ),
        Index("ix_application_checklist_items_application", "application_id"),
    )


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(application_status_enum)
    to_status: Mapped[ApplicationStatus] = mapped_column(application_status_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    application: Mapped[Application] = relationship(back_populates="status_history")

    __table_args__ = (Index("ix_application_status_history_application", "application_id"),)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[DocumentType] = mapped_column(document_type_enum, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        document_status_enum, nullable=False, default=DocumentStatus.STORED
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_documents_current_version_id_document_versions",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sa.func.now(),
    )

    application: Mapped[Application] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentVersion.document_id",
        order_by="DocumentVersion.version_no",
    )
    current_version: Mapped["DocumentVersion | None"] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )

    __table_args__ = (
        Index("ix_documents_application_type", "application_id", "document_type"),
        Index("ix_documents_status", "status"),
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    document: Mapped[Document] = relationship(back_populates="versions", foreign_keys=[document_id])

    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_document_versions_document_version"),
        UniqueConstraint("document_id", "sha256", name="uq_document_versions_document_sha256"),
        CheckConstraint("size_bytes <= 104857600", name="size_bytes_limit"),
        Index("ix_document_versions_sha256", "sha256"),
    )


class ReferenceCounter(Base):
    __tablename__ = "reference_counters"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ApprovalHistory(Base):
    __tablename__ = "approval_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    application_reference: Mapped[str | None] = mapped_column(Text)
    cycle: Mapped[str] = mapped_column(Text, nullable=False)
    approval_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    programmes_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_approval_history_institution_cycle", "institution_id", "cycle"),)


class Programme(Base):
    __tablename__ = "programmes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str | None] = mapped_column(Text)
    intake: Mapped[int | None] = mapped_column(Integer)
    accreditation_status: Mapped[str | None] = mapped_column(Text)
    valid_until: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_programmes_institution", "institution_id"),)


class FacultyRecord(Base):
    __tablename__ = "faculty_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    faculty_ref: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    designation: Mapped[str | None] = mapped_column(Text)
    qualification: Mapped[str | None] = mapped_column(Text)
    experience_months: Mapped[int | None] = mapped_column(Integer)
    programme_code: Mapped[str | None] = mapped_column(Text)
    approved_status: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_faculty_records_institution", "institution_id"),)


class ComplianceDeficiency(Base):
    __tablename__ = "compliance_deficiencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    cycle: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_compliance_deficiencies_institution_cycle", "institution_id", "cycle"),)


class TerPayment(Base):
    __tablename__ = "ter_payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    cycle: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_ter_payments_institution_cycle", "institution_id", "cycle"),)


class AccreditationRecord(Base):
    __tablename__ = "accreditation_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    grade: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_accreditation_records_institution", "institution_id"),)


class NocPermission(Base):
    __tablename__ = "nocs_permissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    authority: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_nocs_permissions_institution", "institution_id"),)



class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    document_type: Mapped[DocumentType | None] = mapped_column(document_type_enum)
    classification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[ExtractionStatus] = mapped_column(extraction_status_enum, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="extraction", cascade="all, delete-orphan", order_by="ExtractedField.created_at"
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(Text, nullable=False, default="TEXT")
    page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    extractor: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    extraction: Mapped[Extraction] = relationship(back_populates="fields")

    __table_args__ = (
        Index("ix_extracted_fields_extraction_name", "extraction_id", "name"),
        Index("ix_extracted_fields_normalized_value", "normalized_value"),
    )



class RuleSet(Base):
    __tablename__ = "rule_sets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("application_categories.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RuleSetStatus] = mapped_column(rule_set_status_enum, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    source_citation: Mapped[str | None] = mapped_column(Text)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rules: Mapped[list["Rule"]] = relationship(
        back_populates="rule_set", cascade="all, delete-orphan", order_by="Rule.sort_order"
    )

    __table_args__ = (UniqueConstraint("code", "version", name="uq_rule_sets_code_version"),)


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rule_type: Mapped[RuleType] = mapped_column(rule_type_enum, nullable=False)
    severity: Mapped[RuleSeverity] = mapped_column(rule_severity_enum, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_citation: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    rule_set: Mapped[RuleSet] = relationship(back_populates="rules")

    __table_args__ = (UniqueConstraint("rule_set_id", "code", name="uq_rules_set_code"),)


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rule_sets.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ValidationStatus] = mapped_column(validation_status_enum, nullable=False)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="validation_run", cascade="all, delete-orphan", order_by="Finding.created_at"
    )

    __table_args__ = (Index("ix_validation_runs_application_created", "application_id", "created_at"),)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("rules.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[RuleOutcome] = mapped_column(rule_outcome_enum, nullable=False)
    severity: Mapped[RuleSeverity] = mapped_column(rule_severity_enum, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    validation_run: Mapped[ValidationRun] = relationship(back_populates="findings")
    evidence: Mapped[list["FindingEvidence"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", order_by="FindingEvidence.created_at"
    )

    __table_args__ = (Index("ix_findings_run_code", "validation_run_id", "code"),)


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    finding: Mapped[Finding] = relationship(back_populates="evidence")


class RecordSnapshot(Base):
    __tablename__ = "record_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    record_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (
        UniqueConstraint("validation_run_id", "record_type", name="uq_record_snapshots_run_type"),
    )



class IssuerKey(Base):
    __tablename__ = "issuer_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    issuer_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    issuer_name: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm: Mapped[str] = mapped_column(Text, nullable=False, default="Ed25519")
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_pem: Mapped[str | None] = mapped_column(Text)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )


class IssuedCredential(Base):
    __tablename__ = "issued_credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    credential_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    issuer_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("issuer_keys.id", ondelete="RESTRICT"), nullable=False
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    subject_reference: Mapped[str | None] = mapped_column(Text)
    claims: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CredentialStatus] = mapped_column(credential_status_enum, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    issuer_key: Mapped[IssuerKey] = relationship()


class IssuerVerification(Base):
    __tablename__ = "issuer_verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    issuer_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("issued_credentials.id", ondelete="SET NULL")
    )
    adapter_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IssuerVerificationStatus] = mapped_column(
        issuer_verification_status_enum, nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    simulated_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (Index("ix_issuer_verifications_version_created", "document_version_id", "created_at"),)



class AnomalySignal(Base):
    __tablename__ = "anomaly_signals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    signal_code: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[AnomalySeverity] = mapped_column(anomaly_severity_enum, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    advisory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (Index("ix_anomaly_signals_application_created", "application_id", "created_at"),)


class InfrastructureEvidence(Base):
    __tablename__ = "infrastructure_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[InfrastructureEvidenceType] = mapped_column(
        infrastructure_evidence_type_enum, nullable=False
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (Index("ix_infrastructure_evidence_application", "application_id", "evidence_type"),)



class ReviewAction(Base):
    __tablename__ = "review_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    action_type: Mapped[ReviewActionType] = mapped_column(review_action_type_enum, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    from_status: Mapped[ApplicationStatus | None] = mapped_column(application_status_enum)
    to_status: Mapped[ApplicationStatus | None] = mapped_column(application_status_enum)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (Index("ix_review_actions_application_created", "application_id", "created_at"),)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    decision_type: Mapped[DecisionType] = mapped_column(decision_type_enum, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (Index("ix_decisions_application", "application_id", "decided_at"),)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    alert_type: Mapped[AlertType] = mapped_column(alert_type_enum, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(alert_status_enum, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (
        UniqueConstraint("application_id", "alert_type", "source_ref", name="uq_alerts_app_type_source"),
        Index("ix_alerts_application_status", "application_id", "status"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[AuditActorType] = mapped_column(audit_actor_type_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="SET NULL")
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    __table_args__ = (Index("ix_audit_events_application_created", "application_id", "created_at"),)


class ZkProof(Base):
    __tablename__ = "zk_proofs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    circuit_name: Mapped[str] = mapped_column(Text, nullable=False, default="faculty_threshold")
    circuit_version: Mapped[str] = mapped_column(Text, nullable=False, default="2.0.0")
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    commitment: Mapped[str] = mapped_column(Text, nullable=False)
    nullifier: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    threshold: Mapped[str] = mapped_column(Text, nullable=False)
    public_signals: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    proof_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[ZkProofStatus] = mapped_column(zk_proof_status_enum, nullable=False)
    vkey_hash: Mapped[str] = mapped_column(Text, nullable=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    chain_status: Mapped[ZkChainStatus] = mapped_column(
        zk_chain_status_enum, nullable=False, default=ZkChainStatus.NOT_REQUESTED
    )
    chain_tx_hash: Mapped[str | None] = mapped_column(Text)
    chain_network: Mapped[str | None] = mapped_column(Text)
    anchored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    application: Mapped["Application"] = relationship()
    document_version: Mapped["DocumentVersion"] = relationship()
    verifier_user: Mapped["User"] = relationship()



class ZkChallenge(Base):
    __tablename__ = "zk_challenges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[str] = mapped_column(Text, nullable=False)
    circuit_name: Mapped[str] = mapped_column(Text, nullable=False, default="faculty_threshold")
    circuit_version: Mapped[str] = mapped_column(Text, nullable=False, default="2.0.0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sa.func.now()
    )

    application: Mapped["Application"] = relationship()
    creator: Mapped["User"] = relationship()
