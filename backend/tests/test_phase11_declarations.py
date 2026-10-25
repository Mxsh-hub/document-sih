from __future__ import annotations

from helpers import checklist, create_application, make_text_pdf

DECLARATION_RULES = (
    "AFFILIATION_DECLARATION_MATCH",
    "PROGRAMME_DECLARATION_MATCH",
    "FACULTY_COUNT_DECLARATION_MATCH",
)


def _upload_pack(
    client,
    headers,
    application_id,
    *,
    name="Sunrise Institute of Technology",
    affiliation_no="AFF/2026/001",
    valid_until="31/03/2031",
):
    items = {item["code"]: item for item in checklist(client, headers, application_id)}
    contents = {
        "AFFILIATION_CERTIFICATE": [
            "AICTE Affiliation Certificate",
            f"Name of Institution: {name}",
            f"Affiliation No: {affiliation_no}",
            "Issued by: State Technical University",
            "Date of Issue: 01/04/2026",
            f"Valid upto: {valid_until}",
        ],
        "LAND_LEASE_DOCUMENT": [
            "Registered Land Lease Deed",
            f"Name of Institution: {name}",
            "Land Area: 2.5 acres",
        ],
        "FACULTY_DEGREE_CERTIFICATE": [
            "University Degree Certificate",
            "Name: Dr. A. Sharma",
            "Degree: Ph.D. (Computer Science)",
        ],
        "INSTITUTIONAL_UNDERTAKING": [
            "Institutional Undertaking",
            f"Name of Institution: {name}",
            "Issued by: The Registrar",
        ],
    }
    for code, lines in contents.items():
        response = client.post(
            f"/api/v1/applications/{application_id}/documents",
            headers=headers,
            files={"file": (f"{code}.pdf", make_text_pdf(lines), "application/pdf")},
            data={
                "document_type": items[code]["accepted_document_types"][0],
                "checklist_item_id": items[code]["id"],
            },
        )
        assert response.status_code == 202, response.text


def _declaration(**overrides):
    payload = {
        "affiliation_number": "AFF/2026/001",
        "affiliation_valid_until": "2031-03-31",
        "programmes": [
            {
                "code": "CSE",
                "name": "B.Tech Computer Science and Engineering",
                "level": "UG",
                "intake": 120,
            },
            {
                "code": "ECE",
                "name": "B.Tech Electronics and Communication Engineering",
                "level": "UG",
                "intake": 60,
            },
        ],
        "total_intake": 180,
        "faculty_count": 2,
    }
    payload.update(overrides)
    return payload


