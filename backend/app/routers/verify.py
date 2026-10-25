from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
from app.services import storage, ocr, orchestrator, attestation
from app.models.schemas import OrchestratorResult, AttestRequest, W3CVerifiableCredential

router = APIRouter(prefix="/verify", tags=["AI Verification & Attestation"])

@router.post("/forensics", response_model=Dict[str, Any])
async def run_forensics_verification(req: Request, file_id: str):
    """
    Runs OCR + AI Multi-Agent Swarm (Forensics, Risk, Deepfake, Orchestrator) on uploaded file.
    Note: Forensics agent explicitly rejects camera uploads.
    """
    file_path = storage.get_file_path(file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
        
    info = storage.get_file_info(file_id) or {}
    source_type = info.get("source_type", "pdf_upload")
    
    # 1. OCR Extraction
    raw_ocr_text = ocr.extract_raw_text(file_path)
    structured_data = ocr.parse_structured_credentials(raw_ocr_text)
    
    # 2. Client Metadata for Risk Agent
    client_metadata = {
        "client_ip": req.client.host if req.client else "127.0.0.1",
        "user_agent": req.headers.get("user-agent", "Browser")
    }
    
    # 3. AI Multi-Agent Swarm Execution
    result: OrchestratorResult = orchestrator.run_ai_swarm(
        file_path=file_path,
        source_type=source_type,
        client_metadata=client_metadata
    )
    
    # Update status in storage
    storage.update_file_status(file_id, status=result.verdict.lower(), extra_data={
        "verdict": result.verdict,
        "confidence": result.confidence,
        "tier": result.tier,
        "extracted_data": structured_data
    })
    
    return {
        "file_id": file_id,
        "source_type": source_type,
        "advisory_note": (
            "Legacy heuristic pipeline. Numeric scores are preliminary indicators only and "
            "must not be presented as a forgery, authenticity, or compliance determination."
        ),
        "extracted_data": structured_data,
        "swarm_result": result.model_dump()
    }

@router.post("/attest", response_model=W3CVerifiableCredential)
async def attest_verified_document(req: AttestRequest):
    """
    Legacy demo endpoint. Issues a demo credential signed with a locally derived
    Ed25519 key (proof type ``AstraEd25519Signature``). It is not an official
    attestation and is not a W3C Data Integrity proof.
    """
    info = storage.get_file_info(req.file_id)
    if not info:
        raise HTTPException(status_code=404, detail="File not found")
        
    if info.get("verdict") != "PASS":
        raise HTTPException(status_code=400, detail="Cannot issue attestation: File did not pass AI Swarm verification")
        
    extracted_data = info.get("extracted_data", {})
    
    vc = attestation.generate_attestation_vc(
        holder_did=req.holder_did,
        holder_name=req.holder_name,
        extracted_data=extracted_data,
        original_issuer=extracted_data.get("university") or "Official Authority",
        trust_level="verified_copy"
    )
    
    storage.update_file_status(req.file_id, status="attested", extra_data={"vc_id": vc.id})
    return vc
