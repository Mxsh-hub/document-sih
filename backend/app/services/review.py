from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.enums import (
    AlertStatus,
    AlertType,
    ApplicationStatus,
    DecisionType,
    ReviewActionType,
    Role,
    RuleOutcome,
    RuleSeverity,
)
from app.db.models import (
    Alert,
    Application,
    ApplicationStatusHistory,
    AuditEvent,
    Decision,
    Document,
    InfrastructureEvidence,
    IssuerVerification,
    ReviewAction,
    User,
    ValidationRun,
)
from app.services.assurance import infrastructure_assessment, list_anomalies
from app.services.audit import record_audit
from app.services.authorization import application_scope_condition, require_staff_access
from app.services.issuers import list_verifications
from app.services.validation import latest_run_for_application

REVIEWABLE_STATUSES = {
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.RESUBMITTED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.RECTIFICATION_REQUESTED,
}
DECISION_STATUSES = REVIEWABLE_STATUSES
TERMINAL = {ApplicationStatus.APPROVED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN}


def _transition(
    db: Session,
    application: Application,
    to_status: ApplicationStatus,
    actor: User,
    reason: str | None,
) -> None:
    db.add(
        ApplicationStatusHistory(
            application_id=application.id,
            from_status=application.status,
            to_status=to_status,
            actor_id=actor.id,
            reason=reason,
        )
    )
    application.status = to_status


def _ensure_alert(
    db: Session,
    application: Application,
    *,
    alert_type: AlertType,
    title: str,
    message: str,
    source_ref: str,
    payload: dict[str, Any] | None = None,
) -> Alert:
    existing = db.scalar(
        select(Alert).where(
            Alert.application_id == application.id,
            Alert.alert_type == alert_type,
            Alert.source_ref == source_ref,
        )
    )
    if existing:
        return existing
    alert = Alert(
        application_id=application.id,
        alert_type=alert_type,
        status=AlertStatus.OPEN,
        title=title,
        message=message,
        source_ref=source_ref,
        payload=payload,
    )
    db.add(alert)
    db.flush()
    return alert


def sync_alerts(db: Session, application: Application) -> list[Alert]:
    created: list[Alert] = []
    run = latest_run_for_application(db, application.id)
    if run:
        for finding in run.findings:
            if finding.outcome is RuleOutcome.FAIL:
                if finding.code == "AFFILIATION_VALIDITY":
                    alert_type = AlertType.EXPIRED_DOCUMENT
                else:
                    alert_type = AlertType.VALIDATION_FAILURE
                before = db.scalar(
                    select(Alert.id).where(
                        Alert.application_id == application.id,
                        Alert.alert_type == alert_type,
                        Alert.source_ref == str(finding.id),
                    )
                )
                alert = _ensure_alert(
                    db,
                    application,
                    alert_type=alert_type,
                    title=finding.title,
                    message=finding.message,
                    source_ref=str(finding.id),
                    payload={
                        "finding_id": str(finding.id),
                        "severity": finding.severity.value,
                        "rule_code": finding.code,
                        "validation_run_id": str(run.id),
                    },
                )
                if before is None:
                    created.append(alert)
            elif finding.outcome is RuleOutcome.INCONCLUSIVE:
                before = db.scalar(
                    select(Alert.id).where(
                        Alert.application_id == application.id,
                        Alert.alert_type == AlertType.PENDING_VERIFICATION,
                        Alert.source_ref == str(finding.id),
                    )
                )
                alert = _ensure_alert(
                    db,
                    application,
                    alert_type=AlertType.PENDING_VERIFICATION,
                    title=finding.title,
                    message=finding.message,
                    source_ref=str(finding.id),
                    payload={"finding_id": str(finding.id), "rule_code": finding.code},
                )
                if before is None:
                    created.append(alert)
    for signal in list_anomalies(db, application.id):
        before = db.scalar(
            select(Alert.id).where(
                Alert.application_id == application.id,
                Alert.alert_type == AlertType.UNRESOLVED_DISCREPANCY,
                Alert.source_ref == str(signal.id),
            )
        )
        alert = _ensure_alert(
            db,
            application,
            alert_type=AlertType.UNRESOLVED_DISCREPANCY,
            title=signal.signal_code.replace("_", " ").title(),
            message=signal.message,
            source_ref=str(signal.id),
            payload={"anomaly_signal_id": str(signal.id), "advisory_only": True},
        )
        if before is None:
            created.append(alert)
    db.commit()
    return created


def list_alerts(
    db: Session,
    application_id: uuid.UUID,
    *,
    status: AlertStatus | None = None,
) -> list[Alert]:
    statement = select(Alert).where(Alert.application_id == application_id).order_by(Alert.created_at.desc())
    if status:
        statement = statement.where(Alert.status == status)
    return list(db.scalars(statement))


