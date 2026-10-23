from __future__ import annotations

from helpers import checklist, create_application, make_text_pdf


def _upload(client, headers, application_id, item, lines):
    return client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        files={"file": (f"{item['code']}.pdf", make_text_pdf(lines), "application/pdf")},
        data={
            "document_type": item["accepted_document_types"][0],
            "checklist_item_id": item["id"],
        },
    )


def _upload_complete_pack(client, headers, application_id, *, valid_until="31/03/2031", name="Sunrise Institute of Technology"):
    items = {item["code"]: item for item in checklist(client, headers, application_id)}
    contents = {
        "AFFILIATION_CERTIFICATE": [
            "AICTE Affiliation Certificate",
            f"Name of Institution: {name}",
            "Affiliation No: AFF/2026/001",
            "Issued by: State Technical University",
            "Date of Issue: 01/04/2026",
            f"Valid upto: {valid_until}",
        ],
        "LAND_LEASE_DOCUMENT": [
            "Registered Land Lease Deed",
            f"Name of Institution: {name}",
            "Land Area: 2.5 acres",
            "Date of Issue: 15/05/2026",
        ],
        "FACULTY_DEGREE_CERTIFICATE": [
            "University Degree Certificate",
            "Name: Dr. A. Sharma",
            "Degree: Ph.D. (Computer Science)",
            "Issued by: State Technical University",
            "Date of Issue: 12/06/2026",
        ],
        "INSTITUTIONAL_UNDERTAKING": [
            "Institutional Undertaking",
            f"Name of Institution: {name}",
            "Issued by: The Registrar",
            "Date of Issue: 20/06/2026",
        ],
    }
    for code, lines in contents.items():
        response = _upload(client, headers, application_id, items[code], lines)
        assert response.status_code == 202, response.text


def test_submission_runs_versioned_validation_and_links_evidence(client, applicant_headers):
    application = create_application(client, applicant_headers)
    _upload_complete_pack(client, applicant_headers, application["id"])
    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submitted.status_code == 200, submitted.text
    run_id = submitted.json()["validation_run_id"]
    assert run_id

    run = client.get(f"/api/v1/validation-runs/{run_id}", headers=applicant_headers)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "COMPLETED"
    assert body["engine_version"].startswith("rules-phase5")
    assert body["summary"]["counts"]["PASS"] == 9
    assert body["summary"]["records_synthetic"] is True
    assert body["summary"]["synthetic_rules"] is True
    for finding in body["findings"]:
        assert finding["outcome"] == "PASS", finding
    evidence_codes = {finding["code"] for finding in body["findings"] if finding["evidence"]}
    assert {"AFFILIATION_VALIDITY", "INSTITUTION_NAME_CONSISTENCY", "PREVIOUS_APPROVAL_STATUS"} <= evidence_codes

    # The application remains submitted; findings are advisory inputs to human review.
    detail = client.get(f"/api/v1/applications/{application['id']}", headers=applicant_headers)
    assert detail.json()["status"] == "SUBMITTED"


def test_expired_affiliation_finding_is_not_an_automatic_rejection(client, applicant_headers):
    application = create_application(client, applicant_headers)
    _upload_complete_pack(
        client, applicant_headers, application["id"], valid_until="31/03/2020"
    )
    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submitted.status_code == 200
    run = client.get(
        f"/api/v1/validation-runs/{submitted.json()['validation_run_id']}",
        headers=applicant_headers,
    ).json()
    expiry = next(item for item in run["findings"] if item["code"] == "AFFILIATION_VALIDITY")
    assert expiry["outcome"] == "FAIL"
    assert expiry["severity"] == "BLOCKING"
    assert expiry["evidence"][0]["metadata_json"]["field"] == "valid_until"
    assert client.get(
        f"/api/v1/applications/{application['id']}", headers=applicant_headers
    ).json()["status"] == "SUBMITTED"


def test_institution_name_mismatch_requires_review(client, applicant_headers):
    application = create_application(client, applicant_headers)
    _upload_complete_pack(
        client, applicant_headers, application["id"], name="Unrelated Valley College"
    )
    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    run = client.get(
        f"/api/v1/validation-runs/{submitted.json()['validation_run_id']}",
        headers=applicant_headers,
    ).json()
    consistency = next(
        item for item in run["findings"] if item["code"] == "INSTITUTION_NAME_CONSISTENCY"
    )
    assert consistency["outcome"] == "FAIL"
    assert consistency["details"]["institution_profile"] == "Sunrise Institute of Technology (Synthetic)"


def test_manual_validation_permissions_and_isolation(
    client, applicant_headers, applicant2_headers, reviewer_headers
):
    application = create_application(client, applicant_headers)
    _upload_complete_pack(client, applicant_headers, application["id"])
    assert client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    ).status_code == 200

    applicant_trigger = client.post(
        f"/api/v1/applications/{application['id']}/validation-runs",
        headers=applicant_headers,
    )
    assert applicant_trigger.status_code == 403

    staff_trigger = client.post(
        f"/api/v1/applications/{application['id']}/validation-runs",
        headers=reviewer_headers,
    )
    assert staff_trigger.status_code == 201, staff_trigger.text
    run_id = staff_trigger.json()["id"]

    hidden = client.get(f"/api/v1/validation-runs/{run_id}", headers=applicant2_headers)
    assert hidden.status_code == 404

    listing = client.get(
        f"/api/v1/applications/{application['id']}/validation-runs",
        headers=reviewer_headers,
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_admin_can_version_and_configure_rules(client, admin_headers, applicant_headers):
    rule_sets = client.get("/api/v1/admin/rule-sets", headers=admin_headers)
    assert rule_sets.status_code == 200
    eoa = next(item for item in rule_sets.json() if item["code"] == "EOA-SYNTHETIC-RULES")
    assert len(eoa["rules"]) == 9

    created = client.post(
        "/api/v1/admin/rule-sets",
        headers=admin_headers,
        json={
            "code": "EOA-SYNTHETIC-RULES",
            "name": "Synthetic EoA rules draft",
            "category_id": eoa["category_id"],
            "version": 99,
            "source_citation": "Synthetic draft only.",
            "rules": [
                {
                    "code": "FACULTY_APPROVED_MINIMUM",
                    "title": "Configurable faculty threshold",
                    "rule_type": "INSTITUTION_RECORD",
                    "severity": "ADVISORY",
                    "config": {"record_type": "faculty", "minimum": 4, "statuses": ["APPROVED"]},
                    "sort_order": 1,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DRAFT"
    rule_id = created.json()["rules"][0]["id"]

    patched = client.patch(
        f"/api/v1/admin/rules/{rule_id}",
        headers=admin_headers,
        json={"config": {"record_type": "faculty", "minimum": 1, "statuses": ["APPROVED"]}},
    )
    assert patched.status_code == 200
    assert patched.json()["rules"][0]["config"]["minimum"] == 1

    non_admin = client.get("/api/v1/admin/rule-sets", headers=applicant_headers)
    assert non_admin.status_code == 403
