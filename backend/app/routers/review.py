from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import AlertStatus, AlertType, Role
from app.db.models import Alert, Application, AuditEvent, Decision, Document, ReviewAction, User
from app.schemas.phase3 import (
    AlertOut,
    AlertResolution,
    AnomalySignalOut,
    AuditEventOut,
    DecisionCreate,
    DecisionOut,
    InfrastructureAssessmentOut,
    IssuerVerificationOut,
    ReviewActionCreate,
    ReviewActionOut,
    ValidationRunOut,
)
from app.services.assurance import infrastructure_assessment, list_anomalies
from app.services.audit import record_audit, verify_audit_chain
from app.services.authorization import get_application_or_404, require_staff_access
from app.services.issuers import list_verifications
from app.services.review import (
    acknowledge_alert,
    create_review_action,
    dashboard_summary,
    list_alerts,
    record_decision,
    resolve_alert,
    review_overview,
)

router = APIRouter(tags=["Review and Audit"])


@router.get("/dashboard/summary")
def get_dashboard_summary(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    return dashboard_summary(db, user)


@router.post(
    "/applications/{application_id}/review-actions",
    response_model=ReviewActionOut,
)
def add_review_action(
    application_id: uuid.UUID,
    payload: ReviewActionCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    require_staff_access(user)
    application = get_application_or_404(db, application_id, user)
    action = create_review_action(
        db,
        application=application,
        actor=user,
        action_type=payload.action_type,
        note=payload.note,
        assigned_user_id=payload.assigned_user_id,
    )
    return ReviewActionOut.model_validate(action)


@router.get(
    "/applications/{application_id}/review-actions",
    response_model=list[ReviewActionOut],
)
def get_review_actions(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    require_staff_access(user)
    get_application_or_404(db, application_id, user)
    actions = db.scalars(
        select(ReviewAction)
        .where(ReviewAction.application_id == application_id)
        .order_by(ReviewAction.created_at.desc())
    )
    return [ReviewActionOut.model_validate(item) for item in actions]


@router.post(
    "/applications/{application_id}/decisions",
    response_model=DecisionOut,
)
def create_decision(
    application_id: uuid.UUID,
    payload: DecisionCreate,
    user: Annotated[User, Depends(require_roles(Role.APPROVER, Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    decision = record_decision(
        db,
        application=application,
        actor=user,
        decision_type=payload.decision_type,
        rationale=payload.rationale,
        conditions=payload.conditions,
    )
    return DecisionOut.model_validate(decision)


@router.get(
    "/applications/{application_id}/decisions",
    response_model=list[DecisionOut],
)
def get_decisions(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    get_application_or_404(db, application_id, user)
    decisions = db.scalars(
        select(Decision)
        .where(Decision.application_id == application_id)
        .order_by(Decision.decided_at.desc())
    )
    return [DecisionOut.model_validate(item) for item in decisions]


@router.get(
    "/applications/{application_id}/alerts",
    response_model=list[AlertOut],
)
def get_application_alerts(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    alert_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
):
    get_application_or_404(db, application_id, user)
    return [AlertOut.model_validate(item) for item in list_alerts(db, application_id, status=alert_status)]


@router.get("/alerts", response_model=list[AlertOut])
def list_all_alerts(
    user: Annotated[User, Depends(require_roles(Role.REVIEWER, Role.APPROVER, Role.ADMIN, Role.AUDITOR))],
    db: Annotated[Session, Depends(get_db)],
    alert_status: Annotated[AlertStatus | None, Query(alias="status")] = AlertStatus.OPEN,
    alert_type: AlertType | None = None,
    application_id: uuid.UUID | None = None,
):
    statement = select(Alert).order_by(Alert.created_at.desc()).limit(200)
    if alert_status:
        statement = statement.where(Alert.status == alert_status)
    if alert_type:
        statement = statement.where(Alert.alert_type == alert_type)
    if application_id:
        statement = statement.where(Alert.application_id == application_id)
    return [AlertOut.model_validate(item) for item in db.scalars(statement)]


def _get_alert(db: Session, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise ApiError(404, "NOT_FOUND", "Alert not found.")
    return alert


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(
    alert_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    return AlertOut.model_validate(acknowledge_alert(db, _get_alert(db, alert_id), user))


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve(
    alert_id: uuid.UUID,
    payload: AlertResolution,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    return AlertOut.model_validate(
        resolve_alert(db, _get_alert(db, alert_id), user, payload.note)
    )


@router.get("/applications/{application_id}/review-overview")
def get_review_overview(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    require_staff_access(user)
    application = get_application_or_404(db, application_id, user)
    overview = review_overview(db, application)
    run = overview["latest_validation_run"]
    documents = overview["documents"]
    return {
        "application": overview["application"],
        "latest_validation_run": ValidationRunOut.model_validate(run).model_dump(mode="json") if run else None,
        "documents": [
            {
                "id": document.id,
                "document_type": document.document_type.value,
                "status": document.status.value,
                "current_version_id": document.current_version_id,
                "created_at": document.created_at,
            }
            for document in documents
        ],
        "issuer_verifications": [
            IssuerVerificationOut.model_validate(item).model_dump(mode="json")
            for item in overview["issuer_verifications"]
        ],
        "anomaly_signals": [
            AnomalySignalOut.model_validate(item).model_dump(mode="json")
            for item in overview["anomaly_signals"]
        ],
        "infrastructure_assessment": InfrastructureAssessmentOut.model_validate(
            overview["infrastructure_assessment"]
        ).model_dump(mode="json"),
        "alerts": [AlertOut.model_validate(item).model_dump(mode="json") for item in overview["alerts"]],
        "review_actions": [
            ReviewActionOut.model_validate(item).model_dump(mode="json")
            for item in overview["review_actions"]
        ],
        "decisions": [
            DecisionOut.model_validate(item).model_dump(mode="json") for item in overview["decisions"]
        ],
        "audit_events": [
            AuditEventOut.model_validate(item).model_dump(mode="json") for item in overview["audit_events"]
        ],
    }


@router.get(
    "/applications/{application_id}/audit-events",
    response_model=list[AuditEventOut],
)
def get_application_audit_events(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    require_staff_access(user)
    get_application_or_404(db, application_id, user)
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.application_id == application_id)
        .order_by(AuditEvent.sequence.desc())
        .limit(200)
    )
    return [AuditEventOut.model_validate(item) for item in events]


@router.get("/admin/audit-events", response_model=list[AuditEventOut])
def list_audit_events(
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.AUDITOR))],
    db: Annotated[Session, Depends(get_db)],
    application_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    statement = select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(limit)
    if application_id:
        statement = statement.where(AuditEvent.application_id == application_id)
    return [AuditEventOut.model_validate(item) for item in db.scalars(statement)]


@router.get("/admin/audit-events/verify")
def verify_audit(
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.AUDITOR))],
    db: Annotated[Session, Depends(get_db)],
):
    return verify_audit_chain(db)
