from __future__ import annotations

import uuid

from helpers import checklist, create_application, make_text_pdf, satisfy_required_items

from app.db.enums import DocumentStatus
from app.db.models import AuditEvent, Document

DECLARATION = {
    "affiliation_number": "AFF/2026/001",
    "affiliation_valid_until": "2031-03-31",
    "programmes": [
        {"code": "CSE", "name": "B.Tech Computer Science", "level": "UG", "intake": 120}
    ],
    "total_intake": 120,
    "faculty_count": 2,
}


def _self_check(client, headers, application_id):
    return client.get(f"/api/v1/applications/{application_id}/self-check", headers=headers)


def _codes(body):
    return {check["code"] for check in body["checks"]}


def _audit_count(db, application_id):
    return db.query(AuditEvent).filter(AuditEvent.application_id == application_id).count()


def test_self_check_reports_blocking_items_then_clears(client, applicant_headers, db):
    application = create_application(client, applicant_headers)

    first = _self_check(client, applicant_headers, application["id"])
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["can_submit"] is False
    assert body["application_id"] == application["id"]
    assert body["reference_no"] == application["reference_no"]
    assert body["status"] == "DRAFT"
    assert body["check_version"] == "self-check-1.0"
    assert body["counts"]["BLOCKING"] >= 1

    required_codes = {
        item["code"] for item in checklist(client, applicant_headers, application["id"]) if item["required"]
    }
    blocking_codes = {
        check["code"].split(":", 1)[1] for check in body["checks"] if check["level"] == "BLOCKING"
    }
    # The preview must name exactly the items the submit gate would reject.
    assert blocking_codes == required_codes
    assert "CHECKLIST_COMPLETE" not in _codes(body)
    assert "VALIDATION_NOT_RUN" in _codes(body)
    assert "DECLARATION_MISSING" in _codes(body)
    assert body["advisory_note"].startswith("This self-check previews")

    satisfy_required_items(client, applicant_headers, application["id"])

    second = _self_check(client, applicant_headers, application["id"]).json()
    assert second["can_submit"] is True
    assert second["counts"]["BLOCKING"] == 0
    assert "CHECKLIST_COMPLETE" in _codes(second)
    assert not any(check["code"].startswith("CHECKLIST_MISSING:") for check in second["checks"])

    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submitted.status_code == 200, submitted.text


def test_self_check_does_not_write_audit_events(client, applicant_headers, db):
    application = create_application(client, applicant_headers)
    before = _audit_count(db, application["id"])

    body = _self_check(client, applicant_headers, application["id"])
    assert body.status_code == 200
    assert _audit_count(db, application["id"]) == before

    # A repeat call is still side-effect free.
    assert _self_check(client, applicant_headers, application["id"]).status_code == 200
    assert _audit_count(db, application["id"]) == before


def test_self_check_tracks_the_structured_declaration(client, applicant_headers):
    application = create_application(client, applicant_headers)
    url = f"/api/v1/applications/{application['id']}/self-check"

    missing = client.get(url, headers=applicant_headers).json()
    assert "DECLARATION_MISSING" in _codes(missing)

    partial = client.put(
        f"/api/v1/applications/{application['id']}/declaration",
        headers=applicant_headers,
        json={"affiliation_number": "AFF/2026/001"},
    )
    assert partial.status_code == 200, partial.text
    incomplete = client.get(url, headers=applicant_headers).json()
    assert "DECLARATION_INCOMPLETE" in _codes(incomplete)
    detail = next(check for check in incomplete["checks"] if check["code"] == "DECLARATION_INCOMPLETE")
    assert "affiliation validity date" in detail["details"]["missing"]
    assert "faculty count" in detail["details"]["missing"]
    assert incomplete["can_submit"] is False  # checklist is still empty

    complete = client.put(
        f"/api/v1/applications/{application['id']}/declaration",
        headers=applicant_headers,
        json=DECLARATION,
    )
    assert complete.status_code == 200, complete.text
    ready = client.get(url, headers=applicant_headers).json()
    assert "DECLARATION_PRESENT" in _codes(ready)
    present = next(check for check in ready["checks"] if check["code"] == "DECLARATION_PRESENT")
    assert "does not verify the declaration" in present["message"]


