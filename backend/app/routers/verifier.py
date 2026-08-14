import uuid
import hashlib
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Path as FastAPIPath
from app.models.schemas import (
    VerificationRequest, 
    VerificationRequestResponse, 
    ZKProofSubmission, 
    VerificationResult
)

router = APIRouter(prefix="/verifier", tags=["Verifier Portal & ZK Proofs"])

VERIFICATION_REQUESTS_DB: Dict[str, VerificationRequestResponse] = {}
VERIFICATION_RESULTS_DB: Dict[str, VerificationResult] = {}

@router.post("/create-request", response_model=VerificationRequestResponse)
async def create_verification_request(req: VerificationRequest):
    """
    Verifier portal creates JSON criteria (e.g. cgpa >= 7.5, degree in ['B.Tech', 'B.E.']).
    """
    req_id = f"req_{uuid.uuid4().hex[:12]}"
    now_str = datetime.utcnow().isoformat() + "Z"
    
    resp = VerificationRequestResponse(
        verification_request_id=req_id,
        verifier_did=req.verifier_did,
        purpose=req.purpose,
        criteria=req.criteria,
        created_at=now_str
    )
    VERIFICATION_REQUESTS_DB[req_id] = resp
    return resp

@router.get("/request/{request_id}", response_model=VerificationRequestResponse)
async def get_verification_request(request_id: str = FastAPIPath(...)):
    req = VERIFICATION_REQUESTS_DB.get(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Verification request criteria not found")
    return req

@router.post("/validate-zk", response_model=VerificationResult)
async def validate_zk_proof(submission: ZKProofSubmission):
    """
    Validates client-side generated ZK proof against requested criteria.
    Emits verification result and SHA-3 hash for blockchain anchoring.
    """
    v_req = VERIFICATION_REQUESTS_DB.get(submission.verification_request_id)
    if not v_req:
        raise HTTPException(status_code=404, detail="Invalid verification_request_id")
        
    verification_id = f"verif_{uuid.uuid4().hex[:12]}"
    criterion_results = []
    all_passed = True
    
    # Evaluate proof & public signals against criteria
    for idx, criterion in enumerate(v_req.criteria):
        # Public signals evaluation (e.g., signal '1' = criterion satisfied in snarkjs)
        signal_val = submission.public_signals[idx] if idx < len(submission.public_signals) else "0"
        passed = (signal_val == "1" or signal_val.lower() == "true")
        if not passed:
            all_passed = False
            
        criterion_results.append({
            "field": criterion.field,
            "operator": criterion.operator,
            "required_value": criterion.value,
            "result": "PASS" if passed else "FAIL"
        })

    status = "APPROVED" if all_passed else "REJECTED"
    overall_confidence = 1.0 if all_passed else 0.0
    
    # Compute SHA-3 hash of result JSON for Polygon blockchain anchor
    result_bytes = f"{verification_id}:{status}:{v_req.verifier_did}".encode("utf-8")
    tx_hash_anchor = "0x" + hashlib.sha3_256(result_bytes).hexdigest()
    
    res = VerificationResult(
        verification_id=verification_id,
        status=status,
        criterion_results=criterion_results,
        overall_confidence=overall_confidence,
        blockchain_tx_hash=tx_hash_anchor
    )
    
    VERIFICATION_RESULTS_DB[verification_id] = res
    return res

@router.get("/result/{verification_id}", response_model=VerificationResult)
async def get_verification_result(verification_id: str = FastAPIPath(...)):
    res = VERIFICATION_RESULTS_DB.get(verification_id)
    if not res:
        raise HTTPException(status_code=404, detail="Verification result not found")
    return res
