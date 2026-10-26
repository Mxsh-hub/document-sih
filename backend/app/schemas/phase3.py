from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import (
    AlertStatus,
    AlertType,
    AnomalySeverity,
    ApplicationStatus,
    ChecklistItemStatus,
    AuditActorType,
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
)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Authentication ---------------------------------------------------------


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=512)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    institution_id: uuid.UUID | None = None
    wallet_did: str | None = None


class MeOut(BaseModel):
    user: UserOut
    scopes: list[str]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    user: UserOut


# --- Institutions -----------------------------------------------------------


class InstitutionSummary(ApiModel):
    id: uuid.UUID
    legal_name: str
    short_name: str | None = None
    aicte_permanent_id: str | None = None
    state: str | None = None
    status: str
    synthetic: bool


class InstitutionOut(InstitutionSummary):
    institute_type: str | None = None
    address: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class InstitutionCreate(BaseModel):
    legal_name: str = Field(min_length=2, max_length=300)
    short_name: str | None = Field(default=None, max_length=100)
    aicte_permanent_id: str | None = Field(default=None, max_length=100)
    institute_type: str | None = Field(default=None, max_length=100)
    address: dict[str, Any] | None = None
    state: str | None = Field(default=None, max_length=100)
    synthetic: bool = True


class InstitutionPatch(BaseModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=300)
    short_name: str | None = Field(default=None, max_length=100)
    institute_type: str | None = Field(default=None, max_length=100)
    address: dict[str, Any] | None = None
    state: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=30)


# --- Administration ---------------------------------------------------------


class AdminUserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    full_name: str = Field(min_length=2, max_length=200)
    role: Role
    institution_id: uuid.UUID | None = None
    wallet_did: str | None = Field(default=None, max_length=300)
    password: str = Field(min_length=12, max_length=256)


class AdminUserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: Role | None = None
    institution_id: uuid.UUID | None = None
    is_active: bool | None = None


class CategoryCreate(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CategoryOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    active: bool


class ChecklistTemplateItemCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_]+$")
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    required: bool = True
    accepted_document_types: list[DocumentType] = Field(default_factory=list)
    record_requirement: dict[str, Any] | None = None
    rule_codes: list[str] = Field(default_factory=list)
    sort_order: int = 0


class ChecklistTemplateCreate(BaseModel):
    category_id: uuid.UUID
    version: int = Field(ge=1)
    effective_from: date | None = None
    source_citation: str | None = Field(default=None, max_length=1000)
    items: list[ChecklistTemplateItemCreate] = Field(min_length=1)


class ChecklistTemplateItemOut(ApiModel):
    id: uuid.UUID
    code: str
    title: str
    description: str | None = None
    required: bool
    accepted_document_types: list[str]
    record_requirement: dict[str, Any] | None = None
    rule_codes: list[str]
    sort_order: int


class ChecklistTemplateOut(ApiModel):
    id: uuid.UUID
    category_id: uuid.UUID
    version: int
    status: ChecklistTemplateStatus
    effective_from: date | None = None
    source_citation: str | None = None
    items: list[ChecklistTemplateItemOut]


# --- Applications -----------------------------------------------------------


class ApplicationCreate(BaseModel):
    category_code: str = Field(min_length=2, max_length=30)
    cycle: str = Field(pattern=r"^\d{4}-\d{2}$")

    @field_validator("category_code")
    @classmethod
    def upper_category(cls, value: str) -> str:
        return value.upper()


class ApplicationPatch(BaseModel):
    cycle: str = Field(pattern=r"^\d{4}-\d{2}$")


class ChecklistCounts(BaseModel):
    total: int
    satisfied: int
    pending: int
    waived: int
    rejected: int


class ApplicationOut(ApiModel):
    id: uuid.UUID
    reference_no: str
    institution_id: uuid.UUID
    category_code: str
    cycle: str
    status: ApplicationStatus
    checklist_template_id: uuid.UUID
    version: int
    submitted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationDetailOut(ApplicationOut):
    institution: InstitutionSummary
    checklist: ChecklistCounts


# --- Structured declaration (declared vs extracted vs records) -------------


class DeclarationProgramme(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=200)
    level: str | None = Field(default=None, max_length=40)
    intake: int | None = Field(default=None, ge=0)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class DeclarationUpsert(BaseModel):
    affiliation_number: str | None = Field(default=None, max_length=100)
    affiliation_valid_until: date | None = None
    programmes: list[DeclarationProgramme] = Field(default_factory=list, max_length=50)
    total_intake: int | None = Field(default=None, ge=0)
    faculty_count: int | None = Field(default=None, ge=0)
    previous_approval_reference: str | None = Field(default=None, max_length=100)


class DeclarationOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    affiliation_number: str | None = None
    affiliation_valid_until: date | None = None
    programmes: list[dict[str, Any]] = Field(default_factory=list)
    total_intake: int | None = None
    faculty_count: int | None = None
    previous_approval_reference: str | None = None
    version: int
    declared_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class DeclarationEnvelope(BaseModel):
    """Returned when the applicant has not declared anything yet."""

    application_id: uuid.UUID
    declaration: DeclarationOut | None = None