def acknowledge_alert(db: Session, alert: Alert, actor: User) -> Alert:
    require_staff_access(actor)
    if alert.status is AlertStatus.RESOLVED:
        raise ApiError(409, "STATE_CONFLICT", "A resolved alert cannot be acknowledged.")
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = actor.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    record_audit(
        db,
        event_type="alert.acknowledged",
        actor=actor,
        application_id=alert.application_id,
        entity_type="alert",
        entity_id=alert.id,
        payload={"alert_type": alert.alert_type.value},
    )
    db.commit()
    db.refresh(alert)
    return alert


def resolve_alert(db: Session, alert: Alert, actor: User, note: str | None) -> Alert:
    require_staff_access(actor)
    if alert.status is AlertStatus.RESOLVED:
        return alert
    alert.status = AlertStatus.RESOLVED
    alert.resolved_by = actor.id
    alert.resolved_at = datetime.now(timezone.utc)
    if note:
        alert.payload = {**(alert.payload or {}), "resolution_note": note}
    record_audit(
        db,
        event_type="alert.resolved",
        actor=actor,
        application_id=alert.application_id,
        entity_type="alert",
        entity_id=alert.id,
        payload={"alert_type": alert.alert_type.value, "resolution_note": note},
    )
    db.commit()
    db.refresh(alert)
    return alert


def _resolve_all_for_decision(db: Session, application: Application, actor: User) -> None:
    alerts = db.scalars(
        select(Alert).where(
            Alert.application_id == application.id,
            Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]),
        )
    )
    now = datetime.now(timezone.utc)
    for alert in alerts:
        alert.status = AlertStatus.RESOLVED
        alert.resolved_by = actor.id
        alert.resolved_at = now


def create_review_action(
    db: Session,
    *,
    application: Application,
    actor: User,
    action_type: ReviewActionType,
    note: str | None,
    assigned_user_id: uuid.UUID | None,
) -> ReviewAction:
    require_staff_access(actor)
    if application.status in TERMINAL:
        raise ApiError(409, "STATE_CONFLICT", "This application is already in a terminal state.")
    if action_type is ReviewActionType.NOTE and not note:
        raise ApiError(400, "VALIDATION_FAILED", "A note is required.")
    if action_type in {ReviewActionType.REQUEST_RECTIFICATION, ReviewActionType.ESCALATE} and not note:
        raise ApiError(400, "VALIDATION_FAILED", "A reason is required for this action.")

    from_status = application.status
    to_status = application.status
    if action_type is ReviewActionType.ASSIGN:
        target_id = assigned_user_id or actor.id
        target = db.get(User, target_id)
        if not target or not target.is_active or target.role not in {Role.REVIEWER, Role.APPROVER}:
            raise ApiError(400, "VALIDATION_FAILED", "The assignee must be an active reviewer or approver.")
        if actor.role is Role.REVIEWER and target.id != actor.id:
            raise ApiError(403, "FORBIDDEN", "Reviewers may only assign applications to themselves.")
        application.assigned_reviewer_id = target.id
        if application.status in {ApplicationStatus.SUBMITTED, ApplicationStatus.RESUBMITTED}:
            to_status = ApplicationStatus.UNDER_REVIEW
            _transition(db, application, to_status, actor, note or "Reviewer assigned.")
    elif action_type is ReviewActionType.REQUEST_RECTIFICATION:
        if application.status not in {
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.RESUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
        }:
            raise ApiError(409, "STATE_CONFLICT", "Rectification cannot be requested in the current state.")
        to_status = ApplicationStatus.RECTIFICATION_REQUESTED
        _transition(db, application, to_status, actor, note)
    elif action_type is ReviewActionType.ESCALATE:
        if application.status not in REVIEWABLE_STATUSES:
            raise ApiError(409, "STATE_CONFLICT", "Only a submitted application can be escalated.")

    review_action = ReviewAction(
        application_id=application.id,
        actor_id=actor.id,
        action_type=action_type,
        note=note,
        from_status=from_status,
        to_status=to_status,
        payload={"assigned_user_id": str(assigned_user_id)} if assigned_user_id else None,
    )
    db.add(review_action)
    db.flush()
    if action_type is ReviewActionType.REQUEST_RECTIFICATION:
        _ensure_alert(
            db,
            application,
            alert_type=AlertType.RECTIFICATION_REQUEST,
            title="Rectification requested",
            message=note or "The reviewer requested rectification.",
            source_ref=str(review_action.id),
            payload={"review_action_id": str(review_action.id)},
        )
    if action_type is ReviewActionType.ESCALATE:
        _ensure_alert(
            db,
            application,
            alert_type=AlertType.ESCALATION,
            title="Application escalated",
            message=note or "The application was escalated for senior review.",
            source_ref=str(review_action.id),
            payload={"review_action_id": str(review_action.id)},
        )
    record_audit(
        db,
        event_type=f"review.{action_type.value.lower()}",
        actor=actor,
        application_id=application.id,
        entity_type="review_action",
        entity_id=review_action.id,
        payload={
            "from_status": from_status.value,
            "to_status": to_status.value,
            "note": note,
            "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
        },
    )
    db.commit()
    db.refresh(review_action)
    db.refresh(application)
    return review_action


