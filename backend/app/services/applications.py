from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.enums import (
    ApplicationStatus,
    ChecklistItemStatus,
    ChecklistTemplateStatus,
    DocumentStatus,
    Role,
)
from app.db.models import (
    Application,
    ApplicationCategory,
    ApplicationChecklistItem,
    ApplicationStatusHistory,
    ChecklistTemplate,
    Document,
    ReferenceCounter,
    User,
)
from app.services.audit import record_audit
from app.services.authorization import (
    application_scope_condition,
    require_application_owner,
    require_editable_application,
)

TERMINAL_STATUSES = {
    ApplicationStatus.APPROVED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
}


def _next_reference(db: Session, cycle: str) -> str:
    year = cycle.split("-")[0]
    counter_name = f"application:{year}"
    counter = db.scalar(
        select(ReferenceCounter).where(ReferenceCounter.name == counter_name).with_for_update()
    )
    if counter is None:
        counter = ReferenceCounter(name=counter_name, value=1)
        db.add(counter)
        db.flush()
    else:
        counter.value += 1
        db.flush()
    return f"APP-{year}-{counter.value:06d}"


def _transition(
    db: Session,
    application: Application,
    to_status: ApplicationStatus,
    actor: User,
    reason: str | None = None,
) -> None:
    history = ApplicationStatusHistory(
        application_id=application.id,
        from_status=application.status,
        to_status=to_status,
        actor_id=actor.id,
        reason=reason,
    )
    application.status = to_status
    db.add(history)


def _active_template(db: Session, category_id: uuid.UUID) -> ChecklistTemplate:
    template = db.scalar(
        select(ChecklistTemplate)
        .where(
            ChecklistTemplate.category_id == category_id,
            ChecklistTemplate.status == ChecklistTemplateStatus.ACTIVE,
        )
        .order_by(ChecklistTemplate.version.desc())
    )
    if not template:
        raise ApiError(409, "STATE_CONFLICT", "No active checklist template is configured for this category.")
    return template


def _duplicate_active_application(
    db: Session, institution_id: uuid.UUID, category_id: uuid.UUID, cycle: str
) -> Application | None:
    return db.scalar(
        select(Application).where(
            Application.institution_id == institution_id,
            Application.category_id == category_id,
            Application.cycle == cycle,
            Application.status.notin_(TERMINAL_STATUSES),
        )
    )


