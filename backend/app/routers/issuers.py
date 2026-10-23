from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import Role
from app.db.models import DocumentVersion, IssuedCredential, User
from app.routers.documents import get_document_version_or_404
from app.schemas.phase3 import (
    DemoCredentialIssue,
    DemoCredentialOut,
    IssuerVerificationCreate,
    IssuerVerificationOut,
)
from app.services.issuers import (
    issue_demo_credential,
    list_verifications,
    revoke_demo_credential,
    verify_demo_credential,
    verify_external_issuer,
)

router = APIRouter(tags=["Issuer Verification"])


@router.post(
    "/demo-issuer/credentials",
    response_model=DemoCredentialOut,
    status_code=status.HTTP_201_CREATED,
)
def create_demo_credential(
    payload: DemoCredentialIssue,
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    version = db.get(DocumentVersion, payload.document_version_id)
    if not version:
        raise ApiError(404, "NOT_FOUND", "Document version not found.")
    if payload.expires_at and payload.expires_at < datetime.now(timezone.utc):
        raise ApiError(400, "VALIDATION_FAILED", "The demo credential expiry must be in the future.")
    if len(str(payload.claims)) > 20000:
        raise ApiError(413, "CLAIMS_TOO_LARGE", "The demonstration claims are too large.")
    credential = issue_demo_credential(
        db,
        version=version,
        actor=user,
        subject_reference=payload.subject_reference,
        claims=payload.claims,
        expires_at=payload.expires_at,
    )
    return DemoCredentialOut.model_validate(credential)


@router.get("/demo-issuer/credentials", response_model=list[DemoCredentialOut])
def list_demo_credentials(
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
    document_version_id: uuid.UUID | None = None,
):
    statement = select(IssuedCredential).order_by(IssuedCredential.issued_at.desc()).limit(100)
    if document_version_id:
        statement = statement.where(IssuedCredential.document_version_id == document_version_id)
    return [DemoCredentialOut.model_validate(item) for item in db.scalars(statement)]


@router.post(
    "/demo-issuer/credentials/{credential_pk}/revoke",
    response_model=DemoCredentialOut,
)
def revoke_credential(
    credential_pk: uuid.UUID,
    user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    credential = db.get(IssuedCredential, credential_pk)
    if not credential:
        raise ApiError(404, "NOT_FOUND", "Demo credential not found.")
    return DemoCredentialOut.model_validate(revoke_demo_credential(db, credential, user))


@router.post(
    "/document-versions/{version_id}/issuer-verifications",
    response_model=IssuerVerificationOut,
    status_code=status.HTTP_201_CREATED,
)
def verify_issuer_credential(
    version_id: uuid.UUID,
    payload: IssuerVerificationCreate,
    user: Annotated[User, Depends(require_roles(Role.REVIEWER, Role.APPROVER, Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    version = get_document_version_or_404(db, version_id, user)
    if payload.issuer_code == "external":
        verification = verify_external_issuer(db, version=version, actor=user)
    else:
        verification = verify_demo_credential(
            db, version=version, credential_id=payload.credential_id, actor=user
        )
    return IssuerVerificationOut.model_validate(verification)


@router.get(
    "/document-versions/{version_id}/issuer-verifications",
    response_model=list[IssuerVerificationOut],
)
def get_issuer_verifications(
    version_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    get_document_version_or_404(db, version_id, user)
    return [IssuerVerificationOut.model_validate(item) for item in list_verifications(db, version_id)]
