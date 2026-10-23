from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.config import settings
from app.core.errors import ApiError
from app.db.base import get_db
from app.db.enums import DocumentType, Role
from app.db.models import Application, Document, DocumentVersion, Extraction, User
from app.schemas.phase3 import (
    DocumentListOut,
    DocumentOut,
    DocumentUploadResponse,
    DocumentVersionListOut,
    DocumentVersionOut,
    DownloadUrlOut,
    ExtractionOut,
)
from app.services import documents as document_service
from app.services.authorization import (
    get_application_or_404,
    get_document_or_404,
    get_document_version_or_404,
)
from app.services.object_store import get_object_store, verify_local_download
from app.services.processing import process_document_version

router = APIRouter(tags=["Documents"])


def _document_out(db: Session, document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        application_id=document.application_id,
        document_type=document.document_type,
        status=document.status,
        current_version_id=document.current_version_id,
        checklist_item_id=document_service.checklist_item_for_document(db, document.id),
        created_at=document.created_at,
        updated_at=document.updated_at,
        current_version=DocumentVersionOut.model_validate(document.current_version)
        if document.current_version
        else None,
    )


def _read_upload(file: UploadFile) -> bytes:
    content = file.file.read(settings.MAX_DOCUMENT_BYTES + 1)
    if len(content) > settings.MAX_DOCUMENT_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "Documents must not exceed 25 MB.")
    return content


@router.post(
    "/applications/{application_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    document_type: Annotated[DocumentType | None, Form()] = None,
    checklist_item_id: Annotated[uuid.UUID | None, Form()] = None,
    document_id: Annotated[uuid.UUID | None, Form()] = None,
):
    application = get_application_or_404(db, application_id, user)
    content = _read_upload(file)
    document, version = document_service.upload_document(
        db,
        application,
        user,
        content=content,
        filename=file.filename,
        document_type=document_type,
        checklist_item_id=checklist_item_id,
        document_id=document_id,
    )
    return DocumentUploadResponse(
        document_id=document.id,
        document_version_id=version.id,
        version_no=version.version_no,
        sha256=version.sha256,
        status=document.status,
        processing_job_id=None,
    )


@router.get("/applications/{application_id}/documents", response_model=DocumentListOut)
def list_documents(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    get_application_or_404(db, application_id, user)
    documents = document_service.list_documents(db, application_id)
    return DocumentListOut(items=[_document_out(db, document) for document in documents])


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    document = get_document_or_404(db, document_id, user)
    return _document_out(db, document)


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_version(
    document_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    checklist_item_id: Annotated[uuid.UUID | None, Form()] = None,
):
    document = get_document_or_404(db, document_id, user)
    application = db.get(Application, document.application_id)
    if not application:
        raise ApiError(404, "NOT_FOUND", "Application not found.")
    content = _read_upload(file)
    document, version = document_service.upload_document(
        db,
        application,
        user,
        content=content,
        filename=file.filename,
        document_type=None,
        checklist_item_id=checklist_item_id,
        document_id=document_id,
    )
    return DocumentUploadResponse(
        document_id=document.id,
        document_version_id=version.id,
        version_no=version.version_no,
        sha256=version.sha256,
        status=document.status,
        processing_job_id=None,
    )


@router.get("/documents/{document_id}/versions", response_model=DocumentVersionListOut)
def list_versions(
    document_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    document = get_document_or_404(db, document_id, user)
    return DocumentVersionListOut(
        items=[DocumentVersionOut.model_validate(version) for version in document.versions]
    )


@router.get("/document-versions/{version_id}", response_model=DocumentVersionOut)
def get_version(
    version_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    version = get_document_version_or_404(db, version_id, user)
    return DocumentVersionOut.model_validate(version)


@router.post("/document-versions/{version_id}/download-url", response_model=DownloadUrlOut)
def download_url(
    version_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    expires_seconds: Annotated[int, Query(ge=30, le=300)] = 300,
):
    version = get_document_version_or_404(db, version_id, user)
    url, expires_at = document_service.create_download_url(version, expires_seconds)
    return DownloadUrlOut(url=url, expires_at=expires_at)


@router.get("/document-versions/{version_id}/content")
def download_content(
    version_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    expires: int,
    signature: str,
):
    verify_local_download(version_id, expires, signature)
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise ApiError(404, "NOT_FOUND", "Document version not found.")
    try:
        handle = get_object_store().open(version.storage_key)
    except FileNotFoundError as exc:
        raise ApiError(404, "NOT_FOUND", "Stored document is unavailable.") from exc

    def chunks():
        try:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            handle.close()

    safe_name = version.original_filename.replace('"', "")
    return StreamingResponse(
        chunks(),
        media_type=version.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/document-versions/{version_id}/extraction", response_model=ExtractionOut)
def get_extraction(
    version_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    get_document_version_or_404(db, version_id, user)
    extraction = db.scalar(
        select(Extraction).where(Extraction.document_version_id == version_id)
    )
    if not extraction:
        raise ApiError(404, "NOT_FOUND", "No extraction is available for this version.")
    return ExtractionOut.model_validate(extraction)


@router.post(
    "/document-versions/{version_id}/reprocess",
    response_model=ExtractionOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_extraction(
    version_id: uuid.UUID,
    user: Annotated[User, Depends(require_roles(Role.REVIEWER, Role.APPROVER, Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    version = get_document_version_or_404(db, version_id, user)
    extraction = process_document_version(db, version, force=True)
    return ExtractionOut.model_validate(extraction)
