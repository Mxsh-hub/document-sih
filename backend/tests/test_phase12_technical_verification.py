from __future__ import annotations

from helpers import create_application, make_pdf

from app.services import technical_verification as tv


def _upload(client, headers, application_id, content=None, *, name="evidence.pdf", mime="application/pdf"):
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        files={"file": (name, content or make_pdf("Synthetic technical inspection document"), mime)},
        data={"document_type": "OTHER"},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _inspect(client, headers, version_id):
    return client.post(
        f"/api/v1/document-versions/{version_id}/technical-verifications", headers=headers
    )


def _by_adapter(rows):
    return {row["adapter_code"]: row for row in rows}


def _signed_pdf() -> bytes:
    """A PDF with a raw signature dictionary whose byte ranges skip the contents."""
    base = make_pdf("Synthetic signed document")
    tail = b"\n%%signature-end\n"

    def build(values) -> bytes:
        return (
            b"<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached "
            b"/Name (Synthetic Signer) /M (D:20261025000000Z) /ByteRange ["
            + b" ".join(f"{value:012d}".encode() for value in values)
            + b"] /Contents <"
            + b"00" * 1024
            + b"> >>"
        )

    gap = build((0, 0, 0, 0))
    second_start = len(base) + len(gap)
    filled = build((0, len(base), second_start, len(tail)))
    assert len(filled) == len(gap)
    return base + filled + tail


def test_unsigned_pdf_reports_absence_without_authenticity_claim(
    client, applicant_headers, admin_headers
):
    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"])

    response = _inspect(client, admin_headers, uploaded["document_version_id"])
    assert response.status_code == 201, response.text
    rows = _by_adapter(response.json())
    assert set(rows) == {"qr-payload", "pdf-signature"}

    qr = rows["qr-payload"]
    assert qr["status"] == "NOT_FOUND"
    assert qr["evidence"]["state"] == "NO_QR_DETECTED"
    assert qr["evidence"]["advisory_only"] is True
    assert qr["evidence"]["cryptographically_verified"] is False
    assert qr["evidence"]["external_lookup_performed"] is False
    assert qr["simulated_source"] is False
    assert "not evidence" in qr["message"]

    signature = rows["pdf-signature"]
    assert signature["status"] == "NOT_FOUND"
    assert signature["evidence"]["state"] == "NO_PDF_SIGNATURE"
    assert signature["evidence"]["trust_chain_checked"] is False
    assert signature["evidence"]["document_sha256"] == uploaded["sha256"]


def test_embedded_signature_structure_is_reported_unverified(
    client, applicant_headers, admin_headers
):
    application = create_application(client, applicant_headers)
    uploaded = _upload(
        client, applicant_headers, application["id"], _signed_pdf(), name="signed.pdf"
    )

    response = _inspect(client, admin_headers, uploaded["document_version_id"])
    assert response.status_code == 201, response.text
    signature = _by_adapter(response.json())["pdf-signature"]

    assert signature["status"] == "SOURCE_UNAVAILABLE"
    assert signature["evidence"]["state"] == "PDF_SIGNATURE_PRESENT_UNVERIFIED"
    assert signature["evidence"]["covers_whole_document"] is True
    assert 0 < signature["evidence"]["coverage_ratio"] <= 1
    assert signature["evidence"]["cryptographically_verified"] is False
    assert signature["evidence"]["trust_chain_checked"] is False
    assert signature["evidence"]["signature_fields"]["signer_name"] == "Synthetic Signer"
    assert signature["evidence"]["signature_fields"]["signing_time"] == "D:20261025000000Z"
    assert "Adobe.PPKLite" in signature["evidence"]["signature_fields"]["filters"]
    assert "NOT verified" in signature["message"]
    assert "advisory" in signature["message"].lower()


