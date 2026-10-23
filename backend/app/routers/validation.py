from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import ApplicationStatus, Role, RuleSetStatus
from app.db.models import ApplicationCategory, Rule, RuleSet, User, ValidationRun
from app.schemas.phase3 import (
    RulePatch,
    RuleSetCreate,
    RuleSetOut,
    ValidationRunOut,
)
from app.services.authorization import get_application_or_404
from app.services.audit import record_audit
from app.services.validation import run_validation

router = APIRouter(tags=["Validation"])


@router.post(
    "/applications/{application_id}/validation-runs",
    response_model=ValidationRunOut,
    status_code=status.HTTP_201_CREATED,
)
def start_validation(
    application_id: uuid.UUID,
    user: Annotated[User, Depends(require_roles(Role.REVIEWER, Role.APPROVER, Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    if application.status is ApplicationStatus.DRAFT:
        raise ApiError(409, "STATE_CONFLICT", "A draft application cannot be validated.")
    return ValidationRunOut.model_validate(run_validation(db, application, actor=user))


@router.get(
    "/applications/{application_id}/validation-runs",
    response_model=list[ValidationRunOut],
)
def list_validation_runs(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    get_application_or_404(db, application_id, user)
    runs = db.scalars(
        select(ValidationRun)
        .where(ValidationRun.application_id == application_id)
        .order_by(ValidationRun.created_at.desc())
        .limit(limit)
    )
    return [ValidationRunOut.model_validate(item) for item in runs]


@router.get("/validation-runs/{run_id}", response_model=ValidationRunOut)
def get_validation_run(
    run_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    run = db.get(ValidationRun, run_id)
    if not run:
        raise ApiError(404, "NOT_FOUND", "Validation run not found.")
    get_application_or_404(db, run.application_id, user)
    return ValidationRunOut.model_validate(run)


@router.get("/admin/rule-sets", response_model=list[RuleSetOut])
def list_rule_sets(
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.AUDITOR))],
    db: Annotated[Session, Depends(get_db)],
    category_id: uuid.UUID | None = None,
):
    statement = select(RuleSet).order_by(RuleSet.category_id, RuleSet.version.desc())
    if category_id:
        statement = statement.where(RuleSet.category_id == category_id)
    return [RuleSetOut.model_validate(item) for item in db.scalars(statement)]


@router.post("/admin/rule-sets", response_model=RuleSetOut, status_code=status.HTTP_201_CREATED)
def create_rule_set(
    payload: RuleSetCreate,
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    category = db.get(ApplicationCategory, payload.category_id)
    if not category:
        raise ApiError(404, "NOT_FOUND", "Application category not found.")
    existing = db.scalar(
        select(RuleSet).where(RuleSet.code == payload.code, RuleSet.version == payload.version)
    )
    if existing:
        raise ApiError(409, "DUPLICATE_RULE_SET", "A rule set with this code and version already exists.")
    rule_set = RuleSet(
        code=payload.code,
        name=payload.name,
        category_id=payload.category_id,
        version=payload.version,
        status=RuleSetStatus.DRAFT,
        effective_from=payload.effective_from,
        source_citation=payload.source_citation,
        synthetic=True,
        created_by=user.id,
    )
    for item in payload.rules:
        rule_set.rules.append(Rule(**item.model_dump()))
    db.add(rule_set)
    db.commit()
    db.refresh(rule_set)
    return RuleSetOut.model_validate(rule_set)


@router.post("/admin/rule-sets/{rule_set_id}/activate", response_model=RuleSetOut)
def activate_rule_set(
    rule_set_id: uuid.UUID,
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    rule_set = db.get(RuleSet, rule_set_id)
    if not rule_set:
        raise ApiError(404, "NOT_FOUND", "Rule set not found.")
    active_sets = db.scalars(
        select(RuleSet).where(
            RuleSet.category_id == rule_set.category_id,
            RuleSet.status == RuleSetStatus.ACTIVE,
        )
    )
    for active in active_sets:
        if active.id != rule_set.id:
            active.status = RuleSetStatus.ARCHIVED
    rule_set.status = RuleSetStatus.ACTIVE
    rule_set.activated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        event_type="rule_set.activated",
        actor=user,
        entity_type="rule_set",
        entity_id=rule_set.id,
        payload={"code": rule_set.code, "version": rule_set.version, "category_id": str(rule_set.category_id)},
    )
    db.commit()
    db.refresh(rule_set)
    return RuleSetOut.model_validate(rule_set)


@router.patch("/admin/rules/{rule_id}", response_model=RuleSetOut)
def update_rule(
    rule_id: uuid.UUID,
    payload: RulePatch,
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise ApiError(404, "NOT_FOUND", "Rule not found.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    record_audit(
        db,
        event_type="rule.updated",
        actor=user,
        entity_type="rule",
        entity_id=rule.id,
        payload={"rule_code": rule.code, "changes": changes},
    )
    db.commit()
    db.refresh(rule.rule_set)
    return RuleSetOut.model_validate(rule.rule_set)
