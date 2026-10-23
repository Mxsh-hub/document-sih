from __future__ import annotations

import uuid

from helpers import checklist, create_application, make_pdf, make_text_pdf


def _upload(client, headers, application_id, content, *, document_type="OTHER", name="evidence.pdf"):
    return client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        files={"file": (name, content, "application/pdf")},
        data={"document_type": document_type},
    )


def test_structured_extraction_produces_evidence_linked_fields(client, applicant_headers):
    application = create_application(client, applicant_headers)
    content = make_text_pdf(
        [
            "AICTE Affiliation Certificate",
            "Name of Institution: Synthetic Institute of Technology",
            "Affiliation No: AFF/2026/001",
            "Issued by: State Technical University",
            "Date of Issue: 01/04/2026",
            "Valid upto: 31/03/2031",
            "Programme: Bachelor of Technology in Computer Science",
        ]
    )
    uploaded = _upload(
        client,
        applicant_headers,
        application["id"],
        content,
        document_type="AFFILIATION_CERTIFICATE",
    )
    assert uploaded.status_code == 202, uploaded.text
    version_id = uploaded.json()["document_version_id"]

    response = client.get(
        f"/api/v1/document-versions/{version_id}/extraction", headers=applicant_headers
    )
    assert response.status_code == 200, response.text
    extraction = response.json()
    assert extraction["status"] == "COMPLETED"
    assert extraction["confidence"] >= 0.8
    assert extraction["classification_confidence"] >= 0.75
    assert extraction["page_count"] == 1

    fields = {field["name"]: field for field in extraction["fields"]}
    assert fields["institution_name"]["raw_value"] == "Synthetic Institute of Technology"
    assert fields["affiliation_number"]["normalized_value"] == "aff/2026/001"
    assert fields["issuing_authority"]["raw_value"] == "State Technical University"
    assert fields["issued_date"]["normalized_value"] == "2026-04-01"
    assert fields["valid_until"]["normalized_value"] == "2031-03-31"
    assert fields["institution_name"]["page"] == 1
    assert fields["institution_name"]["bbox"]
    assert all(field["extractor"].startswith("ocr-phase4") for field in extraction["fields"])


def test_low_information_document_is_flagged_not_trusted(client, applicant_headers):
    application = create_application(client, applicant_headers)
    uploaded = _upload(
        client,
        applicant_headers,
        application["id"],
        make_pdf(f"Unstructured note {uuid.uuid4()}"),
    )
    version_id = uploaded.json()["document_version_id"]
    extraction = client.get(
        f"/api/v1/document-versions/{version_id}/extraction", headers=applicant_headers
    ).json()
    assert extraction["status"] == "LOW_CONFIDENCE"
    assert extraction["error_detail"] is None

    document = client.get(f"/api/v1/documents/{uploaded.json()['document_id']}", headers=applicant_headers)
    assert document.json()["status"] in {"PROCESSED", "LOW_CONFIDENCE"}


def test_blank_document_is_unreadable_and_blocks_submission(client, applicant_headers):
    application = create_application(client, applicant_headers)
    uploaded = _upload(
        client,
        applicant_headers,
        application["id"],
        make_pdf(""),
        document_type="AFFILIATION_CERTIFICATE",
    )
    version_id = uploaded.json()["document_version_id"]
    extraction = client.get(
        f"/api/v1/document-versions/{version_id}/extraction", headers=applicant_headers
    ).json()
    assert extraction["status"] == "UNREADABLE"
    assert extraction["error_code"] == "NO_TEXT"

    item = next(
        entry
        for entry in checklist(client, applicant_headers, application["id"])
        if entry["code"] == "AFFILIATION_CERTIFICATE"
    )
    assert item["status"] != "SATISFIED"

    submit = client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    )
    assert submit.status_code == 400


def test_extraction_visibility_and_reprocess_permissions(
    client, applicant_headers, applicant2_headers, reviewer_headers
):
    application = create_application(client, applicant_headers)
    uploaded = _upload(
        client,
        applicant_headers,
        application["id"],
        make_text_pdf(["Name of Institution: Example College", "Affiliation No: AFF/1"]),
        document_type="AFFILIATION_CERTIFICATE",
    )
    version_id = uploaded.json()["document_version_id"]

    hidden = client.get(
        f"/api/v1/document-versions/{version_id}/extraction", headers=applicant2_headers
    )
    assert hidden.status_code == 404

    # Draft applications are not visible to reviewers.
    review_hidden = client.post(
        f"/api/v1/document-versions/{version_id}/reprocess", headers=reviewer_headers
    )
    assert review_hidden.status_code == 404

    from helpers import satisfy_required_items

    satisfy_required_items(client, applicant_headers, application["id"])
    assert (
        client.post(
            f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
        ).status_code
        == 200
    )

    forbidden = client.post(
        f"/api/v1/document-versions/{version_id}/reprocess", headers=applicant_headers
    )
    assert forbidden.status_code == 403

    reprocessed = client.post(
        f"/api/v1/document-versions/{version_id}/reprocess", headers=reviewer_headers
    )
    assert reprocessed.status_code == 202, reprocessed.text
    assert reprocessed.json()["status"] in {"COMPLETED", "LOW_CONFIDENCE"}
