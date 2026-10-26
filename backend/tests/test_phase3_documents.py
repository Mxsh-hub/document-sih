from __future__ import annotations

import uuid

from helpers import checklist, create_application, make_pdf, satisfy_required_items


def test_document_upload_hash_and_checklist_link(client, applicant_headers):
    application = create_application(client, applicant_headers)
    item = next(item for item in checklist(client, applicant_headers, application["id"]) if item["required"])
    content = make_pdf(f"Affiliation certificate {uuid.uuid4()}")

    response = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("affiliation.pdf", content, "application/pdf")},
        data={"document_type": "AFFILIATION_CERTIFICATE", "checklist_item_id": item["id"]},
    )
    assert response.status_code == 202, response.text
    uploaded = response.json()
    assert uploaded["version_no"] == 1
    assert len(uploaded["sha256"]) == 64
    assert uploaded["status"] in {"STORED", "PROCESSED"}

    current = client.get(
        f"/api/v1/applications/{application['id']}/checklist", headers=applicant_headers
    ).json()["items"]
    linked = next(entry for entry in current if entry["id"] == item["id"])
    assert linked["document_id"] == uploaded["document_id"]
    assert linked["status"] == "SATISFIED"

    metadata = client.get(f"/api/v1/documents/{uploaded['document_id']}", headers=applicant_headers)
    assert metadata.status_code == 200
    assert metadata.json()["current_version"]["page_count"] == 1
    assert metadata.json()["checklist_item_id"] == item["id"]


def test_duplicate_content_is_rejected(client, applicant_headers):
    application = create_application(client, applicant_headers)
    content = make_pdf(f"Duplicate {uuid.uuid4()}")
    first = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("a.pdf", content, "application/pdf")},
        data={"document_type": "OTHER"},
    )
    assert first.status_code == 202
    second = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("b.pdf", content, "application/pdf")},
        data={"document_type": "OTHER"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_DOCUMENT"


def test_invalid_file_and_size_limits(client, applicant_headers):
    application = create_application(client, applicant_headers)
    url = f"/api/v1/applications/{application['id']}/documents"

    invalid = client.post(
        url,
        headers=applicant_headers,
        files={"file": ("notes.txt", b"not a document", "text/plain")},
        data={"document_type": "OTHER"},
    )
    assert invalid.status_code == 415
    assert invalid.json()["error"]["code"] == "UNSUPPORTED_FILE"

    too_large = client.post(
        url,
        headers=applicant_headers,
        files={"file": ("huge.pdf", b"x" * (25 * 1024 * 1024 + 1), "application/pdf")},
        data={"document_type": "OTHER"},
    )
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_new_version_preserves_previous_version(client, applicant_headers):
    application = create_application(client, applicant_headers)
    first = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("v1.pdf", make_pdf("version one"), "application/pdf")},
        data={"document_type": "OTHER"},
    )
    assert first.status_code == 202
    document_id = first.json()["document_id"]
    first_version_id = first.json()["document_version_id"]

    second = client.post(
        f"/api/v1/documents/{document_id}/versions",
        headers=applicant_headers,
        files={"file": ("v2.pdf", make_pdf("version two"), "application/pdf")},
    )
    assert second.status_code == 202, second.text
    assert second.json()["version_no"] == 2

    versions = client.get(f"/api/v1/documents/{document_id}/versions", headers=applicant_headers)
    assert versions.status_code == 200
    assert [entry["version_no"] for entry in versions.json()["items"]] == [1, 2]
    assert versions.json()["items"][0]["id"] == first_version_id

    metadata = client.get(f"/api/v1/documents/{document_id}", headers=applicant_headers)
    assert metadata.json()["current_version"]["version_no"] == 2


def test_download_url_and_tamper_rejection(client, applicant_headers, applicant2_headers):
    application = create_application(client, applicant_headers)
    content = make_pdf(f"Download {uuid.uuid4()}")
    uploaded = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("download.pdf", content, "application/pdf")},
        data={"document_type": "OTHER"},
    ).json()

    url_response = client.post(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/download-url",
        headers=applicant_headers,
    )
    assert url_response.status_code == 200
    url = url_response.json()["url"]
    downloaded = client.get(url)
    assert downloaded.status_code == 200
    assert downloaded.content == content

    tampered = client.get(url[:-2] + ("aa" if not url.endswith("aa") else "bb"))
    assert tampered.status_code == 403

    expired = client.get(re.sub(r"expires=\d+", "expires=0", url))
    assert expired.status_code == 403

    denied = client.post(
        f"/api/v1/document-versions/{uploaded['document_version_id']}/download-url",
        headers=applicant2_headers,
    )
    assert denied.status_code == 404


def test_upload_blocked_after_submission(client, applicant_headers):
    application = create_application(client, applicant_headers)
    satisfy_required_items(client, applicant_headers, application["id"])
    assert client.post(
        f"/api/v1/applications/{application['id']}/submit", headers=applicant_headers
    ).status_code == 200
    blocked = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("late.pdf", make_pdf("late upload"), "application/pdf")},
        data={"document_type": "OTHER"},
    )
    assert blocked.status_code == 409


def test_checklist_type_mismatch_rejected(client, applicant_headers):
    application = create_application(client, applicant_headers)
    item = next(
        item
        for item in checklist(client, applicant_headers, application["id"])
        if item["code"] == "AFFILIATION_CERTIFICATE"
    )
    response = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        headers=applicant_headers,
        files={"file": ("wrong.pdf", make_pdf("wrong type"), "application/pdf")},
        data={"document_type": "OTHER", "checklist_item_id": item["id"]},
    )
    assert response.status_code == 400


import re
