from __future__ import annotations

import uuid

from helpers import create_application, make_pdf, make_text_pdf


def _upload(client, headers, application_id, *, content=None, document_type="OTHER"):
    return client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        files={
            "file": (
                "evidence.pdf",
                content or make_pdf(f"evidence {uuid.uuid4()}"),
                "application/pdf",
            )
        },
        data={"document_type": document_type},
    )


def test_anomaly_signals_are_advisory_and_evidence_linked(
    client, applicant_headers, applicant2_headers, admin_headers
):
    first = create_application(client, applicant_headers, cycle="2026-27")
    second = create_application(client, applicant2_headers, cycle="2026-27")
    shared = make_text_pdf(
        [
            "Affiliation Certificate",
            "Name of Institution: Sunrise Institute of Technology",
            "Affiliation No: SHARED/AFF/42",
            "Valid upto: 31/03/2031",
        ]
    )
    first_upload = _upload(
        client, applicant_headers, first["id"], content=shared, document_type="AFFILIATION_CERTIFICATE"
    )
    second_upload = _upload(
        client, applicant2_headers, second["id"], content=shared, document_type="AFFILIATION_CERTIFICATE"
    )
    assert first_upload.status_code == 202
    assert second_upload.status_code == 202

    scan = client.post(f"/api/v1/applications/{first['id']}/anomaly-scan", headers=admin_headers)
    assert scan.status_code == 200, scan.text
    codes = {item["signal_code"] for item in scan.json()}
    assert {"CROSS_APPLICATION_FILE_REUSE", "SHARED_REFERENCE_IDENTIFIER"} <= codes
    for signal in scan.json():
        assert signal["advisory"] is True
        assert "not proof" in signal["message"].lower() or "advisory" in signal["message"].lower()
        assert signal["evidence"]["advisory_only"] is True

    applicant_view = client.get(
        f"/api/v1/applications/{first['id']}/anomaly-signals", headers=applicant_headers
    )
    assert applicant_view.status_code == 200
    hidden = client.get(
        f"/api/v1/applications/{first['id']}/anomaly-signals", headers=applicant2_headers
    )
    assert hidden.status_code == 404


def test_pdf_metadata_heuristic_is_low_severity(client, applicant_headers, admin_headers):
    import pymupdf

    application = create_application(client, applicant_headers)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((50, 100), "Evidence text")
    document.set_metadata({"creator": "Adobe Photoshop", "producer": "Adobe Photoshop"})
    content = document.tobytes()
    document.close()
    upload = _upload(client, applicant_headers, application["id"], content=content)
    assert upload.status_code == 202

    scan = client.post(f"/api/v1/applications/{application['id']}/anomaly-scan", headers=admin_headers)
    signal = next(
        item for item in scan.json() if item["signal_code"] == "PDF_EDITING_TOOL_METADATA"
    )
    assert signal["severity"] == "LOW"
    assert signal["advisory"] is True
    assert "does not establish alteration" in signal["message"]


def test_infrastructure_presence_and_completeness_checks(
    client, applicant_headers, applicant2_headers, admin_headers
):
    application = create_application(client, applicant_headers)
    document = _upload(client, applicant_headers, application["id"]).json()

    photo_without_file = client.post(
        f"/api/v1/applications/{application['id']}/infrastructure-evidence",
        headers=applicant_headers,
        json={"evidence_type": "PHOTO", "label": "Campus photograph registration"},
    )
    assert photo_without_file.status_code == 201
    assert photo_without_file.json()["synthetic"] is True

    for evidence_type, label in (("FLOOR_PLAN", "Floor plan"), ("CERTIFICATE", "Fire safety certificate")):
        response = client.post(
            f"/api/v1/applications/{application['id']}/infrastructure-evidence",
            headers=applicant_headers,
            json={
                "evidence_type": evidence_type,
                "label": label,
                "document_version_id": document["document_version_id"],
            },
        )
        assert response.status_code == 201, response.text

    assessment = client.get(
        f"/api/v1/applications/{application['id']}/infrastructure-assessment",
        headers=applicant_headers,
    )
    assert assessment.status_code == 200
    body = assessment.json()
    assert body["complete"] is False
    assert body["simulated"] is True
    checks = {item["evidence_type"]: item for item in body["checks"]}
    assert checks["PHOTO"]["status"] == "NEEDS_REVIEW"
    assert checks["FLOOR_PLAN"]["status"] == "PRESENT"
    assert "No image, video, structural, or authenticity analysis" in body["note"]

    hidden = client.get(
        f"/api/v1/applications/{application['id']}/infrastructure-assessment",
        headers=applicant2_headers,
    )
    assert hidden.status_code == 404

    admin_view = client.get(
        f"/api/v1/applications/{application['id']}/infrastructure-assessment",
        headers=admin_headers,
    )
    assert admin_view.status_code == 200


def test_infrastructure_document_must_belong_to_application(
    client, applicant_headers, applicant2_headers
):
    first = create_application(client, applicant_headers)
    second = create_application(client, applicant2_headers)
    other_document = _upload(client, applicant2_headers, second["id"]).json()
    response = client.post(
        f"/api/v1/applications/{first['id']}/infrastructure-evidence",
        headers=applicant_headers,
        json={
            "evidence_type": "FLOOR_PLAN",
            "label": "Cross-application document",
            "document_version_id": other_document["document_version_id"],
        },
    )
    assert response.status_code == 404
