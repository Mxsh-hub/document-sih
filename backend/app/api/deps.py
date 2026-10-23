from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import Role
from app.db.models import User
from app.services.auth import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "AUTH_REQUIRED", "Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    payload = decode_access_token(credentials.credentials)
    raw_id = payload.get("sub")
    try:
        user_id = uuid.UUID(str(raw_id))
    except (ValueError, TypeError) as exc:
        raise ApiError(401, "AUTH_REQUIRED", "Authentication required.") from exc
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise ApiError(401, "AUTH_REQUIRED", "Authentication required.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    allowed = set(roles)

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise ApiError(403, "FORBIDDEN", "You do not have permission to perform this action.")
        return user

    return dependency


def require_staff(user: CurrentUser) -> User:
    if user.role not in {Role.REVIEWER, Role.APPROVER, Role.ADMIN, Role.AUDITOR}:
        raise ApiError(403, "FORBIDDEN", "You do not have permission to perform this action.")
    return user
