from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from typing import Optional
from app.services import storage
from app.models.schemas import UploadResponse

router = APIRouter(prefix="/upload", tags=["Upload"])

@router.post("", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source_type: Optional[str] = Form("pdf_upload")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
        
    valid_sources = ["pdf_upload", "camera_upload"]
    if source_type not in valid_sources:
        source_type = "pdf_upload"
        
    record = storage.save_upload_file(file, source_type=source_type)
    
    return UploadResponse(
        file_id=record["file_id"],
        filename=record["original_filename"],
        content_type=record["content_type"],
        size_bytes=record["size_bytes"],
        status="received",
        source_type=record["source_type"],
        message=f"File successfully received as {source_type}"
    )

@router.get("/{file_id}", response_model=UploadResponse)
async def get_upload_status(file_id: str):
    info = storage.get_file_info(file_id)
    if not info:
        raise HTTPException(status_code=404, detail="File not found")
        
    return UploadResponse(
        file_id=info["file_id"],
        filename=info["original_filename"],
        content_type=info["content_type"],
        size_bytes=info["size_bytes"],
        status=info.get("status", "received"),
        source_type=info.get("source_type", "pdf_upload"),
        message=f"File status: {info.get('status', 'received')}"
    )
