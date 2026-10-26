from __future__ import annotations

import uuid


def test_synthetic_record_bundle_and_type_access(
    client, applicant_headers, reviewer_headers, auditor_headers
):
    institution_id = client.get("/api/v1/institutions/me", headers=applicant_headers).json()["id"]
    bundle = client.get(f"/api/v1/institutions/{institution_id}/records", headers=reviewer_headers)
    assert bundle.status_code == 200
    body = bundle.json()
    assert body["synthetic"] is True
    assert body["source"] == "synthetic-aicte-records-v1"
    assert set(body["records"]) == {
        "approvals",
        "programmes",
        "faculty",
        "deficiencies",
        "ter",
        "accreditations",
        "nocs",
    }
    assert body["records"]["ter"]["items"][0]["synthetic"] is True

    typed = client.get(
        f"/api/v1/institutions/{institution_id}/records/ter", headers=auditor_headers
    )
    assert typed.status_code == 200
    assert typed.json()["items"][0]["status"] == "PAID"

    forbidden = client.get(
        f"/api/v1/institutions/{institution_id}/records", headers=applicant_headers
    )
    assert forbidden.status_code == 403

    unknown = client.get(
        f"/api/v1/institutions/{institution_id}/records/not-a-type", headers=reviewer_headers
    )
    assert unknown.status_code == 404


def test_admin_can_create_and_activate_checklist_template(client, admin_headers):
    code = f"CAT{uuid.uuid4().hex[:6].upper()}"
    category = client.post(
        "/api/v1/admin/categories",
        headers=admin_headers,
        json={"code": code, "name": "Synthetic category"},
    )
    assert category.status_code == 201
    category_id = category.json()["id"]

    template = client.post(
        "/api/v1/admin/checklist-templates",
        headers=admin_headers,
        json={
            "category_id": category_id,
            "version": 1,
            "source_citation": "Synthetic test citation",
            "items": [
                {
                    "code": "TEST_DOCUMENT",
                    "title": "Test document",
                    "required": True,
                    "accepted_document_types": ["OTHER"],
                    "rule_codes": ["TEST_RULE"],
                    "sort_order": 1,
                }
            ],
        },
    )
    assert template.status_code == 201, template.text
    assert template.json()["status"] == "DRAFT"

    activated = client.post(
        f"/api/v1/admin/checklist-templates/{template.json()['id']}/activate",
        headers=admin_headers,
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"

    listing = client.get(
        f"/api/v1/admin/checklist-templates?category_id={category_id}", headers=admin_headers
    )
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == template.json()["id"]


def test_admin_can_create_and_update_institution(client, admin_headers, auditor_headers):
    payload = {
        "legal_name": f"Synthetic Institute {uuid.uuid4().hex[:6]}",
        "short_name": "SI",
        "aicte_permanent_id": f"SYN-TEST-{uuid.uuid4().hex[:10]}",
        "institute_type": "Private unaided",
        "state": "Maharashtra",
        "synthetic": True,
    }
    created = client.post("/api/v1/institutions", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    institution_id = created.json()["id"]

    listing = client.get("/api/v1/institutions", headers=auditor_headers)
    assert listing.status_code == 200
    assert any(item["id"] == institution_id for item in listing.json())

    updated = client.patch(
        f"/api/v1/institutions/{institution_id}",
        headers=admin_headers,
        json={"short_name": "SI-2"},
    )
    assert updated.status_code == 200
    assert updated.json()["short_name"] == "SI-2"