def test_signature_structure_with_invalid_coverage_is_advisory_mismatch(
    client, applicant_headers, admin_headers
):
    application = create_application(client, applicant_headers)
    content = make_pdf("Synthetic modified document") + (
        b"\n<< /Type /Sig /ByteRange [0 999999999 5 10] >>\n"
    )
    uploaded = _upload(
        client, applicant_headers, application["id"], content, name="modified.pdf"
    )

    signature = _by_adapter(
        _inspect(client, admin_headers, uploaded["document_version_id"]).json()
    )["pdf-signature"]
    assert signature["status"] == "MISMATCH"
    assert signature["evidence"]["state"] == "PDF_SIGNATURE_COVERAGE_INCOMPLETE"
    assert signature["evidence"]["covers_whole_document"] is False
    assert "not proof of alteration" in signature["message"]


def test_qr_payload_is_recorded_but_never_fetched(
    client, applicant_headers, admin_headers, monkeypatch
):
    payload = "https://verify.example.test/d/ABC123?issuer=synthetic"
    monkeypatch.setattr(tv, "_decode_qr", lambda image: [payload])

    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"], make_pdf("QR document"))

    qr = _by_adapter(
        _inspect(client, admin_headers, uploaded["document_version_id"]).json()
    )["qr-payload"]
    assert qr["status"] == "SOURCE_UNAVAILABLE"
    assert qr["evidence"]["state"] == "QR_PAYLOAD_DETECTED_UNVERIFIED"
    assert qr["evidence"]["external_lookup_performed"] is False
    assert qr["evidence"]["payload_count"] == 1
    entry = qr["evidence"]["payloads"][0]
    assert entry["page"] == 1
    assert entry["payload_preview"] == payload
    assert entry["payload_sha256"] and len(entry["payload_sha256"]) == 64
    assert entry["host"] == "verify.example.test"
    assert entry["scheme"] == "https"
    assert entry["not_fetched"] is True
    assert "no authenticity claim" in qr["message"].lower()


def test_missing_qr_decoder_is_a_deployment_limitation(
    client, applicant_headers, admin_headers, monkeypatch
):
    def unavailable(_image):
        raise tv.QrDecoderUnavailable("not installed")

    monkeypatch.setattr(tv, "_decode_qr", unavailable)

    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"])

    rows = _by_adapter(
        _inspect(client, admin_headers, uploaded["document_version_id"]).json()
    )
    assert rows["qr-payload"]["status"] == "SOURCE_UNAVAILABLE"
    assert rows["qr-payload"]["evidence"]["state"] == "QR_DECODER_UNAVAILABLE"
    # The signature inspection still runs and keeps its own state.
    assert rows["pdf-signature"]["evidence"]["state"] == "NO_PDF_SIGNATURE"


def test_technical_inspection_permissions_and_review_overview(
    client, applicant_headers, admin_headers, db
):
    application = create_application(client, applicant_headers)
    uploaded = _upload(client, applicant_headers, application["id"])
    version_id = uploaded["document_version_id"]

    assert _inspect(client, applicant_headers, version_id).status_code == 403

    from app.db.models import DocumentVersion

    version = db.get(DocumentVersion, version_id)
    version.mime_type = "text/plain"
    db.commit()
    unsupported = _inspect(client, admin_headers, version_id)
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    version.mime_type = "application/pdf"
    db.commit()
    inspected = _inspect(client, admin_headers, version_id)
    assert inspected.status_code == 201

    overview = client.get(
        f"/api/v1/applications/{application['id']}/review-overview", headers=admin_headers
    )
    assert overview.status_code == 200, overview.text
    technical = overview.json()["technical_verifications"]
    assert {item["adapter_code"] for item in technical} == {"qr-payload", "pdf-signature"}
    assert all(item["document_version_id"] == version_id for item in technical)
    # Re-running keeps every attempt in the audit trail but the overview shows the latest.
    assert _inspect(client, admin_headers, version_id).status_code == 201
    refreshed = client.get(
        f"/api/v1/applications/{application['id']}/review-overview", headers=admin_headers
    ).json()["technical_verifications"]
    assert len(refreshed) == 2

    events = client.get(
        f"/api/v1/applications/{application['id']}/audit-events", headers=admin_headers
    ).json()
    recorded = [event for event in events if event["event_type"] == "issuer.verification_recorded"]
    assert recorded
    assert any(
        event["payload"]["adapter_code"] == "pdf-signature" for event in recorded
    )
