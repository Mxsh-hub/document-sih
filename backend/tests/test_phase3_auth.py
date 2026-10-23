from __future__ import annotations

import uuid

from helpers import create_application, satisfy_required_items
from conftest import login


def test_login_me_and_missing_token(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant@example.test", "password": "ChangeMe123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "Bearer"
    assert data["user"]["role"] == "APPLICANT"
    assert data["user"]["institution_id"]

    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert "application:read:own" in me.json()["scopes"]

    missing = client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTH_REQUIRED"


def test_refresh_rotation_and_reuse_revokes_family(client):
    first = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant@example.test", "password": "ChangeMe123!"},
    )
    refresh_one = first.json()["refresh_token"]

    second = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_one})
    assert second.status_code == 200
    refresh_two = second.json()["refresh_token"]
    assert refresh_two != refresh_one

    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_one})
    assert reuse.status_code == 401

    after_family_revocation = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_two})
    assert after_family_revocation.status_code == 401


def test_applicant_cannot_read_institutional_records(client, applicant_headers, db):
    institution_id = client.get("/api/v1/institutions/me", headers=applicant_headers).json()["id"]
    response = client.get(f"/api/v1/institutions/{institution_id}/records", headers=applicant_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_applicant_isolation_returns_404(client, applicant_headers, applicant2_headers):
    application = create_application(client, applicant_headers)
    response = client.get(f"/api/v1/applications/{application['id']}", headers=applicant2_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_reviewer_sees_only_non_draft_applications(
    client, applicant_headers, reviewer_headers
):
    application = create_application(client, applicant_headers)
    draft_list = client.get("/api/v1/applications", headers=reviewer_headers)
    assert draft_list.status_code == 200
    assert draft_list.json()["total"] == 0

    satisfy_required_items(client, applicant_headers, application["id"])
    submit = client.post(f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers)
    assert submit.status_code == 200
    submitted_list = client.get("/api/v1/applications", headers=reviewer_headers)
    assert submitted_list.status_code == 200
    assert submitted_list.json()["total"] == 1


def test_admin_provisioning_rules(client, admin_headers, applicant_headers):
    institution_id = client.get("/api/v1/institutions/me", headers=applicant_headers).json()["id"]
    email = f"new-applicant-{uuid.uuid4().hex[:8]}@example.test"

    missing_institution = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": email,
            "full_name": "New Applicant",
            "role": "APPLICANT",
            "password": "StrongPassword123!",
        },
    )
    assert missing_institution.status_code == 400

    staff_with_institution = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": f"staff-{uuid.uuid4().hex[:8]}@example.test",
            "full_name": "Staff",
            "role": "REVIEWER",
            "institution_id": institution_id,
            "password": "StrongPassword123!",
        },
    )
    assert staff_with_institution.status_code == 400

    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": email,
            "full_name": "New Applicant",
            "role": "APPLICANT",
            "institution_id": institution_id,
            "password": "StrongPassword123!",
        },
    )
    assert created.status_code == 201
    assert created.json()["email"] == email

    login_headers = login(client, email, "StrongPassword123!")
    assert client.get("/api/v1/auth/me", headers=login_headers).status_code == 200


def test_last_admin_cannot_be_demoted(client, admin_headers, db):
    from sqlalchemy import select

    from app.db.models import User

    admin = db.scalar(select(User).where(User.email == "admin@example.test"))
    response = client.patch(
        f"/api/v1/admin/users/{admin.id}",
        headers=admin_headers,
        json={"role": "REVIEWER"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"
