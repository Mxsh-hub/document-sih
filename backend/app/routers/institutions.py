from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import Role
from app.db.models import Institution, User
from app.schemas.phase3 import (
    InstitutionCreate,
    InstitutionOut,
    InstitutionPatch,
    RecordBundleOut,
    RecordItemsOut,
)
from app.services.authorization import require_staff_access
from app.services.records import get_record_bundle, get_record_group

router = APIRouter(prefix="/institutions", tags=["Institutions"])


def _require_institution(db: Session, institution_id: uuid.UUID) -> Institution:
    institution = db.get(Institution, institution_id)
    if not institution:
        raise ApiError(404, "NOT_FOUND", "Institution not found.")
    return institution


@router.get("/me", response_model=InstitutionOut)
def get_my_institution(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    if user.role is not Role.APPLICANT or user.institution_id is None:
        raise ApiError(404, "NOT_FOUND", "No institution is associated with this account.")
    return _require_institution(db, user.institution_id)


@router.get("", response_model=list[InstitutionOut])
def list_institutions(
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.AUDITOR))],
    db: Annotated[Session, Depends(get_db)],
):
    return list(db.scalars(select(Institution).order_by(Institution.legal_name)))


@router.post("", response_model=InstitutionOut, status_code=status.HTTP_201_CREATED)
def create_institution(
    payload: InstitutionCreate,
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    institution = Institution(**payload.model_dump())
    db.add(institution)
    db.commit()
    db.refresh(institution)
    return institution


@router.get("/{institution_id}/records", response_model=RecordBundleOut)
def get_records(
    institution_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    require_staff_access(user)
    _require_institution(db, institution_id)
    return get_record_bundle(db, institution_id)


@router.get("/{institution_id}/records/{record_type}", response_model=RecordItemsOut)
def get_records_by_type(
    institution_id: uuid.UUID,
    record_type: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    require_staff_access(user)
    _require_institution(db, institution_id)
    return get_record_group(db, institution_id, record_type)


@router.get("/{institution_id}", response_model=InstitutionOut)
def get_institution(
    institution_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if user.role is Role.APPLICANT:
        if user.institution_id != institution_id:
            raise ApiError(404, "NOT_FOUND", "Institution not found.")
    elif user.role not in {Role.REVIEWER, Role.APPROVER, Role.ADMIN, Role.AUDITOR}:
        raise ApiError(403, "FORBIDDEN", "You do not have permission to view this institution.")
    return _require_institution(db, institution_id)


@router.patch("/{institution_id}", response_model=InstitutionOut)
def update_institution(
    institution_id: uuid.UUID,
    payload: InstitutionPatch,
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    institution = _require_institution(db, institution_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(institution, field, value)
    db.commit()
    db.refresh(institution)
    return institution
