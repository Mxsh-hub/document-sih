from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import ChecklistTemplateStatus, Role
from app.db.models import (
    ApplicationCategory,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Institution,
    User,
)
from app.schemas.phase3 import (
    AdminUserCreate,
    AdminUserPatch,
    CategoryCreate,
    CategoryOut,
    ChecklistTemplateCreate,
    ChecklistTemplateItemOut,
    ChecklistTemplateOut,
    UserOut,
)
from app.services.auth import hash_password, normalize_email, revoke_all_user_tokens

router = APIRouter(prefix="/admin", tags=["Administration"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]


def _validate_institution_membership(db: Session, role: Role, institution_id: uuid.UUID | None) -> None:
    if role is Role.APPLICANT and institution_id is None:
        raise ApiError(400, "VALIDATION_FAILED", "Applicants require an institution_id.")
    if role is not Role.APPLICANT and institution_id is not None:
        raise ApiError(400, "VALIDATION_FAILED", "AICTE staff accounts must not be tied to an institution.")
    if institution_id is not None and not db.get(Institution, institution_id):
        raise ApiError(404, "NOT_FOUND", "Institution not found.")


@router.get("/users", response_model=list[UserOut])
def list_users(admin: AdminUser, db: Annotated[Session, Depends(get_db)]):
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: AdminUserCreate, admin: AdminUser, db: Annotated[Session, Depends(get_db)]):
    _validate_institution_membership(db, payload.role, payload.institution_id)
    email = normalize_email(payload.email)
    if db.scalar(select(User).where(User.email == email)):
        raise ApiError(409, "STATE_CONFLICT", "An account with this email already exists.")
    if payload.wallet_did and db.scalar(select(User).where(User.wallet_did == payload.wallet_did)):
        raise ApiError(409, "STATE_CONFLICT", "This wallet DID is already in use.")
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        role=payload.role,
        institution_id=payload.institution_id,
        wallet_did=payload.wallet_did,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUserPatch,
    admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)
    if not user:
        raise ApiError(404, "NOT_FOUND", "User not found.")
    new_role = payload.role if payload.role is not None else user.role
    new_institution = (
        payload.institution_id if "institution_id" in payload.model_fields_set else user.institution_id
    )
    _validate_institution_membership(db, new_role, new_institution)
    if user.role is Role.ADMIN and (new_role is not Role.ADMIN or payload.is_active is False):
        admin_count = db.scalar(
            select(func.count()).select_from(User).where(
                User.role == Role.ADMIN, User.is_active.is_(True)
            )
        )
        if admin_count is not None and admin_count <= 1:
            raise ApiError(409, "STATE_CONFLICT", "The last active administrator cannot be demoted or disabled.")
    for field in ("full_name", "is_active"):
        if field in payload.model_fields_set:
            setattr(user, field, getattr(payload, field))
    user.role = new_role
    user.institution_id = new_institution
    user.version += 1
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: uuid.UUID, admin: AdminUser, db: Annotated[Session, Depends(get_db)]):
    user = db.get(User, user_id)
    if not user:
        raise ApiError(404, "NOT_FOUND", "User not found.")
    temporary_password = f"Tmp-{secrets.token_urlsafe(15)}"
    user.password_hash = hash_password(temporary_password)
    user.version += 1
    db.commit()
    revoke_all_user_tokens(db, user.id)
    return {"user_id": str(user.id), "temporary_password": temporary_password}


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(admin: AdminUser, db: Annotated[Session, Depends(get_db)]):
    return list(db.scalars(select(ApplicationCategory).order_by(ApplicationCategory.code)))


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, admin: AdminUser, db: Annotated[Session, Depends(get_db)]):
    code = payload.code.upper()
    if db.scalar(select(ApplicationCategory).where(ApplicationCategory.code == code)):
        raise ApiError(409, "STATE_CONFLICT", "This category already exists.")
    category = ApplicationCategory(
        code=code, name=payload.name, description=payload.description, active=True
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/checklist-templates", response_model=list[ChecklistTemplateOut])
def list_templates(
    admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
    category_id: uuid.UUID | None = Query(None),
):
    query = select(ChecklistTemplate).order_by(ChecklistTemplate.created_at.desc())
    if category_id:
        query = query.where(ChecklistTemplate.category_id == category_id)
    return list(db.scalars(query))


@router.post(
    "/checklist-templates", response_model=ChecklistTemplateOut, status_code=status.HTTP_201_CREATED
)
def create_template(
    payload: ChecklistTemplateCreate,
    admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
):
    category = db.get(ApplicationCategory, payload.category_id)
    if not category:
        raise ApiError(404, "NOT_FOUND", "Application category not found.")
    if db.scalar(
        select(ChecklistTemplate).where(
            ChecklistTemplate.category_id == payload.category_id,
            ChecklistTemplate.version == payload.version,
        )
    ):
        raise ApiError(409, "STATE_CONFLICT", "This checklist template version already exists.")
    codes = [item.code for item in payload.items]
    if len(codes) != len(set(codes)):
        raise ApiError(400, "VALIDATION_FAILED", "Checklist item codes must be unique.")
    template = ChecklistTemplate(
        category_id=payload.category_id,
        version=payload.version,
        status=ChecklistTemplateStatus.DRAFT,
        effective_from=payload.effective_from,
        source_citation=payload.source_citation,
        created_by=admin.id,
    )
    for item in payload.items:
        template.items.append(
            ChecklistTemplateItem(
                code=item.code,
                title=item.title,
                description=item.description,
                required=item.required,
                accepted_document_types=[value.value for value in item.accepted_document_types],
                record_requirement=item.record_requirement,
                rule_codes=item.rule_codes,
                sort_order=item.sort_order,
            )
        )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.post("/checklist-templates/{template_id}/activate", response_model=ChecklistTemplateOut)
def activate_template(
    template_id: uuid.UUID,
    admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
):
    template = db.get(ChecklistTemplate, template_id)
    if not template:
        raise ApiError(404, "NOT_FOUND", "Checklist template not found.")
    if template.status is ChecklistTemplateStatus.ACTIVE:
        return template
    current = db.scalar(
        select(ChecklistTemplate).where(
            ChecklistTemplate.category_id == template.category_id,
            ChecklistTemplate.status == ChecklistTemplateStatus.ACTIVE,
        )
    )
    if current:
        current.status = ChecklistTemplateStatus.RETIRED
    template.status = ChecklistTemplateStatus.ACTIVE
    db.commit()
    db.refresh(template)
    return template
