from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ApiError
from app.db.models import RefreshToken, User
from app.services.audit import record_audit

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _jwt_secret() -> str:
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    return settings.JWT_SECRET


def create_access_token(user: User) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "institution_id": str(user.institution_id) if user.institution_id else None,
        "typ": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "TOKEN_EXPIRED", "Access token expired; refresh required.") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "AUTH_REQUIRED", "Authentication required.") from exc
    if payload.get("typ") != "access":
        raise ApiError(401, "AUTH_REQUIRED", "Authentication required.")
    return payload


def _refresh_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_refresh_token(db: Session, user: User) -> tuple[str, RefreshToken]:
    raw = f"rt_{secrets.token_urlsafe(32)}"
    token = RefreshToken(
        user_id=user.id,
        jti=uuid.uuid4(),
        token_hash=_refresh_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_DAYS),
    )
    db.add(token)
    return raw, token


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # Always perform a hash check to keep failure timing broadly similar.
    reference_hash = user.password_hash if user else hash_password("invalid-password-placeholder")
    valid = verify_password(password, reference_hash)
    if not user or not valid or not user.is_active:
        record_audit(
            db,
            event_type="auth.login_failed",
            actor=user if user and user.is_active else None,
            entity_type="user",
            entity_id=user.id if user else None,
            payload={"email": normalize_email(email), "reason": "invalid_credentials"},
        )
        db.commit()
        raise ApiError(401, "AUTH_REQUIRED", "Invalid credentials.")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def revoke_token(db: Session, raw_token: str, user_id: uuid.UUID | None = None) -> None:
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _refresh_hash(raw_token)))
    if not token:
        return
    if user_id is not None and token.user_id != user_id:
        return
    if token.revoked_at is None:
        token.revoked_at = datetime.now(timezone.utc)
        db.commit()


def revoke_all_user_tokens(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[User, str, RefreshToken]:
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _refresh_hash(raw_token)))
    if not token:
        raise ApiError(401, "AUTH_REQUIRED", "Invalid refresh token.")

    if token.revoked_at is not None:
        # Reuse of a rotated token: revoke the whole session family.
        revoke_all_user_tokens(db, token.user_id)
        raise ApiError(401, "AUTH_REQUIRED", "Invalid refresh token.")

    if token.expires_at <= datetime.now(timezone.utc):
        raise ApiError(401, "AUTH_REQUIRED", "Refresh token expired.")

    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        raise ApiError(401, "AUTH_REQUIRED", "Invalid refresh token.")

    new_raw, new_token = issue_refresh_token(db, user)
    token.revoked_at = datetime.now(timezone.utc)
    token.replaced_by_jti = new_token.jti
    db.commit()
    db.refresh(user)
    return user, new_raw, new_token
