from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from helpers import checklist, create_application, make_text_pdf

from app.db.enums import Role
from app.db.models import Alert, Application, AuditEvent, User
from app.services.reports import render_html

ADVISORY_MARKERS = (
    "advisory",
    "not proof",
    "not an AICTE decision",
)


def _upload_pack(client, headers, application_id, *, valid_until="31/03/2020", affiliation_no="AFF/2026/001"):
    items = {item["code"]: item for item in checklist(client, headers, application_id)}
    contents = {
        "AFFILIATION_CERTIFICATE": [
            "AICTE Affiliation Certificate",
            "Name of Institution: Sunrise Institute of Technology",
            f"Affiliation No: {affiliation_no}",
            "Issued by: State Technical University",
            "Date of Issue: 01/04/2026",
            f"Valid upto: {valid_until}",
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
            f"/api/v1/applications/{application_id}/documents",
            headers=headers,
            files={"file": (f"{code}.pdf", make_text_pdf(lines), "application/pdf")},
            data={
                "document_type": items[code]["accepted_document_types"][0],
                "checklist_item_id": items[code]["id"],
            },
        )
        assert response.status_code == 202, response.text


def _submitted_application(client, headers):
    application = create_application(client, headers)
    _upload_pack(client, headers, application["id"])
    declared = client.put(
        f"/api/v1/applications/{application['id']}/declaration",
        headers=headers,
        json={
            "affiliation_number": "AFF/2026/001",
            "affiliation_valid_until": "2031-03-31",
            "programmes": [
                {"code": "CSE", "name": "B.Tech Computer Science", "level": "UG", "intake": 120}
            ],
            "total_intake": 120,
            "faculty_count": 2,
        },
    )
    assert declared.status_code == 200, declared.text
    submitted = client.post(f"/api/v1/applications/{application['id']}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    return application, submitted.json()


def _application_alerts(client, headers, application_id):
    response = client.get(f"/api/v1/applications/{application_id}/alerts", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_report_export_formats_carry_the_advisory_limitations(
    client, applicant_headers, reviewer_headers, auditor_headers
):
    application, submitted = _submitted_application(client, applicant_headers)
    url = f"/api/v1/applications/{application['id']}/report"

    as_json = client.get(url, headers=reviewer_headers)
    assert as_json.status_code == 200, as_json.text
    assert as_json.headers["content-type"].startswith("application/json")
    assert "attachment" in as_json.headers["content-disposition"]
    assert application["reference_no"] in as_json.headers["content-disposition"]
    report = json.loads(as_json.text)
    assert report["report_version"] == "application-report-1.0"
    assert report["application"]["reference_no"] == application["reference_no"]
    assert report["latest_validation_run"]["id"] == submitted["validation_run_id"]
    assert report["latest_validation_run"]["findings"]
    assert report["declaration"]["verified"] is False
    assert report["declaration"]["affiliation_number"] == "AFF/2026/001"
    assert report["audit"]["chain_valid"] is True
    assert report["audit"]["application_event_count_at_export"] > 0
    assert len(report["limitations"]) >= 5
    joined = " ".join(report["limitations"]).lower()
    assert "not proof" in joined
    assert "synthetic" in joined
    # An expired affiliation produces an advisory alert, so the report carries one.
    assert any(alert["alert_type"] == "EXPIRED_DOCUMENT" for alert in report["alerts"])
    assert all(finding["outcome"] in {"PASS", "FAIL", "INCONCLUSIVE", "NOT_AVAILABLE"}
               for finding in report["latest_validation_run"]["findings"])

    as_markdown = client.get(f"{url}?format=markdown", headers=reviewer_headers)
    assert as_markdown.status_code == 200, as_markdown.text
    assert as_markdown.headers["content-type"].startswith("text/markdown")
    assert as_markdown.text.startswith(f"# Application report — {application['reference_no']}")
    assert "## Limitations" in as_markdown.text
    assert "Applicant-supplied; never verified by the system." in as_markdown.text

    as_html = client.get(f"{url}?format=html", headers=reviewer_headers)
    assert as_html.status_code == 200, as_html.text
    assert as_html.headers["content-type"].startswith("text/html")
    assert as_html.text.startswith("<!DOCTYPE html>")
    assert "Prototype review aid." in as_html.text
    assert "Not an official AICTE document." in as_html.text
    assert "<script" not in as_html.text.lower()

    unsupported = client.get(f"{url}?format=pdf", headers=reviewer_headers)
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "VALIDATION_FAILED"

    events = client.get(
        f"/api/v1/applications/{application['id']}/audit-events", headers=auditor_headers
    ).json()
    exports = [event for event in events if event["event_type"] == "application.report_exported"]
    assert {event["payload"]["format"] for event in exports} == {"json", "markdown", "html"}
    assert all(event["actor_id"] for event in exports)

    assert client.get(url, headers=applicant_headers).status_code == 403


def test_report_is_unavailable_to_another_institution(
    client, applicant_headers, applicant2_headers
):
    application, _ = _submitted_application(client, applicant_headers)
    other = client.get(
        f"/api/v1/applications/{application['id']}/report", headers=applicant2_headers
    )
    # Applicants have no report access at all, so this is a role rejection rather
    # than a scope leak; both outcomes must not disclose the report body.
    assert other.status_code == 403


def test_html_renderer_escapes_exported_values(client, applicant_headers, reviewer_headers):
    application, _ = _submitted_application(client, applicant_headers)
    report = client.get(
        f"/api/v1/applications/{application['id']}/report", headers=reviewer_headers
    ).json()
    report["application"]["institution"]["legal_name"] = "<script>alert('x')</script>"
    report["latest_validation_run"]["findings"][0]["message"] = "<img src=x onerror=alert(1)>"

    rendered = render_html(report)
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<img src=x" not in rendered
    assert "&lt;img src=x" in rendered


def test_alert_disposition_is_recorded_and_dismissals_need_a_note(
    client, applicant_headers, reviewer_headers, auditor_headers
):
    application, _ = _submitted_application(client, applicant_headers)
    alert = _application_alerts(client, reviewer_headers, application["id"])[0]
    url = f"/api/v1/alerts/{alert['id']}/resolve"

    missing_note = client.post(
        url, headers=reviewer_headers, json={"disposition": "FALSE_POSITIVE", "note": "  "}
    )
    assert missing_note.status_code == 400
    assert missing_note.json()["error"]["code"] == "VALIDATION_FAILED"

    accepted_risk_without_note = client.post(
        url, headers=reviewer_headers, json={"disposition": "ACCEPTED_RISK"}
    )
    assert accepted_risk_without_note.status_code == 400

    unknown_disposition = client.post(
        url, headers=reviewer_headers, json={"disposition": "IGNORED", "note": "nope"}
    )
    assert unknown_disposition.status_code == 400
    assert unknown_disposition.json()["error"]["code"] == "VALIDATION_FAILED"

    resolved = client.post(
        url,
        headers=reviewer_headers,
        json={
            "disposition": "FALSE_POSITIVE",
            "note": "Synthetic demo data: the expiry date is intentionally in the past.",
        },
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "RESOLVED"
    assert body["disposition"] == "FALSE_POSITIVE"
    assert body["resolved_by"]
    assert body["payload"]["resolution_note"].startswith("Synthetic demo data")

    detail = client.get(f"/api/v1/alerts/{alert['id']}", headers=reviewer_headers)
    assert detail.status_code == 200
    assert detail.json()["disposition"] == "FALSE_POSITIVE"

    events = client.get(
        f"/api/v1/applications/{application['id']}/audit-events", headers=auditor_headers
    ).json()
    resolved_events = [event for event in events if event["event_type"] == "alert.resolved"]
    assert resolved_events[0]["payload"]["disposition"] == "FALSE_POSITIVE"


def test_alert_detail_is_staff_only_and_scoped_to_the_application(
    client, applicant_headers, reviewer_headers, admin_headers, db
):
    application, _ = _submitted_application(client, applicant_headers)
    alert = _application_alerts(client, reviewer_headers, application["id"])[0]

    assert client.get(f"/api/v1/alerts/{alert['id']}", headers=applicant_headers).status_code == 403
    assert client.get(f"/api/v1/alerts/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"/api/v1/alerts/{alert['id']}", headers=admin_headers).status_code == 200

    # A reviewer assigned to somebody else cannot see the application, so the
    # alert must not leak either.
    stored = db.get(Alert, uuid.UUID(alert["id"]))
    app_row = db.get(Application, stored.application_id)
    app_row.assigned_reviewer_id = db.scalar(
        select(User.id).where(User.role == Role.APPROVER)
    )
    db.commit()
    assert client.get(f"/api/v1/alerts/{alert['id']}", headers=reviewer_headers).status_code == 404


def test_stale_alerts_are_superseded_when_a_new_run_replaces_the_finding(
    client, applicant_headers, reviewer_headers, db
):
    application = create_application(client, applicant_headers)
    _upload_pack(client, applicant_headers, application["id"], valid_until="31/03/2020")
    assert client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    ).status_code == 200

    expired = [
        alert
        for alert in _application_alerts(client, reviewer_headers, application["id"])
        if alert["alert_type"] == "EXPIRED_DOCUMENT"
    ]
    assert expired
    expired_ids = {alert["id"] for alert in expired}

    rectification = client.post(
        f"/api/v1/applications/{application['id']}/review-actions",
        headers=reviewer_headers,
        json={
            "action_type": "REQUEST_RECTIFICATION",
            "note": "Upload a current affiliation certificate.",
        },
    )
    assert rectification.status_code == 200, rectification.text

    item = next(
        entry
        for entry in checklist(client, applicant_headers, application["id"])
        if entry["code"] == "AFFILIATION_CERTIFICATE"
    )
    replaced = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={
            "file": (
                "affiliation-renewed.pdf",
                make_text_pdf(
                    [
                        "AICTE Affiliation Certificate (renewed)",
                        "Name of Institution: Sunrise Institute of Technology",
                        "Affiliation No: AFF/2026/002",
                        "Valid upto: 31/03/2032",
                    ]
                ),
                "application/pdf",
            )
        },
        data={"document_type": "AFFILIATION_CERTIFICATE", "checklist_item_id": item["id"]},
    )
    assert replaced.status_code == 202, replaced.text

    resubmitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert resubmitted.status_code == 200, resubmitted.text

    refreshed = {
        alert["id"]: alert
        for alert in _application_alerts(client, reviewer_headers, application["id"])
    }
    for alert_id in expired_ids:
        row = refreshed[alert_id]
        assert row["status"] == "RESOLVED"
        assert row["disposition"] == "SUPERSEDED"
        assert row["resolved_by"] is None
        assert "Superseded automatically" in row["payload"]["resolution_note"]

    superseded_events = (
        db.query(AuditEvent).filter(AuditEvent.event_type == "alert.superseded").all()
    )
    assert superseded_events
    assert all(event.actor_id is None for event in superseded_events)
