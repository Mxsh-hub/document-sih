import os
import uuid
import json
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import UploadFile
from app.config import settings

METADATA_FILE = settings.UPLOAD_DIR / "metadata.json"

def _load_metadata() -> Dict[str, Any]:
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_metadata(data: Dict[str, Any]):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def save_upload_file(file: UploadFile, source_type: str = "pdf_upload") -> Dict[str, Any]:
    file_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix if file.filename else ".pdf"
    saved_filename = f"{file_id}{extension}"
    file_path = settings.UPLOAD_DIR / saved_filename
    
    content = file.file.read()
    size_bytes = len(content)
    
    with open(file_path, "wb") as f:
        f.write(content)
        
    metadata = _load_metadata()
    record = {
        "file_id": file_id,
        "original_filename": file.filename or "uploaded_document",
        "saved_filename": saved_filename,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": size_bytes,
        "source_type": source_type,  # 'pdf_upload' or 'camera_upload'
        "status": "received",
        "file_path": str(file_path)
    }
    metadata[file_id] = record
    _save_metadata(metadata)
    
    return record

def get_file_info(file_id: str) -> Optional[Dict[str, Any]]:
    metadata = _load_metadata()
    return metadata.get(file_id)

def get_file_path(file_id: str) -> Optional[Path]:
    info = get_file_info(file_id)
    if info and "file_path" in info:
        path = Path(info["file_path"])
        if path.exists():
            return path
    return None

def update_file_status(file_id: str, status: str, extra_data: Optional[Dict[str, Any]] = None) -> bool:
    metadata = _load_metadata()
    if file_id in metadata:
        metadata[file_id]["status"] = status
        if extra_data:
            metadata[file_id].update(extra_data)
        _save_metadata(metadata)
        return True
    return False