class ApplicationPage(BaseModel):
    items: list[ApplicationOut]
    page: int
    page_size: int
    total: int


class ChecklistItemOut(ApiModel):
    id: uuid.UUID
    code: str
    title: str
    required: bool
    status: ChecklistItemStatus
    document_id: uuid.UUID | None = None
    justification: str | None = None
    accepted_document_types: list[str]
    rule_codes: list[str]
    sort_order: int


class ChecklistOut(BaseModel):
    application_id: uuid.UUID
    items: list[ChecklistItemOut]


class ChecklistItemPatch(BaseModel):
    justification: str | None = Field(default=None, max_length=2000)
    document_id: uuid.UUID | None = None
    status: ChecklistItemStatus | None = None


class WithdrawRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class StatusHistoryOut(ApiModel):
    id: uuid.UUID
    from_status: ApplicationStatus | None = None
    to_status: ApplicationStatus
    actor_id: uuid.UUID | None = None
    reason: str | None = None
    created_at: datetime


class SubmitResponse(BaseModel):
    application_id: uuid.UUID
    status: ApplicationStatus
    validation_run_id: uuid.UUID | None = None


# --- Documents --------------------------------------------------------------


class DocumentVersionOut(ApiModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_no: int
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int | None = None
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    synthetic: bool


class DocumentOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    document_type: DocumentType
    status: DocumentStatus
    current_version_id: uuid.UUID | None = None
    checklist_item_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    current_version: DocumentVersionOut | None = None


class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    version_no: int
    sha256: str
    status: DocumentStatus
    processing_job_id: uuid.UUID | None = None


class DocumentListOut(BaseModel):
    items: list[DocumentOut]


class DocumentVersionListOut(BaseModel):
    items: list[DocumentVersionOut]


class DownloadUrlOut(BaseModel):
    url: str
    expires_at: datetime


# --- Synthetic institutional records ---------------------------------------


class RecordItemsOut(BaseModel):
    source: str
    synthetic: bool
    retrieved_at: datetime | None = None
    items: list[dict[str, Any]]


class RecordBundleOut(BaseModel):
    institution_id: uuid.UUID
    source: str
    synthetic: bool
    retrieved_at: datetime | None = None
    records: dict[str, RecordItemsOut]


# --- Phase 4 extraction ------------------------------------------------------


class ExtractedFieldOut(ApiModel):
    id: uuid.UUID
    name: str
    raw_value: str | None = None
    normalized_value: str | None = None
    value_type: str
    page: int | None = None
    bbox: list[float] | None = None
    page_width: float | None = None
    page_height: float | None = None
    confidence: float | None = None
    extractor: str


class ExtractionOut(ApiModel):
    id: uuid.UUID
    document_version_id: uuid.UUID
    document_type: DocumentType | None = None
    classification_confidence: float | None = None
    status: ExtractionStatus
    confidence: float | None = None
    extractor_version: str
    page_count: int | None = None
    error_code: str | None = None
    error_detail: str | None = None
    completed_at: datetime | None = None
    fields: list[ExtractedFieldOut] = Field(default_factory=list)



# --- Phase 5 validation -----------------------------------------------------


class RuleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    rule_type: RuleType
    severity: RuleSeverity = RuleSeverity.ADVISORY
    config: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    source_citation: str | None = None
    sort_order: int = 0


class RulePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    severity: RuleSeverity | None = None
    config: dict[str, Any] | None = None
    required: bool | None = None
    source_citation: str | None = None
    sort_order: int | None = None


class RuleOut(ApiModel):
    id: uuid.UUID
    rule_set_id: uuid.UUID
    code: str
    title: str
    description: str | None = None
    rule_type: RuleType
    severity: RuleSeverity
    config: dict[str, Any]
    required: bool
    source_citation: str | None = None
    sort_order: int


class RuleSetCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=3, max_length=200)
    category_id: uuid.UUID
    version: int = Field(ge=1)
    effective_from: date | None = None
    source_citation: str | None = None
    rules: list[RuleCreate] = Field(default_factory=list)


class RuleSetOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    category_id: uuid.UUID
    version: int
    status: RuleSetStatus
    effective_from: date | None = None
    source_citation: str | None = None
    synthetic: bool
    activated_at: datetime | None = None
    rules: list[RuleOut] = Field(default_factory=list)


class FindingEvidenceOut(ApiModel):
    id: uuid.UUID
    evidence_type: str
    entity_id: uuid.UUID | None = None
    label: str
    metadata_json: dict[str, Any] | None = None


class FindingOut(ApiModel):
    id: uuid.UUID
    rule_id: uuid.UUID | None = None
    code: str
    title: str
    outcome: RuleOutcome
    severity: RuleSeverity
    message: str
    details: dict[str, Any] | None = None
    evidence: list[FindingEvidenceOut] = Field(default_factory=list)


class ValidationRunOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    rule_set_id: uuid.UUID
    status: ValidationStatus
    engine_version: str
    summary: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    findings: list[FindingOut] = Field(default_factory=list)



# --- Phase 6 issuer verification -------------------------------------------


class DemoCredentialIssue(BaseModel):
    document_version_id: uuid.UUID
    subject_reference: str | None = Field(default=None, max_length=200)
    claims: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


class DemoCredentialOut(ApiModel):
    id: uuid.UUID
    credential_id: str
    document_version_id: uuid.UUID | None = None
    document_sha256: str | None = None
    subject_reference: str | None = None
    claims: dict[str, Any]
    status: CredentialStatus
    synthetic: bool
    issued_at: datetime
    expires_at: datetime | None = None


class IssuerVerificationCreate(BaseModel):
    issuer_code: Literal["demo", "external"] = "demo"
    credential_id: str | None = Field(default=None, max_length=300)


class IssuerVerificationOut(ApiModel):
    id: uuid.UUID
    document_version_id: uuid.UUID
    issuer_credential_id: uuid.UUID | None = None
    adapter_code: str
    status: IssuerVerificationStatus
    message: str
    evidence: dict[str, Any] | None = None
    simulated_source: bool
    verified_by: uuid.UUID | None = None
    created_at: datetime



# --- Phase 7 anomaly and infrastructure ------------------------------------


class AnomalySignalOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    signal_code: str
    severity: AnomalySeverity
    score: float | None = None
    advisory: bool
    message: str
    evidence: dict[str, Any] | None = None
    source: str
    created_at: datetime


class InfrastructureEvidenceCreate(BaseModel):
    evidence_type: InfrastructureEvidenceType
    document_version_id: uuid.UUID | None = None
    label: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    captured_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InfrastructureEvidenceOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    evidence_type: InfrastructureEvidenceType
    document_version_id: uuid.UUID | None = None
    label: str
    description: str | None = None
    captured_at: datetime | None = None
    metadata_json: dict[str, Any] | None = None
    synthetic: bool
    created_at: datetime


class InfrastructureCheckOut(BaseModel):
    evidence_type: str
    status: str
    message: str
    evidence_ids: list[str]


class InfrastructureAssessmentOut(BaseModel):
    application_id: uuid.UUID
    required_types: list[str]
    checks: list[InfrastructureCheckOut]
    complete: bool
    synthetic: bool
    simulated: bool
    note: str
    assessed_at: datetime



# --- Phase 8 review, alerts, audit -----------------------------------------


class ReviewActionCreate(BaseModel):
    action_type: ReviewActionType
    note: str | None = Field(default=None, max_length=4000)
    assigned_user_id: uuid.UUID | None = None


class ReviewActionOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    action_type: ReviewActionType
    note: str | None = None
    from_status: ApplicationStatus | None = None
    to_status: ApplicationStatus | None = None
    created_at: datetime


class DecisionCreate(BaseModel):
    decision_type: DecisionType
    rationale: str = Field(min_length=10, max_length=5000)
    conditions: dict[str, Any] = Field(default_factory=dict)


class DecisionOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    decision_type: DecisionType
    rationale: str
    conditions: dict[str, Any] | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime


class AlertOut(ApiModel):
    id: uuid.UUID
    application_id: uuid.UUID
    alert_type: AlertType
    status: AlertStatus
    title: str
    message: str
    source_ref: str
    payload: dict[str, Any] | None = None
    disposition: str | None = None
    acknowledged_by: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime


AlertDispositionValue = Literal[
    "ADDRESSED",
    "FALSE_POSITIVE",
    "DUPLICATE",
    "SUPERSEDED",
    "ACCEPTED_RISK",
    "ESCALATED",
]


class AlertResolution(BaseModel):
    """Resolve an alert with an explicit human disposition.

    The disposition is stored in the alert payload so no schema migration is
    needed. Dismissive dispositions (``FALSE_POSITIVE``, ``ACCEPTED_RISK``) must
    carry a note so the reasoning survives with the audit record.
    """

    note: str | None = Field(default=None, max_length=2000)
    disposition: AlertDispositionValue = "ADDRESSED"


class SelfCheckCheck(BaseModel):
    code: str
    level: Literal["BLOCKING", "WARNING", "INFO", "OK"]
    title: str
    message: str
    remediation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SelfCheckOut(BaseModel):
    application_id: uuid.UUID
    reference_no: str
    status: ApplicationStatus
    check_version: str
    generated_at: datetime
    can_submit: bool
    counts: dict[str, int]
    checks: list[SelfCheckCheck]
    advisory_note: str


class AuditEventOut(ApiModel):
    id: uuid.UUID
    sequence: int
    event_type: str
    actor_type: AuditActorType
    actor_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    entity_type: str
    entity_id: uuid.UUID | None = None
    payload: dict[str, Any]
    previous_hash: str | None = None
    event_hash: str
    created_at: datetime
