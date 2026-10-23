from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.enums import ApplicationStatus, Role
from app.db.models import Application, ApplicationChecklistItem, Document, DocumentVersion, User


def can_view_application(user: User, application: Application) -> bool:
    if user.role in {Role.ADMIN, Role.AUDITOR}:
        return True
    if user.role is Role.APPLICANT:
        return user.institution_id is not None and application.institution_id == user.institution_id
    if user.role is Role.REVIEWER:
        if application.status is ApplicationStatus.DRAFT:
            return False
        return application.assigned_reviewer_id in {None, user.id}
    if user.role is Role.APPROVER:
        return application.status is not ApplicationStatus.DRAFT
    return False


def application_scope_condition(user: User):
    if user.role in {Role.ADMIN, Role.AUDITOR}:
        return true()
    if user.role is Role.APPLICANT:
        return Application.institution_id == user.institution_id
    if user.role is Role.REVIEWER:
        return and_(
            Application.status != ApplicationStatus.DRAFT,
            or_(Application.assigned_reviewer_id.is_(None), Application.assigned_reviewer_id == user.id),
        )
    if user.role is Role.APPROVER:
        return Application.status != ApplicationStatus.DRAFT
    return Application.id.is_(None)


def get_application_or_404(db: Session, application_id: uuid.UUID, user: User) -> Application:
    application = db.get(Application, application_id)
    if not application or not can_view_application(user, application):
        raise ApiError(404, "NOT_FOUND", "Application not found.")
    return application


def require_editable_application(application: Application, user: User) -> None:
    if user.role is not Role.APPLICANT:
        raise ApiError(403, "FORBIDDEN", "Only the applicant may modify this application.")
    if application.institution_id != user.institution_id:
        raise ApiError(404, "NOT_FOUND", "Application not found.")
    if application.status is not ApplicationStatus.DRAFT:
        raise ApiError(409, "STATE_CONFLICT", "Only a draft application may be modified.")


def require_application_owner(application: Application, user: User) -> None:
    if user.role is not Role.APPLICANT or application.institution_id != user.institution_id:
        raise ApiError(404, "NOT_FOUND", "Application not found.")


def get_checklist_item_or_404(
    db: Session, application_id: uuid.UUID, item_id: uuid.UUID, user: User
) -> ApplicationChecklistItem:
    get_application_or_404(db, application_id, user)
    item = db.scalar(
        select(ApplicationChecklistItem).where(
            ApplicationChecklistItem.id == item_id,
            ApplicationChecklistItem.application_id == application_id,
        )
    )
    if not item:
        raise ApiError(404, "NOT_FOUND", "Checklist item not found.")
    return item


def get_document_or_404(db: Session, document_id: uuid.UUID, user: User) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise ApiError(404, "NOT_FOUND", "Document not found.")
    application = db.get(Application, document.application_id)
    if not application or not can_view_application(user, application):
        raise ApiError(404, "NOT_FOUND", "Document not found.")
    return document


def get_document_version_or_404(db: Session, version_id: uuid.UUID, user: User) -> DocumentVersion:
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise ApiError(404, "NOT_FOUND", "Document version not found.")
    document = db.get(Document, version.document_id)
    if not document:
        raise ApiError(404, "NOT_FOUND", "Document version not found.")
    application = db.get(Application, document.application_id)
    if not application or not can_view_application(user, application):
        raise ApiError(404, "NOT_FOUND", "Document version not found.")
    return version


def require_staff_access(user: User) -> None:
    if user.role not in {Role.REVIEWER, Role.APPROVER, Role.ADMIN, Role.AUDITOR}:
        raise ApiError(403, "FORBIDDEN", "You do not have permission to view institutional records.")