def _submit_and_run(client, headers, application_id):
    submitted = client.post(
        f"/api/v1/applications/{application_id}/submit", headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    run = client.get(
        f"/api/v1/validation-runs/{submitted.json()['validation_run_id']}", headers=headers
    )
    assert run.status_code == 200, run.text
    body = run.json()
    return body, {finding["code"]: finding for finding in body["findings"]}


def test_declaration_is_optional_versioned_and_draft_only(
    client, applicant_headers, applicant2_headers, reviewer_headers, admin_headers
):
    application = create_application(client, applicant_headers)
    url = f"/api/v1/applications/{application['id']}/declaration"

    empty = client.get(url, headers=applicant_headers)
    assert empty.status_code == 200, empty.text
    assert empty.json()["declaration"] is None

    first = client.put(
        url,
        headers=applicant_headers,
        json=_declaration(
            programmes=[
                {"code": " cse ", "name": None, "level": None, "intake": 120},
                {"code": "CSE", "name": "Duplicate", "level": None, "intake": 999},
            ]
        ),
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["version"] == 1
    assert body["application_id"] == application["id"]
    assert body["declared_by"]
    # Codes are normalised to upper case and duplicates collapse to one entry.
    assert [item["code"] for item in body["programmes"]] == ["CSE"]

    second = client.put(
        url,
        headers=applicant_headers,
        json=_declaration(
            programmes=[{"code": "CSE", "name": None, "level": None, "intake": 120}],
            faculty_count=3,
        ),
    )
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2
    assert second.json()["faculty_count"] == 3

    # Staff may read it; another institution cannot even see the application.
    # Reviewers are scoped to submitted work, so draft reads are exercised as admin.
    admin_view = client.get(url, headers=admin_headers)
    assert admin_view.status_code == 200
    assert admin_view.json()["declaration"]["version"] == 2
    assert client.get(url, headers=applicant2_headers).status_code == 404
    assert client.put(url, headers=admin_headers, json=_declaration()).status_code == 403

    audit = client.get(
        f"/api/v1/applications/{application['id']}/audit-events", headers=admin_headers
    )
    assert audit.status_code == 200, audit.text
    events = [item for item in audit.json() if item["event_type"] == "application.declaration_saved"]
    assert len(events) == 2
    newest = max(events, key=lambda item: item["sequence"])
    assert newest["payload"]["version"] == 2
    assert newest["payload"]["changed_fields"] == ["faculty_count"]

    _upload_pack(client, applicant_headers, application["id"])
    assert client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    ).status_code == 200
    reviewer_view = client.get(url, headers=reviewer_headers)
    assert reviewer_view.status_code == 200
    assert reviewer_view.json()["declaration"]["version"] == 2
    locked = client.put(url, headers=applicant_headers, json=_declaration())
    assert locked.status_code == 409


def test_matching_declaration_makes_all_checks_pass(client, applicant_headers):
    application = create_application(client, applicant_headers)
    _upload_pack(client, applicant_headers, application["id"])
    saved = client.put(
        f"/api/v1/applications/{application['id']}/declaration",
        headers=applicant_headers,
        json=_declaration(),
    )
    assert saved.status_code == 200, saved.text

    run, findings = _submit_and_run(client, applicant_headers, application["id"])
    assert run["summary"]["total"] == 12
    assert run["summary"]["counts"]["PASS"] == 12
    assert run["summary"]["counts"]["NOT_AVAILABLE"] == 0

    for code in DECLARATION_RULES:
        assert findings[code]["outcome"] == "PASS", findings[code]
        assert "DECLARATION" in {item["evidence_type"] for item in findings[code]["evidence"]}

    affiliation = findings["AFFILIATION_DECLARATION_MATCH"]
    assert affiliation["details"]["declared"]["affiliation_number"] == "AFF/2026/001"
    assert affiliation["details"]["extracted"]["valid_until"] == "2031-03-31"
    assert "EXTRACTED_FIELD" in {item["evidence_type"] for item in affiliation["evidence"]}
    assert "RECORD" in {
        item["evidence_type"] for item in findings["PROGRAMME_DECLARATION_MATCH"]["evidence"]
    }

    # Advisory only: a clean run does not change the application's status.
    detail = client.get(
        f"/api/v1/applications/{application['id']}", headers=applicant_headers
    )
    assert detail.json()["status"] == "SUBMITTED"


def test_declaration_mismatches_are_advisory_findings(client, applicant_headers, reviewer_headers):
    application = create_application(client, applicant_headers)
    _upload_pack(client, applicant_headers, application["id"])
    saved = client.put(
        f"/api/v1/applications/{application['id']}/declaration",
        headers=applicant_headers,
        json=_declaration(
            affiliation_number="AFF/OTHER/777",
            affiliation_valid_until="2030-03-31",
            programmes=[{"code": "MEC", "name": "B.Tech Mechanical Engineering", "level": "UG", "intake": 60}],
            total_intake=30,
            faculty_count=5,
        ),
    )
    assert saved.status_code == 200, saved.text

    run, findings = _submit_and_run(client, applicant_headers, application["id"])
    for code in DECLARATION_RULES:
        assert findings[code]["outcome"] == "FAIL", findings[code]
        assert findings[code]["severity"] == "ADVISORY"

    affiliation = findings["AFFILIATION_DECLARATION_MATCH"]["details"]
    mismatched_fields = {item["field"] for item in affiliation["mismatches"]}
    assert {"affiliation_number", "valid_until"} <= mismatched_fields

    programme = findings["PROGRAMME_DECLARATION_MATCH"]["details"]
    assert programme["missing_in_records"] == ["MEC"]
    assert programme["total_intake_mismatch"] is True
    assert programme["advisory"] is True

    faculty = findings["FACULTY_COUNT_DECLARATION_MATCH"]["details"]
    assert faculty["declared_faculty_count"] == 5
    assert faculty["record_faculty_count"] == 2
    assert faculty["difference"] == 3
    assert faculty["tolerance"] == 0

    assert client.get(
        f"/api/v1/applications/{application['id']}", headers=applicant_headers
    ).json()["status"] == "SUBMITTED"

    overview = client.get(
        f"/api/v1/applications/{application['id']}/review-overview", headers=reviewer_headers
    )
    assert overview.status_code == 200, overview.text
    assert overview.json()["declaration"]["faculty_count"] == 5


def test_missing_declaration_reports_not_available(client, applicant_headers):
    application = create_application(client, applicant_headers)
    _upload_pack(client, applicant_headers, application["id"])
    run, findings = _submit_and_run(client, applicant_headers, application["id"])
    assert run["summary"]["counts"]["NOT_AVAILABLE"] == 3
    for code in DECLARATION_RULES:
        assert findings[code]["outcome"] == "NOT_AVAILABLE", findings[code]
