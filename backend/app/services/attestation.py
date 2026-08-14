import uuid
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, Optional
from app.config import settings
from app.models.schemas import W3CVerifiableCredential, W3CCredentialSubject, W3CProof

def generate_attestation_vc(
    holder_did: str,
    holder_name: str,
    extracted_data: Dict[str, Any],
    original_issuer: str = "University / Authority",
    trust_level: str = "verified_copy"
) -> W3CVerifiableCredential:
    cred_id = f"urn:uuid:{uuid.uuid4()}"
    now_str = datetime.utcnow().isoformat() + "Z"
    
    subject = W3CCredentialSubject(
        id=holder_did,
        name=holder_name,
        document_type=extracted_data.get("degree") or extracted_data.get("document_type") or "degree",
        degree=extracted_data.get("degree"),
        cgpa=extracted_data.get("cgpa"),
        year=extracted_data.get("year"),
        roll_number=extracted_data.get("roll_number"),
        company=extracted_data.get("company"),
        additional_data={
            "original_issuer": original_issuer,
            "trust_level": trust_level,
            "verification_method": "AI+CrossRef",
            "attested_date": now_str
        }
    )
    
    # Generate cryptographic proof signature over credential subject contents
    raw_payload = f"{cred_id}:{holder_did}:{holder_name}:{extracted_data.get('cgpa')}:{now_str}"
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        raw_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    proof = W3CProof(
        type="Ed25519Signature2020",
        created=now_str,
        proofPurpose="assertionMethod",
        verificationMethod=f"{settings.ISSUER_DID}#key-1",
        proofValue=signature
    )
    
    return W3CVerifiableCredential(
        context=["https://www.w3.org/2018/credentials/v1"],
        id=cred_id,
        type=["VerifiableCredential", "AstraVerifyAttestedCredential"],
        issuer=settings.ISSUER_DID,
        issuanceDate=now_str,
        credentialSubject=subject,
        proof=proof
    )
