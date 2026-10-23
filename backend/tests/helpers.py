from __future__ import annotations

import uuid

import pymupdf


def make_pdf(text: str) -> bytes:
    return make_text_pdf([text])


def make_text_pdf(lines: list[str]) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((50, 100 + index * 22), line)
    content = document.tobytes()
    document.close()
    return content


def upload_pdf(client, headers, application_id: str, *, document_type: str, checklist_item_id=None, text=None):
    content = make_pdf(text or f"Synthetic evidence {uuid.uuid4()}")
    data = {"document_type": document_type}
    if checklist_item_id:
        data["checklist_item_id"] = checklist_item_id
    return client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        files={"file": ("evidence.pdf", content, "application/pdf")},
        data=data,
    )


def create_application(client, headers, cycle="2026-27"):
    response = client.post(
        "/api/v1/applications",
        headers=headers,
        json={"category_code": "EOA", "cycle": cycle},
    )
    assert response.status_code == 201, response.text
    return response.json()


def checklist(client, headers, application_id):
    response = client.get(f"/api/v1/applications/{application_id}/checklist", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def satisfy_required_items(client, headers, application_id):
    uploaded = []
    for item in checklist(client, headers, application_id):
        if not item["required"]:
            continue
        response = upload_pdf(
            client,
            headers,
            application_id,
            document_type=item["accepted_document_types"][0],
            checklist_item_id=item["id"],
            text=f"Synthetic {item['code']} {uuid.uuid4()}",
        )
        assert response.status_code == 202, response.text
        uploaded.append(response.json())
    return uploaded
