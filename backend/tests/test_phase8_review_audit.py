from __future__ import annotations

from helpers import checklist, create_application, make_text_pdf


def _upload_complete_pack(client, headers, application_id, *, valid_until="31/03/2031"):
    items = {item["code"]: item for item in checklist(client, headers, application_id)}
    contents = {
        "AFFILIATION_CERTIFICATE": [
            "AICTE Affiliation Certificate",
            "Name of Institution: Sunrise Institute of Technology",
            "Affiliation No: AFF/2026/001",
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
            "Issued by: State Technical University",
        ],
        "INSTITUTIONAL_UNDERTAKING": [
            "Institutional Undertaking",
            "Name of Institution: Sunrise Institute of Technology",
            "Issued by: The Registrar",
            "Date of Issue: 20/06/2026",
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


def _submit(client, headers, application_id):
    response = client.post(f"/api/v1/applications/{application_id}/submit", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_review_assignment_alerts_rectification_and_final_decision(
    client, applicant_headers, reviewer_headers, approver_headers, auditor_headers
):
    application = create_application(client, applicant_headers)
    _upload_complete_pack(client, applicant_headers, application["id"], valid_until="31/03/2020")
    _submit(client, applicant_headers, application["id"])

    alerts = client.get(
        f"/api/v1/applications/{application['id']}/alerts", headers=reviewer_headers
    )
    assert alerts.status_code == 200
    assert any(item["alert_type"] == "EXPIRED_DOCUMENT" for item in alerts.json())

    assigned = client.post(
        f"/api/v1/applications/{application['id']}/review-actions",
        headers=reviewer_headers,
        json={"action_type": "ASSIGN", "note": "Assigned to self for review."},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["to_status"] == "UNDER_REVIEW"
    detail = client.get(f"/api/v1/applications/{application['id']}", headers=reviewer_headers)
    assert detail.json()["status"] == "UNDER_REVIEW"

    note = client.post(
        f"/api/v1/applications/{application['id']}/review-actions",
        headers=reviewer_headers,
        json={"action_type": "NOTE", "note": "Affiliation expiry requires clarification."},
    )
    assert note.status_code == 200

    rectification = client.post(
        f"/api/v1/applications/{application['id']}/review-actions",
        headers=reviewer_headers,
        json={
            "action_type": "REQUEST_RECTIFICATION",
            "note": "Upload a current affiliation certificate.",
        },
    )
    assert rectification.status_code == 200
    assert rectification.json()["to_status"] == "RECTIFICATION_REQUESTED"

    # The applicant can replace the affiliation evidence and resubmit.
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
        data={
            "document_type": "AFFILIATION_CERTIFICATE",
            "checklist_item_id": item["id"],
        },
    )
    assert replaced.status_code == 202, replaced.text
    resubmitted = _submit(client, applicant_headers, application["id"])
    assert resubmitted["status"] == "RESUBMITTED"

    reviewer_decision = client.post(
        f"/api/v1/applications/{application['id']}/decisions",
        headers=reviewer_headers,
        json={"decision_type": "APPROVE", "rationale": "Reviewer cannot make final decisions."},
    )
    assert reviewer_decision.status_code == 403

    decision = client.post(
        f"/api/v1/applications/{application['id']}/decisions",
        headers=approver_headers,
        json={
            "decision_type": "APPROVE",
            "rationale": "Human review completed; evidence and synthetic records were considered.",
            "conditions": {"follow_up": "Verify renewed affiliation in next cycle."},
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["decision_type"] == "APPROVE"
    final = client.get(f"/api/v1/applications/{application['id']}", headers=applicant_headers)
    assert final.json()["status"] == "APPROVED"

    duplicate_decision = client.post(
        f"/api/v1/applications/{application['id']}/decisions",
        headers=approver_headers,
        json={"decision_type": "REJECT", "rationale": "A second decision is not permitted."},
    )
    assert duplicate_decision.status_code == 409

    resolved_alerts = client.get(
        f"/api/v1/applications/{application['id']}/alerts", headers=reviewer_headers
    )
    assert all(item["status"] == "RESOLVED" for item in resolved_alerts.json())

    overview = client.get(
        f"/api/v1/applications/{application['id']}/review-overview",
        headers=reviewer_headers,
    )
    assert overview.status_code == 200
    body = overview.json()
    assert body["latest_validation_run"]["findings"]
    assert body["documents"]
    # The evidence workspace needs these to decide PDF vs image rendering.
    assert all(item["original_filename"] for item in body["documents"])
    assert all(item["mime_type"] for item in body["documents"])
    assert body["infrastructure_assessment"]["simulated"] is True
    assert body["decisions"][0]["decision_type"] == "APPROVE"

    audit = client.get(
        f"/api/v1/applications/{application['id']}/audit-events",
        headers=auditor_headers,
    )
    assert audit.status_code == 200
    event_types = {item["event_type"] for item in audit.json()}
    assert {"application.created", "application.submitted", "document.uploaded", "validation.completed", "review.assign", "decision.approve"} <= event_types
    chain = client.get("/api/v1/admin/audit-events/verify", headers=auditor_headers)
    assert chain.status_code == 200
    assert chain.json()["valid"] is True


def test_alert_acknowledgement_and_resolution_are_audited(
    client, applicant_headers, reviewer_headers, auditor_headers
):
    application = create_application(client, applicant_headers)
    _upload_complete_pack(client, applicant_headers, application["id"], valid_until="31/03/2020")
    _submit(client, applicant_headers, application["id"])
    alerts = client.get(
        f"/api/v1/applications/{application['id']}/alerts", headers=reviewer_headers
    ).json()
    alert_id = alerts[0]["id"]

    acknowledged = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=reviewer_headers)
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"

    resolved = client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        headers=reviewer_headers,
        json={"note": "Clarification received during review."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"

    audit = client.get(
        f"/api/v1/applications/{application['id']}/audit-events",
        headers=auditor_headers,
    ).json()
    event_types = {item["event_type"] for item in audit}
    assert {"alert.acknowledged", "alert.resolved"} <= event_types


def test_tampered_audit_chain_is_detected(client, applicant_headers, auditor_headers, db):
    from sqlalchemy import select

    from app.db.models import AuditEvent

    create_application(client, applicant_headers)
    event = db.scalar(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1))
    event.payload = {**event.payload, "tampered": True}
    db.commit()
    result = client.get("/api/v1/admin/audit-events/verify", headers=auditor_headers)
    assert result.status_code == 200
    assert result.json()["valid"] is False
    assert result.json()["broken_sequence"] == event.sequence


def test_dashboard_and_review_authorization(
    client, applicant_headers, reviewer_headers, applicant2_headers
):
    application = create_application(client, applicant_headers)
    _upload_complete_pack(client, applicant_headers, application["id"])
    _submit(client, applicant_headers, application["id"])

    dashboard = client.get("/api/v1/dashboard/summary", headers=reviewer_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["counts"]["SUBMITTED"] == 1
    assert dashboard.json()["role"] == "REVIEWER"

    applicant_action = client.post(
        f"/api/v1/applications/{application['id']}/review-actions",
        headers=applicant_headers,
        json={"action_type": "NOTE", "note": "Applicant cannot add reviewer notes."},
    )
    assert applicant_action.status_code == 403

    hidden = client.get(
        f"/api/v1/applications/{application['id']}/review-overview",
        headers=applicant2_headers,
    )
    assert hidden.status_code == 403