def record_decision(
    db: Session,
    *,
    application: Application,
    actor: User,
    decision_type: DecisionType,
    rationale: str,
    conditions: dict[str, Any] | None,
) -> Decision:
    if actor.role not in {Role.APPROVER, Role.ADMIN}:
        raise ApiError(403, "FORBIDDEN", "Only an approver or administrator may record a final decision.")
    if application.status in TERMINAL:
        raise ApiError(409, "STATE_CONFLICT", "A final decision already exists for this application.")
    if application.status not in DECISION_STATUSES:
        raise ApiError(409, "STATE_CONFLICT", "This application cannot receive a final decision in its current state.")
    existing = db.scalar(select(Decision).where(Decision.application_id == application.id).limit(1))
    if existing:
        raise ApiError(409, "STATE_CONFLICT", "A final decision already exists for this application.")
    if len(rationale.strip()) < 10:
        raise ApiError(400, "VALIDATION_FAILED", "A substantive decision rationale is required.")

    to_status = (
        ApplicationStatus.APPROVED
        if decision_type is DecisionType.APPROVE
        else ApplicationStatus.REJECTED
    )
    _transition(db, application, to_status, actor, rationale)
    decision = Decision(
        application_id=application.id,
        decision_type=decision_type,
        rationale=rationale,
        conditions=conditions,
        decided_by=actor.id,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(decision)
    db.flush()
    _resolve_all_for_decision(db, application, actor)
    record_audit(
        db,
        event_type=f"decision.{decision_type.value.lower()}",
        actor=actor,
        application_id=application.id,
        entity_type="decision",
        entity_id=decision.id,
        payload={
            "decision": decision_type.value,
            "rationale": rationale,
            "conditions": conditions,
            "status": to_status.value,
        },
    )
    db.commit()
    db.refresh(decision)
    db.refresh(application)
    return decision


def dashboard_summary(db: Session, actor: User) -> dict[str, Any]:
    scope = application_scope_condition(actor)
    counts = {
        status.value: count
        for status, count in db.execute(
            select(Application.status, func.count(Application.id))
            .where(scope)
            .group_by(Application.status)
        )
    }
    visible_ids = select(Application.id).where(scope)
    open_alerts = db.scalar(
        select(func.count(Alert.id)).where(
            Alert.application_id.in_(visible_ids),
            Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]),
        )
    ) or 0
    pending_verification = db.scalar(
        select(func.count(Alert.id)).where(
            Alert.application_id.in_(visible_ids),
            Alert.alert_type == AlertType.PENDING_VERIFICATION,
            Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]),
        )
    ) or 0
    assigned_to_me = db.scalar(
        select(func.count(Application.id)).where(
            scope,
            Application.assigned_reviewer_id == actor.id,
        )
    ) or 0
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "open_alerts": open_alerts,
        "pending_verification": pending_verification,
        "assigned_to_me": assigned_to_me,
        "role": actor.role.value,
    }


def review_overview(db: Session, application: Application) -> dict[str, Any]:
    run = latest_run_for_application(db, application.id)
    documents = list(db.scalars(select(Document).where(Document.application_id == application.id)))
    verifications: list[IssuerVerification] = []
    for document in documents:
        if document.current_version_id:
            verifications.extend(list_verifications(db, document.current_version_id))
    decisions = list(
        db.scalars(
            select(Decision)
            .where(Decision.application_id == application.id)
            .order_by(Decision.decided_at.desc())
        )
    )
    actions = list(
        db.scalars(
            select(ReviewAction)
            .where(ReviewAction.application_id == application.id)
            .order_by(ReviewAction.created_at.desc())
        )
    )
    audits = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.application_id == application.id)
            .order_by(AuditEvent.sequence.desc())
            .limit(100)
        )
    )
    return {
        "application": {
            "id": application.id,
            "reference_no": application.reference_no,
            "status": application.status,
            "cycle": application.cycle,
            "assigned_reviewer_id": application.assigned_reviewer_id,
            "version": application.version,
        },
        "latest_validation_run": run,
        "documents": documents,
        "issuer_verifications": verifications,
        "anomaly_signals": list_anomalies(db, application.id),
        "infrastructure_assessment": infrastructure_assessment(db, application),
        "alerts": list_alerts(db, application.id),
        "review_actions": actions,
        "decisions": decisions,
        "audit_events": audits,
    }
