from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://astra:astra@localhost:55432/astra_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-secret-for-phase3-only-32-bytes-minimum"
os.environ["DOWNLOAD_SIGNING_KEY"] = "test-download-key-for-phase3-32-bytes"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["OBJECT_STORE_DIR"] = tempfile.mkdtemp(prefix="astra-test-objects-")
os.environ.setdefault("SEED_PASSWORD", "ChangeMe123!")

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.base import SessionLocal, engine
from app.main import app
from app.core.security import reset_login_limits
from app.seed import seed


def _admin_dsn() -> str:
    return TEST_DATABASE_URL.replace("+psycopg", "").rsplit("/", 1)[0] + "/postgres"


def _test_dsn() -> str:
    return TEST_DATABASE_URL.replace("+psycopg", "")


def _ensure_test_database() -> None:
    with psycopg.connect(_admin_dsn(), autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'astra_test'"
        ).fetchone()
        if not exists:
            connection.execute("CREATE DATABASE astra_test")


def _reset_schema() -> None:
    with psycopg.connect(_test_dsn(), autocommit=True) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")


def _run_migrations() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    _ensure_test_database()
    _reset_schema()
    _run_migrations()
    seed()
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_case_data(prepared_database):
    reset_login_limits()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE applications, refresh_tokens, reference_counters, issued_credentials, "
                "audit_events RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def seed_password():
    return os.environ["SEED_PASSWORD"]


def login(client: TestClient, email: str, password: str | None = None) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password or os.environ["SEED_PASSWORD"]},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def applicant_headers(client):
    return login(client, "applicant@example.test")


@pytest.fixture()
def applicant2_headers(client):
    return login(client, "applicant2@example.test")


@pytest.fixture()
def reviewer_headers(client):
    return login(client, "reviewer@example.test")


@pytest.fixture()
def approver_headers(client):
    return login(client, "approver@example.test")


@pytest.fixture()
def admin_headers(client):
    return login(client, "admin@example.test")


@pytest.fixture()
def auditor_headers(client):
    return login(client, "auditor@example.test")


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
