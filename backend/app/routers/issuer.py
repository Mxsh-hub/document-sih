import uuid
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Path as FastAPIPath
from app.config import settings
from app.models.schemas import IssueCredentialRequest, IssueCredentialResponse, W3CVerifiableCredential, W3CCredentialSubject, W3CProof

router = APIRouter(prefix="/issuer", tags=["Issuer Portal"])

ISSUED_CREDENTIALS_DB: Dict[str, W3CVerifiableCredential] = {}

@router.post("/issue", response_model=IssueCredentialResponse)
async def issue_credential(req: IssueCredentialRequest):
    """
    Universities, employers, or government offices issue native W3C VCs directly to a user's DID.
    These are Gold Tier credentials (signature is trust).
    """
    cred_id = f"urn:uuid:{uuid.uuid4()}"
    now_str = datetime.utcnow().isoformat() + "Z"
    
    subject = W3CCredentialSubject(
        id=req.holder_did,
        name=req.holder_name,
        document_type=req.document_type,
        degree=req.degree_name,
        cgpa=req.cgpa,
        year=req.year_of_passing,
        roll_number=req.roll_number,
        company=req.company,
        role=req.role,
        years_of_experience=req.years_of_experience,
        id_type=req.id_type,
        id_number=req.id_number
    )
    
    # Demo integrity tag, not a digital signature: HMAC-SHA256 with the shared
    # application secret. The proof type says so instead of claiming Ed25519.
    sig_payload = f"{cred_id}:{req.holder_did}:{req.holder_name}:{req.degree_name}:{req.cgpa}:{now_str}"
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        sig_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    proof = W3CProof(
        type="AstraDemoHmacIntegrity",
        created=now_str,
        proofPurpose="assertionMethod",
        verificationMethod=f"did:gov:university#demo-shared-secret",
        proofValue=sig
    )
    
    vc = W3CVerifiableCredential(
        context=["https://www.w3.org/2018/credentials/v1"],
        id=cred_id,
        type=["VerifiableCredential", "IssuerNativeGoldCredential"],
        issuer="did:gov:university",
        issuanceDate=now_str,
        credentialSubject=subject,
        proof=proof
    )
    
    ISSUED_CREDENTIALS_DB[cred_id] = vc
    
    # Anchor SHA-3 hash of VC on chain
    credential_hash = hashlib.sha3_256(vc.model_dump_json().encode("utf-8")).hexdigest()
    
    return IssueCredentialResponse(
        status="ISSUED",
        credential_id=cred_id,
        vc=vc,
        blockchain_anchor=f"0x{credential_hash}"
    )

@router.get("/credentials/{credential_id}")
async def lookup_issued_credential(credential_id: str = FastAPIPath(...)):
    vc = ISSUED_CREDENTIALS_DB.get(credential_id)
    if not vc:
        raise HTTPException(status_code=404, detail="Credential not found")
    return vc
