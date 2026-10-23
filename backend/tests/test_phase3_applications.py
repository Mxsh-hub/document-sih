from __future__ import annotations

import re

from fastapi.testclient import TestClient

from helpers import (
    checklist,
    create_application,
    satisfy_required_items,
    upload_pdf,
)


def test_application_creation_snapshots_checklist(client, applicant_headers):
    application = create_application(client, applicant_headers)
    assert re.match(r"^APP-2026-\d{6}$", application["reference_no"])
    assert application["status"] == "DRAFT"

    items = checklist(client, applicant_headers, application["id"])
    assert len(items) == 6
    assert sum(1 for item in items if item["required"]) == 4
    assert {item["code"] for item in items} >= {
        "AFFILIATION_CERTIFICATE",
        "LAND_LEASE_DOCUMENT",
        "FACULTY_DEGREE_CERTIFICATE",
        "INSTITUTIONAL_UNDERTAKING",
    }

    history = client.get(
        f"/api/v1/applications/{application['id']}/status-history", headers=applicant_headers
    )
    assert history.status_code == 200
    assert history.json()[0]["to_status"] == "DRAFT"


def test_duplicate_active_application_is_rejected(client, applicant_headers):
    create_application(client, applicant_headers)
    duplicate = client.post(
        "/api/v1/applications",
        headers=applicant_headers,
        json={"category_code": "EOA", "cycle": "2026-27"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "STATE_CONFLICT"


def test_application_patch_uses_optimistic_concurrency(client, applicant_headers):
    application = create_application(client, applicant_headers)
    url = f"/api/v1/applications/{application['id']}"

    missing = client.patch(url, headers=applicant_headers, json={"cycle": "2027-28"})
    assert missing.status_code == 400

    updated = client.patch(
        url,
        headers={**applicant_headers, "If-Match": "1"},
        json={"cycle": "2027-28"},
    )
    assert updated.status_code == 200
    assert updated.json()["cycle"] == "2027-28"
    assert updated.json()["version"] == 2

    stale = client.patch(
        url,
        headers={**applicant_headers, "If-Match": "1"},
        json={"cycle": "2028-29"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_submit_requires_required_evidence(client, applicant_headers):
    application = create_application(client, applicant_headers)
    submit = client.post(f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers)
    assert submit.status_code == 400
    assert submit.json()["error"]["code"] == "VALIDATION_FAILED"
    assert len(submit.json()["error"]["details"]) == 4

    uploaded = satisfy_required_items(client, applicant_headers, application["id"])
    assert len(uploaded) == 4

    submit = client.post(f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers)
    assert submit.status_code == 200
    assert submit.json()["status"] == "SUBMITTED"

    detail = client.get(f"/api/v1/applications/{application['id']}", headers=applicant_headers)
    assert detail.status_code == 200
    assert detail.json()["checklist"]["satisfied"] == 4
    assert detail.json()["submitted_at"] is not None


def test_withdraw_and_invalid_transition(client, applicant_headers):
    application = create_application(client, applicant_headers)
    withdraw = client.post(
        f"/api/v1/applications/{application['id']}/withdraw",
        headers=applicant_headers,
        json={"reason": "Application created in error."},
    )
    assert withdraw.status_code == 200
    assert withdraw.json()["status"] == "WITHDRAWN"
    assert withdraw.json()["submitted_at"] is not None

    submit = client.post(f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers)
    assert submit.status_code == 409
    assert submit.json()["error"]["code"] == "STATE_CONFLICT"


def test_justification_can_satisfy_submission_validation(client, applicant_headers):
    application = create_application(client, applicant_headers)
    required = [item for item in checklist(client, applicant_headers, application["id"]) if item["required"]]
    for item in required[:3]:
        uploaded = upload_pdf(
            client,
            applicant_headers,
            application["id"],
            document_type=item["accepted_document_types"][0],
            checklist_item_id=item["id"],
        )
        assert uploaded.status_code == 202

    last = required[3]
    response = client.patch(
        f"/api/v1/applications/{application['id']}/checklist/{last['id']}",
        headers=applicant_headers,
        json={"justification": "Renewal receipt is attached separately; certificate is in process."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    # The justification is visible but the item remains pending for reviewer assessment.
    submit = client.post(f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers)
    assert submit.status_code == 200


def test_reviewer_can_waive_after_submission(client, applicant_headers, reviewer_headers):
    application = create_application(client, applicant_headers)
    satisfy_required_items(client, applicant_headers, application["id"])
    assert client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    ).status_code == 200
    item = checklist(client, applicant_headers, application["id"])[0]

    no_rationale = client.patch(
        f"/api/v1/applications/{application['id']}/checklist/{item['id']}",
        headers=reviewer_headers,
        json={"status": "WAIVED"},
    )
    assert no_rationale.status_code == 400

    waived = client.patch(
        f"/api/v1/applications/{application['id']}/checklist/{item['id']}",
        headers=reviewer_headers,
        json={"status": "WAIVED", "justification": "Verified against the synthetic record bundle."},
    )
    assert waived.status_code == 200
    assert waived.json()["status"] == "WAIVED"


def test_application_persists_across_client_instances(client, applicant_headers):
    application = create_application(client, applicant_headers)
    fresh = TestClient(client.app)
    response = fresh.get(f"/api/v1/applications/{application['id']}", headers=applicant_headers)
    assert response.status_code == 200
    assert response.json()["reference_no"] == application["reference_no"]


def test_applicant_cannot_filter_by_institution(client, applicant_headers, db):
    from sqlalchemy import select

    from app.db.models import Institution

    institution_id = db.scalar(select(Institution.id))
    response = client.get(
        f"/api/v1/applications?institution_id={institution_id}", headers=applicant_headers
    )
    assert response.status_code == 403
