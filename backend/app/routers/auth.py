from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.config import settings
from app.core.errors import ApiError
from app.core.security import check_login_allowed, clear_login_failures, record_login_failure
from app.db.base import get_db
from app.schemas.phase3 import (
    LoginRequest,
    LogoutRequest,
    MeOut,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth as auth_service
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _scopes_for(user) -> list[str]:
    scopes = ["auth:me"]
    if user.role.value == "APPLICANT":
        scopes += ["application:read:own", "application:write:own", "document:write:own"]
    elif user.role.value == "REVIEWER":
        scopes += ["application:read:assigned", "records:read:scope"]
    elif user.role.value == "APPROVER":
        scopes += ["application:read:scope", "records:read:scope"]
    elif user.role.value == "ADMIN":
        scopes += ["application:read:all", "records:read:all", "admin:manage"]
    elif user.role.value == "AUDITOR":
        scopes += ["application:read:all", "records:read:all", "audit:read"]
    return scopes


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    client_ip = request.client.host if request.client else "unknown"
    check_login_allowed(client_ip, payload.email)
    try:
        user = auth_service.authenticate(db, payload.email, payload.password)
    except ApiError:
        record_login_failure(client_ip, payload.email)
        raise
    clear_login_failures(client_ip, payload.email)
    access_token, _ = auth_service.create_access_token(user)
    refresh_token, _ = auth_service.issue_refresh_token(db, user)
    record_audit(
        db,
        event_type="auth.login_succeeded",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        payload={"email": user.email},
    )
    db.commit()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Annotated[Session, Depends(get_db)]):
    user, refresh_token, _ = auth_service.rotate_refresh_token(db, payload.refresh_token)
    access_token, _ = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    auth_service.revoke_token(db, payload.refresh_token, user.id)
    record_audit(
        db,
        event_type="auth.logout",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        payload={},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser):
    return MeOut(user=UserOut.model_validate(user), scopes=_scopes_for(user))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if not auth_service.verify_password(payload.current_password, user.password_hash):
        raise ApiError(401, "AUTH_REQUIRED", "Current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise ApiError(400, "VALIDATION_FAILED", "New password must differ from the current password.")
    user.password_hash = auth_service.hash_password(payload.new_password)
    user.version += 1
    record_audit(
        db,
        event_type="auth.password_changed",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        payload={},
    )
    db.commit()
    auth_service.revoke_all_user_tokens(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
