from __future__ import annotations

from helpers import create_application, make_pdf


def _upload(client, headers, application_id):
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        files={"file": ("credential.pdf", make_pdf("Synthetic credential document"), "application/pdf")},
        data={"document_type": "OTHER"},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _issue(client, admin_headers, version_id, **overrides):
    payload = {
        "document_version_id": version_id,
        "subject_reference": "URN:SYNTHETIC:INSTITUTE:1",
        "claims": {"document_kind": "synthetic-affiliation", "institution": "Synthetic Institute"},
    }
    payload.update(overrides)
    return client.post("/api/v1/demo-issuer/credentials", headers=admin_headers, json=payload)


def test_demo_ed25519_credential_verifies_and_is_labelled_synthetic(
    client, applicant_headers, admin_headers
):
    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"])
    issued = _issue(client, admin_headers, uploaded["document_version_id"])
    assert issued.status_code == 201, issued.text
    assert issued.json()["synthetic"] is True
    assert issued.json()["status"] == "ACTIVE"

    verified = client.post(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/issuer-verifications",
        headers=admin_headers,
        json={"issuer_code": "demo"},
    )
    assert verified.status_code == 201, verified.text
    body = verified.json()
    assert body["status"] == "VERIFIED"
    assert body["simulated_source"] is True
    assert "not an AICTE" in body["message"]
    assert body["evidence"]["document_sha256_match"] is True

    listing = client.get(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/issuer-verifications",
        headers=applicant_headers,
    )
    assert listing.status_code == 200
    assert listing.json()[0]["status"] == "VERIFIED"


def test_credential_bound_to_other_document_is_mismatch(
    client, applicant_headers, admin_headers
):
    application = create_application(client, applicant_headers)
    first = _upload(client, applicant_headers, application["id"])
    second = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("second.pdf", make_pdf("A different document"), "application/pdf")},
        data={"document_type": "OTHER"},
    ).json()
    credential = _issue(client, admin_headers, first["document_version_id"]).json()

    mismatch = client.post(
        f"/api/v1/document-versions/{second['document_version_id']}/issuer-verifications",
        headers=admin_headers,
        json={"issuer_code": "demo", "credential_id": credential["credential_id"]},
    )
    assert mismatch.status_code == 201
    assert mismatch.json()["status"] == "MISMATCH"


def test_revoked_and_tampered_credentials_do_not_verify(
    client, applicant_headers, admin_headers, db
):
    from app.db.models import IssuedCredential

    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"])
    credential = _issue(client, admin_headers, uploaded["document_version_id"]).json()

    revoked = client.post(
        f"/api/v1/demo-issuer/credentials/{credential['id']}/revoke",
        headers=admin_headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"

    failed = client.post(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/issuer-verifications",
        headers=admin_headers,
        json={"issuer_code": "demo", "credential_id": credential["credential_id"]},
    )
    assert failed.json()["status"] == "MISMATCH"

    second_credential = _issue(client, admin_headers, uploaded["document_version_id"]).json()
    row = db.get(IssuedCredential, second_credential["id"])
    row.signature = "tampered-signature"
    db.commit()
    tampered = client.post(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/issuer-verifications",
        headers=admin_headers,
        json={"issuer_code": "demo", "credential_id": second_credential["credential_id"]},
    )
    assert tampered.json()["status"] == "MISMATCH"


def test_external_issuer_is_explicitly_unavailable(client, applicant_headers, admin_headers):
    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"])
    response = client.post(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/issuer-verifications",
        headers=admin_headers,
        json={"issuer_code": "external"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "SOURCE_UNAVAILABLE"
    assert response.json()["simulated_source"] is True


def test_issuer_permissions(client, applicant_headers, applicant2_headers, admin_headers):
    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"])

    applicant_issue = _issue(client, applicant_headers, uploaded["document_version_id"])
    assert applicant_issue.status_code == 403

    applicant_verify = client.post(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/issuer-verifications",
        headers=applicant_headers,
        json={"issuer_code": "demo"},
    )
    assert applicant_verify.status_code == 403

    other_view = client.get(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/issuer-verifications",
        headers=applicant2_headers,
    )
    assert other_view.status_code == 404
