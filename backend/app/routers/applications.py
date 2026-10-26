from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import ApplicationStatus, ChecklistItemStatus, Role
from app.db.models import Application, ApplicationChecklistItem, User
from app.schemas.phase3 import (
    ApplicationCreate,
    ApplicationDetailOut,
    ApplicationOut,
    ApplicationPage,
    ApplicationPatch,
    ChecklistCounts,
    ChecklistItemOut,
    ChecklistItemPatch,
    ChecklistOut,
    DeclarationEnvelope,
    DeclarationOut,
    DeclarationUpsert,
    InstitutionSummary,
    StatusHistoryOut,
    SelfCheckOut,
    SubmitResponse,
    WithdrawRequest,
)
from app.services import applications as application_service
from app.services import declarations as declaration_service
from app.services import self_check as self_check_service
from app.services.authorization import (
    get_application_or_404,
    get_checklist_item_or_404,
    require_editable_application,
)
from app.services.assurance import scan_anomalies
from app.services.audit import record_audit
from app.services.review import sync_alerts
from app.services.validation import run_validation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["Applications"])


def _application_out(application: Application) -> ApplicationOut:
    return ApplicationOut(
        id=application.id,
        reference_no=application.reference_no,
        institution_id=application.institution_id,
        category_code=application.category.code,
        cycle=application.cycle,
        status=application.status,
        checklist_template_id=application.checklist_template_id,
        version=application.version,
        submitted_at=application.submitted_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def _application_detail(application: Application) -> ApplicationDetailOut:
    base = _application_out(application)
    return ApplicationDetailOut(
        **base.model_dump(),
        institution=InstitutionSummary.model_validate(application.institution),
        checklist=ChecklistCounts(**application_service.checklist_counts(application)),
    )


def _checklist_item_out(item: ApplicationChecklistItem) -> ChecklistItemOut:
    return ChecklistItemOut(
        id=item.id,
        code=item.code,
        title=item.title,
        required=item.required,
        status=item.status,
        document_id=item.document_id,
        justification=item.justification,
        accepted_document_types=item.accepted_document_types or [],
        rule_codes=item.rule_codes or [],
        sort_order=item.sort_order,
    )


def _check_if_match(application: Application, if_match: str | None) -> None:
    if if_match is None:
        raise ApiError(400, "VALIDATION_FAILED", "If-Match header is required.")
    try:
        version = int(if_match.strip().strip('"'))
    except ValueError as exc:
        raise ApiError(400, "VALIDATION_FAILED", "If-Match must be an integer version.") from exc
    if version != application.version:
        raise ApiError(409, "VERSION_CONFLICT", "The application was modified by another request.")


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = application_service.create_application(db, user, payload.category_code, payload.cycle)
    return _application_out(application)


@router.get("", response_model=ApplicationPage)
def list_applications(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    application_status: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    cycle: str | None = None,
    institution_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = application_service.list_applications(
        db,
        user,
        status=application_status,
        cycle=cycle,
        institution_id=institution_id,
        assigned_to_me=assigned_to_me,
        q=q,
        page=page,
        page_size=page_size,
    )
    return ApplicationPage(
        items=[_application_out(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{application_id}", response_model=ApplicationDetailOut)
def get_application(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    return _application_detail(application)


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationPatch,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    application = get_application_or_404(db, application_id, user)
    _check_if_match(application, if_match)
    application = application_service.update_application(db, application, user, payload.cycle)
    return _application_out(application)


@router.post("/{application_id}/submit", response_model=SubmitResponse)
def submit_application(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    application = application_service.submit_application(db, application, user)
    validation_run_id = None
    try:
        validation_run_id = run_validation(db, application, actor=user).id
    except Exception:
        # Submission must not be lost because the advisory validation engine is unavailable.
        logger.exception("automatic validation failed application_id=%s", application.id)
    try:
        scan_anomalies(db, application)
    except Exception:
        logger.exception("automatic anomaly scan failed application_id=%s", application.id)
    try:
        sync_alerts(db, application)
    except Exception:
        logger.exception("alert generation failed application_id=%s", application.id)
    return SubmitResponse(
        application_id=application.id,
        status=application.status,
        validation_run_id=validation_run_id,
    )


@router.post("/{application_id}/withdraw", response_model=ApplicationOut)
def withdraw_application(
    application_id: uuid.UUID,
    payload: WithdrawRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    application = application_service.withdraw_application(db, application, user, payload.reason)
    return _application_out(application)


@router.get("/{application_id}/checklist", response_model=ChecklistOut)
def get_checklist(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    return ChecklistOut(
        application_id=application.id,
        items=[_checklist_item_out(item) for item in application.checklist_items],
    )


@router.get("/{application_id}/self-check", response_model=SelfCheckOut)
def get_self_check(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Preview whether submission would be accepted, without submitting.

    Read-only and side-effect free: no validation run, no alerts, no audit
    event. Blocking checks reuse the same helper that ``submit`` uses, so the
    preview cannot disagree with the real gate. Everything else is advisory and
    the response says so.
    """
    application = get_application_or_404(db, application_id, user)
    if application.status not in {
        ApplicationStatus.DRAFT,
        ApplicationStatus.RECTIFICATION_REQUESTED,
    }:
        raise ApiError(
            409,
            "STATE_CONFLICT",
            "The self-check is only available for a draft or an application under rectification.",
        )
    return SelfCheckOut(**self_check_service.build_self_check(db, application))


@router.patch("/{application_id}/checklist/{item_id}", response_model=ChecklistItemOut)
def update_checklist_item(
    application_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ChecklistItemPatch,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    item = get_checklist_item_or_404(db, application_id, item_id, user)
    if user.role in {Role.REVIEWER, Role.APPROVER}:
        if payload.status not in {ChecklistItemStatus.WAIVED, ChecklistItemStatus.REJECTED}:
            raise ApiError(403, "FORBIDDEN", "Reviewers may only waive or reject checklist items.")
        if not payload.justification or not payload.justification.strip():
            raise ApiError(400, "VALIDATION_FAILED", "A rationale is required.")
        if application.status is ApplicationStatus.DRAFT:
            raise ApiError(409, "STATE_CONFLICT", "A draft application is not under review.")
        item.status = payload.status
        item.justification = payload.justification.strip()
        db.commit()
        db.refresh(item)
        return _checklist_item_out(item)
    item = application_service.update_checklist_item(
        db,
        application,
        item,
        user,
        justification=payload.justification,
        document_id=payload.document_id,
    )
    return _checklist_item_out(item)


@router.get("/{application_id}/declaration", response_model=DeclarationEnvelope)
def get_declaration(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Return the applicant's declared facts, or null when none were saved.

    Any user who can view the application may read the declaration; only the
    applicant may change it, and only while the application is a draft.
    """

    application = get_application_or_404(db, application_id, user)
    declaration = declaration_service.get_declaration(db, application.id)
    return DeclarationEnvelope(
        application_id=application.id,
        declaration=DeclarationOut.model_validate(declaration) if declaration else None,
    )


@router.put("/{application_id}/declaration", response_model=DeclarationOut)
def put_declaration(
    application_id: uuid.UUID,
    payload: DeclarationUpsert,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    require_editable_application(application, user)
    declaration = declaration_service.upsert_declaration(db, application, user, payload)
    return DeclarationOut.model_validate(declaration)


@router.get("/{application_id}/status-history", response_model=list[StatusHistoryOut])
def get_status_history(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    return [StatusHistoryOut.model_validate(row) for row in application.status_history]


@router.get("/{application_id}/summary")
def get_summary(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    counts = application_service.checklist_counts(application)
    return {
        "application_id": str(application.id),
        "status": application.status.value,
        "checklist": counts,
        "findings": {"PASS": 0, "FAIL": 0, "INCONCLUSIVE": 0, "NOT_AVAILABLE": 0, "NOT_APPLICABLE": 0},
        "verifications": {
            "VERIFIED": 0,
            "MISMATCH": 0,
            "EXPIRED": 0,
            "PENDING": 0,
            "SOURCE_UNAVAILABLE": 0,
            "MANUAL_REVIEW": 0,
        },
        "anomalies": {"total": 0, "high": 0},
        "alerts": {"open": 0},
        "last_validation_run_id": None,
        "chain": {"pending": 0, "confirmed": 0, "failed": 0},
    }
