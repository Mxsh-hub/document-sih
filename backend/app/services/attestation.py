"""Legacy demo attestation.

The proof is a real Ed25519 signature over the canonical credential payload,
but it is **not** a W3C Data Integrity proof: the proof value is base64url
encoded rather than multibase, and the key is derived from local configuration
instead of being published as a DID document. The proof type therefore says
``AstraEd25519Signature`` rather than claiming ``Ed25519Signature2020``.

This module is only reachable through the legacy API surface, which is gated
behind ``LEGACY_API_ENABLED`` and must not be presented as an AICTE capability.
"""

import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.config import settings
from app.models.schemas import W3CCredentialSubject, W3CProof, W3CVerifiableCredential


def _signing_key() -> Ed25519PrivateKey:
    """Derive a stable demo key from configuration (no key material at rest)."""
    seed = hashlib.sha256(f"{settings.SECRET_KEY}:{settings.ISSUER_DID}".encode("utf-8")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def generate_attestation_vc(
    holder_did: str,
    holder_name: str,
    extracted_data: Dict[str, Any],
    original_issuer: str = "University / Authority",
    trust_level: str = "verified_copy",
) -> W3CVerifiableCredential:
    cred_id = f"urn:uuid:{uuid.uuid4()}"
    now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

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
            "verification_method": "synthetic_demo_pipeline",
            "attested_date": now_str,
            "synthetic": True,
        },
    )

    signing_payload = {
        "id": cred_id,
        "issuer": settings.ISSUER_DID,
        "issuanceDate": now_str,
        "credentialSubject": subject.model_dump(mode="json"),
    }
    signature = base64.urlsafe_b64encode(_signing_key().sign(_canonical(signing_payload))).decode("ascii").rstrip("=")

    proof = W3CProof(
        type="AstraEd25519Signature",
        created=now_str,
        proofPurpose="assertionMethod",
        verificationMethod=f"{settings.ISSUER_DID}#key-1",
        proofValue=signature,
    )

    return W3CVerifiableCredential(
        context=["https://www.w3.org/2018/credentials/v1"],
        id=cred_id,
        type=["VerifiableCredential", "AstraVerifyAttestedCredential"],
        issuer=settings.ISSUER_DID,
        issuanceDate=now_str,
        credentialSubject=subject,
        proof=proof,
    )


def verify_attestation_vc(vc: W3CVerifiableCredential) -> bool:
    """Verify a credential produced by :func:`generate_attestation_vc`."""
    from cryptography.exceptions import InvalidSignature

    if vc.proof is None:
        return False
    signing_payload = {
        "id": vc.id,
        "issuer": vc.issuer,
        "issuanceDate": vc.issuanceDate,
        "credentialSubject": vc.credentialSubject.model_dump(mode="json"),
    }
    padded = vc.proof.proofValue + "=" * (-len(vc.proof.proofValue) % 4)
    try:
        signature = base64.urlsafe_b64decode(padded)
        _signing_key().public_key().verify(signature, _canonical(signing_payload))
        return True
    except (InvalidSignature, ValueError):
        return False
