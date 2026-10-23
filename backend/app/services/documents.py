from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ApiError
from app.db.enums import ApplicationStatus, ChecklistItemStatus, DocumentStatus, DocumentType, Role
from app.db.models import (
    Application,
    ApplicationChecklistItem,
    Document,
    DocumentVersion,
    User,
)
from app.services.audit import record_audit
from app.services.object_store import build_download_url, get_object_store

Image.MAX_IMAGE_PIXELS = 50_000_000


@dataclass
class ValidatedFile:
    mime_type: str
    page_count: int | None


def _validate_pdf(content: bytes) -> ValidatedFile:
    import fitz

    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ApiError(415, "UNSUPPORTED_FILE", "The PDF could not be parsed.") from exc
    try:
        if document.needs_pass or document.page_count < 1:
            raise ApiError(415, "UNSUPPORTED_FILE", "Encrypted or empty PDFs are not accepted.")
        if document.page_count > settings.MAX_PDF_PAGES:
            raise ApiError(413, "FILE_TOO_LARGE", "The PDF has too many pages.")
        return ValidatedFile(mime_type="application/pdf", page_count=document.page_count)
    finally:
        document.close()


def _validate_image(content: bytes) -> ValidatedFile:
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError(415, "UNSUPPORTED_FILE", "The image could not be parsed.") from exc
    if image_format not in {"JPEG", "PNG"}:
        raise ApiError(415, "UNSUPPORTED_FILE", "Only PDF, JPEG, and PNG files are accepted.")
    if width < 1 or height < 1 or width > 20000 or height > 20000:
        raise ApiError(415, "UNSUPPORTED_FILE", "Image dimensions are not acceptable.")
    return ValidatedFile(mime_type="image/jpeg" if image_format == "JPEG" else "image/png", page_count=None)


def validate_upload(content: bytes) -> ValidatedFile:
    if not content:
        raise ApiError(415, "UNSUPPORTED_FILE", "The uploaded file is empty.")
    if content.startswith(b"%PDF-"):
        return _validate_pdf(content)
    if content.startswith(b"\xff\xd8\xff"):
        return _validate_image(content)
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return _validate_image(content)
    raise ApiError(415, "UNSUPPORTED_FILE", "Only PDF, JPEG, and PNG files are accepted.")


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "document").name
    name = "".join(ch for ch in name if ch.isprintable() and ch not in {"/", "\\"})
    return name[:255] or "document"


def _require_uploadable(application: Application, user: User) -> None:
    if user.role is not Role.APPLICANT:
        raise ApiError(403, "FORBIDDEN", "Only the applicant may upload documents.")
    if application.institution_id != user.institution_id:
        raise ApiError(404, "NOT_FOUND", "Application not found.")
    if application.status not in {ApplicationStatus.DRAFT, ApplicationStatus.RECTIFICATION_REQUESTED}:
        raise ApiError(409, "STATE_CONFLICT", "Documents cannot be uploaded in the current application state.")


def upload_document(
    db: Session,
    application: Application,
    actor: User,
    *,
    content: bytes,
    filename: str | None,
    document_type: DocumentType | None,
    checklist_item_id: uuid.UUID | None,
    document_id: uuid.UUID | None,
) -> tuple[Document, DocumentVersion]:
    _require_uploadable(application, actor)
    if len(content) > settings.MAX_DOCUMENT_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "Documents must not exceed 25 MB.")
    validated = validate_upload(content)
    digest = hashlib.sha256(content).hexdigest()

    duplicate = db.scalar(
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.application_id == application.id, DocumentVersion.sha256 == digest)
    )
    if duplicate:
        raise ApiError(409, "DUPLICATE_DOCUMENT", "Identical content is already attached to this application.")

    checklist_item: ApplicationChecklistItem | None = None
    if checklist_item_id is not None:
        checklist_item = db.scalar(
            select(ApplicationChecklistItem).where(
                ApplicationChecklistItem.id == checklist_item_id,
                ApplicationChecklistItem.application_id == application.id,
            )
        )
        if not checklist_item:
            raise ApiError(404, "NOT_FOUND", "Checklist item not found.")

    document: Document
    if document_id is not None:
        existing = db.get(Document, document_id)
        if not existing or existing.application_id != application.id:
            raise ApiError(404, "NOT_FOUND", "Document not found.")
        if document_type is not None and document_type is not existing.document_type:
            raise ApiError(400, "VALIDATION_FAILED", "The document type cannot be changed for a new version.")
        document = existing
        max_version = db.scalar(
            select(func.max(DocumentVersion.version_no)).where(DocumentVersion.document_id == document.id)
        ) or 0
        version_no = max_version + 1
    else:
        if document_type is None:
            raise ApiError(400, "VALIDATION_FAILED", "document_type is required for a new document.")
        document = Document(
            application_id=application.id,
            document_type=document_type,
            status=DocumentStatus.STORED,
        )
        db.add(document)
        db.flush()
        version_no = 1

    if checklist_item is not None:
        semantic_type = document.document_type.value
        if checklist_item.accepted_document_types and semantic_type not in checklist_item.accepted_document_types:
            raise ApiError(400, "VALIDATION_FAILED", "This document type is not accepted for the checklist item.")

    storage_key = (
        f"documents/{application.id}/{document.id}/v{version_no}-{digest[:16]}-{uuid.uuid4().hex[:8]}"
    )
    store = get_object_store()
    try:
        store.put(storage_key, content, validated.mime_type)
    except Exception as exc:
        raise ApiError(500, "INTERNAL_ERROR", "The document could not be stored.") from exc

    try:
        version = DocumentVersion(
            document_id=document.id,
            version_no=version_no,
            storage_key=storage_key,
            original_filename=_safe_filename(filename),
            mime_type=validated.mime_type,
            size_bytes=len(content),
            sha256=digest,
            page_count=validated.page_count,
            uploaded_by=actor.id,
            synthetic=False,
        )
        db.add(version)
        db.flush()
        document.current_version_id = version.id
        document.status = DocumentStatus.STORED
        if checklist_item is not None:
            checklist_item.document_id = document.id
            checklist_item.status = ChecklistItemStatus.SATISFIED
        record_audit(
            db,
            event_type="document.uploaded",
            actor=actor,
            application_id=application.id,
            entity_type="document_version",
            entity_id=version.id,
            payload={
                "document_id": str(document.id),
                "document_type": document.document_type.value,
                "version_no": version_no,
                "sha256": digest,
                "size_bytes": len(content),
            },
        )
        db.commit()
        if settings.PROCESS_DOCUMENTS_INLINE:
            from app.services.processing import process_document_version

            process_document_version(db, version)
        db.refresh(document)
        db.refresh(version)
        return document, version
    except Exception:
        db.rollback()
        store.delete(storage_key)
        raise


def list_documents(db: Session, application_id: uuid.UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.created_at.asc())
        )
    )


def create_download_url(
    version: DocumentVersion, expires_seconds: int = 300
) -> tuple[str, datetime]:
    store = get_object_store()
    url = store.presigned_url(version.storage_key, expires_seconds)
    if url:
        return url, datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + expires_seconds, tz=timezone.utc
        )
    return build_download_url(version.id, expires_seconds)


def checklist_item_for_document(db: Session, document_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(ApplicationChecklistItem.id).where(ApplicationChecklistItem.document_id == document_id).limit(1)
    )