def test_self_check_is_unavailable_once_submitted(client, applicant_headers):
    application = create_application(client, applicant_headers)
    satisfy_required_items(client, applicant_headers, application["id"])
    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submitted.status_code == 200, submitted.text

    response = _self_check(client, applicant_headers, application["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"


def test_self_check_is_scoped_to_the_owning_institution(
    client, applicant_headers, applicant2_headers
):
    application = create_application(client, applicant_headers)
    assert _self_check(client, applicant2_headers, application["id"]).status_code == 404


def test_self_check_reports_latest_findings_as_advisory_warnings(
    client, applicant_headers, reviewer_headers
):
    application = create_application(client, applicant_headers)
    items = {item["code"]: item for item in checklist(client, applicant_headers, application["id"])}
    contents = {
        "AFFILIATION_CERTIFICATE": [
            "AICTE Affiliation Certificate",
            "Name of Institution: Sunrise Institute of Technology",
            "Affiliation No: AFF/2026/001",
            "Date of Issue: 01/04/2026",
            "Valid upto: 31/03/2020",
        ],
        "LAND_LEASE_DOCUMENT": [
            "Registered Land Lease Deed",
            "Name of Institution: Sunrise Institute of Technology",
            "Land Area: 2.5 acres",
        ],
        "FACULTY_DEGREE_CERTIFICATE": [
            "University Degree Certificate",
            "Name: Dr. A. Sharma",
            "Degree: Ph.D. (Computer Science)",
        ],
        "INSTITUTIONAL_UNDERTAKING": [
            "Institutional Undertaking",
            "Name of Institution: Sunrise Institute of Technology",
            "Issued by: The Registrar",
        ],
    }
    for code, lines in contents.items():
        response = client.post(
            f"/api/v1/applications/{application['id']}/documents",
            headers=applicant_headers,
            files={"file": (f"{code}.pdf", make_text_pdf(lines), "application/pdf")},
            data={
                "document_type": items[code]["accepted_document_types"][0],
                "checklist_item_id": items[code]["id"],
            },
        )
        assert response.status_code == 202, response.text

    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submitted.status_code == 200, submitted.text

    # Put the application back into a self-checkable state the way a reviewer would.
    rectification = client.post(
        f"/api/v1/applications/{application['id']}/review-actions",
        headers=reviewer_headers,
        json={"action_type": "REQUEST_RECTIFICATION", "note": "Affiliation certificate has expired."},
    )
    assert rectification.status_code == 200, rectification.text

    body = _self_check(client, applicant_headers, application["id"]).json()
    assert body["status"] == "RECTIFICATION_REQUESTED"
    assert "VALIDATION_ATTENTION" in _codes(body)
    warning = next(check for check in body["checks"] if check["code"] == "VALIDATION_ATTENTION")
    assert warning["level"] == "WARNING"
    assert "AFFILIATION_VALIDITY" in warning["details"]["rule_codes"]
    # Advisory only: warnings never block submission.
    assert body["counts"]["BLOCKING"] == 0
    assert body["can_submit"] is True


def test_self_check_does_not_block_on_a_failed_document_outside_the_gate(
    client, applicant_headers, db
):
    """A document problem is a warning; only checklist items can block submit.

    ``submit_application`` rejects on missing checklist items, not on arbitrary
    document states. The preview must not claim a failure the real gate would
    accept, otherwise applicants chase a phantom blocker.
    """
    application = create_application(client, applicant_headers)
    satisfy_required_items(client, applicant_headers, application["id"])

    uploaded = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("unused.pdf", make_text_pdf(["Synthetic unused document"]), "application/pdf")},
        data={"document_type": "OTHER"},
    )
    assert uploaded.status_code == 202, uploaded.text
    payload = uploaded.json()
    document = db.get(Document, uuid.UUID(payload["document_id"]))
    document.status = DocumentStatus.FAILED
    db.commit()

    body = _self_check(client, applicant_headers, application["id"]).json()
    assert body["can_submit"] is True
    assert body["counts"]["BLOCKING"] == 0
    entry = next(
        check for check in body["checks"] if check["code"] == f"DOCUMENT_REJECTED:{document.id}"
    )
    assert entry["level"] == "WARNING"

    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submitted.status_code == 200, submitted.text
