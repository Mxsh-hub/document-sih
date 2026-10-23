from __future__ import annotations

from helpers import checklist, create_application, make_text_pdf
from test_phase10_zkp import challenge, make_proof


def upload_pack(client, headers, application_id):
    items = {item["code"]: item for item in checklist(client, headers, application_id)}
    docs = {
        "AFFILIATION_CERTIFICATE": [
            "AICTE Affiliation Certificate",
            "Name of Institution: Sunrise Institute of Technology",
            "Affiliation No: AFF/E2E/001",
            "Issued by: State Technical University",
            "Date of Issue: 01/04/2026",
            "Valid upto: 31/03/2032",
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
    for code, lines in docs.items():
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


def test_full_application_to_decision_and_zkp_audit(
    client,
    applicant_headers,
    reviewer_headers,
    approver_headers,
    auditor_headers,
    tmp_path,
):
    application = create_application(client, applicant_headers)
    upload_pack(client, applicant_headers, application["id"])
    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submitted.status_code == 200, submitted.text
    run_id = submitted.json()["validation_run_id"]

    findings = client.get(f"/api/v1/validation-runs/{run_id}", headers=applicant_headers)
    assert findings.status_code == 200
    assert all(item["outcome"] in {"PASS", "WARN", "FAIL"} for item in findings.json()["findings"])

    issued = challenge(client, applicant_headers, application["id"])
    proof, signals = make_proof(
        tmp_path, value=850, threshold=issued["threshold"], request_hash=issued["request_hash"]
    )
    verified = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={"challenge_id": issued["id"], "proof": proof, "public_signals": signals},
    )
    assert verified.status_code == 200, verified.text

    assigned = client.post(
        f"/api/v1/applications/{application['id']}/review-actions",
        headers=reviewer_headers,
        json={"action_type": "ASSIGN", "note": "Assigned for end-to-end review."},
    )
    assert assigned.status_code == 200

    overview = client.get(
        f"/api/v1/applications/{application['id']}/review-overview", headers=reviewer_headers
    )
    assert overview.status_code == 200
    # Proof records are available to reviewers through the dedicated proof endpoint.
    proofs = client.get(
        f"/api/v1/zkp/applications/{application['id']}/proofs", headers=reviewer_headers
    )
    assert proofs.status_code == 200
    assert proofs.json()["items"][0]["status"] == "VERIFIED"

    decision = client.post(
        f"/api/v1/applications/{application['id']}/decisions",
        headers=approver_headers,
        json={
            "decision_type": "APPROVE",
            "rationale": "Synthetic end-to-end review completed by an authorized human reviewer.",
        },
    )
    assert decision.status_code == 200, decision.text

    audit = client.get(
        f"/api/v1/applications/{application['id']}/audit-events", headers=auditor_headers
    )
    assert audit.status_code == 200
    types = {item["event_type"] for item in audit.json()}
    assert {
        "application.created",
        "document.uploaded",
        "application.submitted",
        "validation.completed",
        "zkp.challenge_created",
        "zkp.proof_verified",
        "review.assign",
        "decision.approve",
    } <= types

    chain = client.get("/api/v1/admin/audit-events/verify", headers=auditor_headers)
    assert chain.status_code == 200
    assert chain.json()["valid"] is True