def create_application(db: Session, actor: User, category_code: str, cycle: str) -> Application:
    if actor.role is not Role.APPLICANT or actor.institution_id is None:
        raise ApiError(403, "FORBIDDEN", "Only an applicant with an institution may create an application.")
    category = db.scalar(
        select(ApplicationCategory).where(
            ApplicationCategory.code == category_code.upper(), ApplicationCategory.active.is_(True)
        )
    )
    if not category:
        raise ApiError(404, "NOT_FOUND", "Application category not found.")
    if _duplicate_active_application(db, actor.institution_id, category.id, cycle):
        raise ApiError(409, "STATE_CONFLICT", "An active application already exists for this category and cycle.")
    template = _active_template(db, category.id)

    application = Application(
        reference_no=_next_reference(db, cycle),
        institution_id=actor.institution_id,
        category_id=category.id,
        checklist_template_id=template.id,
        cycle=cycle,
        status=ApplicationStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(application)
    db.flush()

    for index, template_item in enumerate(template.items):
        db.add(
            ApplicationChecklistItem(
                application_id=application.id,
                template_item_id=template_item.id,
                code=template_item.code,
                title=template_item.title,
                required=template_item.required,
                accepted_document_types=template_item.accepted_document_types,
                rule_codes=template_item.rule_codes,
                status=ChecklistItemStatus.PENDING,
                sort_order=template_item.sort_order or index,
            )
        )
    db.add(
        ApplicationStatusHistory(
            application_id=application.id,
            from_status=None,
            to_status=ApplicationStatus.DRAFT,
            actor_id=actor.id,
            reason="Application created.",
        )
    )
    record_audit(
        db,
        event_type="application.created",
        actor=actor,
        application_id=application.id,
        entity_type="application",
        entity_id=application.id,
        payload={"reference_no": application.reference_no, "cycle": cycle, "category": category_code},
    )
    db.commit()
    db.refresh(application)
    return application


def update_application(db: Session, application: Application, actor: User, cycle: str) -> Application:
    require_editable_application(application, actor)
    if cycle != application.cycle:
        duplicate = _duplicate_active_application(db, application.institution_id, application.category_id, cycle)
        if duplicate and duplicate.id != application.id:
            raise ApiError(409, "STATE_CONFLICT", "An active application already exists for this category and cycle.")
        application.cycle = cycle
    application.version += 1
    db.commit()
    db.refresh(application)
    return application


def missing_required_items(db: Session, application: Application) -> list[str]:
    missing: list[str] = []
    for item in application.checklist_items:
        if not item.required:
            continue
        if item.status in {ChecklistItemStatus.WAIVED, ChecklistItemStatus.REJECTED}:
            continue
        if item.document_id:
            document = db.get(Document, item.document_id)
            if document and document.status not in {DocumentStatus.FAILED, DocumentStatus.QUARANTINED}:
                continue
        if item.justification and item.justification.strip():
            continue
        missing.append(item.code)
    return missing


def submit_application(db: Session, application: Application, actor: User) -> Application:
    require_application_owner(application, actor)
    if application.status not in {ApplicationStatus.DRAFT, ApplicationStatus.RECTIFICATION_REQUESTED}:
        raise ApiError(409, "STATE_CONFLICT", "Only a draft or rectification application may be submitted.")
    missing = missing_required_items(db, application)
    if missing:
        raise ApiError(
            400,
            "VALIDATION_FAILED",
            "Required checklist items are incomplete.",
            details=[{"field": "checklist", "issue": f"Missing evidence for {code}."} for code in missing],
        )
    target_status = (
        ApplicationStatus.RESUBMITTED
        if application.status is ApplicationStatus.RECTIFICATION_REQUESTED
        else ApplicationStatus.SUBMITTED
    )
    _transition(db, application, target_status, actor, "Application submitted.")
    application.submitted_at = datetime.now(timezone.utc)
    if application.assigned_reviewer_id is None:
        # Candidate pool only; assignment remains an explicit reviewer action in a later phase.
        pass
    record_audit(
        db,
        event_type="application.submitted",
        actor=actor,
        application_id=application.id,
        entity_type="application",
        entity_id=application.id,
        payload={"status": target_status.value, "version": application.version},
    )
    db.commit()
    db.refresh(application)
    return application


def withdraw_application(db: Session, application: Application, actor: User, reason: str) -> Application:
    require_application_owner(application, actor)
    if application.status not in {
        ApplicationStatus.DRAFT,
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.RECTIFICATION_REQUESTED,
    }:
        raise ApiError(409, "STATE_CONFLICT", "This application cannot be withdrawn in its current state.")
    if application.submitted_at is None:
        application.submitted_at = datetime.now(timezone.utc)
    _transition(db, application, ApplicationStatus.WITHDRAWN, actor, reason)
    record_audit(
        db,
        event_type="application.withdrawn",
        actor=actor,
        application_id=application.id,
        entity_type="application",
        entity_id=application.id,
        payload={"reason": reason},
    )
    db.commit()
    db.refresh(application)
    return application


def update_checklist_item(
    db: Session,
    application: Application,
    item: ApplicationChecklistItem,
    actor: User,
    justification: str | None,
    document_id: uuid.UUID | None,
) -> ApplicationChecklistItem:
    require_editable_application(application, actor)
    if document_id is not None:
        document = db.get(Document, document_id)
        if not document or document.application_id != application.id:
            raise ApiError(404, "NOT_FOUND", "Document not found.")
        if item.accepted_document_types and document.document_type.value not in item.accepted_document_types:
            raise ApiError(400, "VALIDATION_FAILED", "This document type is not accepted for the checklist item.")
        item.document_id = document_id
        item.status = ChecklistItemStatus.SATISFIED
    if justification is not None:
        item.justification = justification.strip() or None
    if item.document_id is None:
        item.status = ChecklistItemStatus.PENDING
    db.commit()
    db.refresh(item)
    return item


def checklist_counts(application: Application) -> dict[str, int]:
    counts = {
        "total": len(application.checklist_items),
        "satisfied": 0,
        "pending": 0,
        "waived": 0,
        "rejected": 0,
    }
    for item in application.checklist_items:
        if item.status is ChecklistItemStatus.SATISFIED:
            counts["satisfied"] += 1
        elif item.status is ChecklistItemStatus.WAIVED:
            counts["waived"] += 1
        elif item.status is ChecklistItemStatus.REJECTED:
            counts["rejected"] += 1
        else:
            counts["pending"] += 1
    return counts


def list_applications(
    db: Session,
    actor: User,
    *,
    status: ApplicationStatus | None = None,
    cycle: str | None = None,
    institution_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Application], int]:
    conditions = [application_scope_condition(actor)]
    if status is not None:
        conditions.append(Application.status == status)
    if cycle:
        conditions.append(Application.cycle == cycle)
    if institution_id is not None:
        if actor.role in {Role.APPLICANT, Role.REVIEWER}:
            raise ApiError(403, "FORBIDDEN", "You may not filter by institution.")
        conditions.append(Application.institution_id == institution_id)
    if assigned_to_me:
        conditions.append(Application.assigned_reviewer_id == actor.id)
    if q:
        conditions.append(Application.reference_no.ilike(f"%{q}%"))
    base = select(Application).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = list(
        db.scalars(
            base.order_by(Application.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total
