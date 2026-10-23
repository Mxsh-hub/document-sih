from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.config import Settings, settings
from app.core.errors import ApiError

_lock = threading.Lock()
_login_failures: dict[str, deque[float]] = defaultdict(deque)


def _key(client_ip: str, email: str) -> str:
    return f"{client_ip}|{email.strip().lower()}"


def check_login_allowed(client_ip: str, email: str) -> None:
    now = time.monotonic()
    key = _key(client_ip, email)
    with _lock:
        attempts = _login_failures[key]
        while attempts and now - attempts[0] > settings.LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= settings.LOGIN_MAX_FAILURES:
            raise ApiError(
                429,
                "RATE_LIMITED",
                "Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(settings.LOGIN_WINDOW_SECONDS)},
            )


def record_login_failure(client_ip: str, email: str) -> None:
    with _lock:
        _login_failures[_key(client_ip, email)].append(time.monotonic())


def clear_login_failures(client_ip: str, email: str) -> None:
    with _lock:
        _login_failures.pop(_key(client_ip, email), None)


def reset_login_limits() -> None:
    with _lock:
        _login_failures.clear()


def validate_security_config(config: Settings = settings) -> None:
    if len(config.JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be configured with at least 32 characters.")
    if len(config.DOWNLOAD_SIGNING_KEY) < 32:
        raise RuntimeError("DOWNLOAD_SIGNING_KEY must be configured with at least 32 characters.")
    if config.is_production:
        if any(origin.strip() == "*" for origin in config.cors_origins):
            raise RuntimeError("Wildcard CORS origins are not permitted in production.")
        if config.STORAGE_BACKEND != "s3":
            raise RuntimeError("Production deployments must use the s3 storage backend.")
