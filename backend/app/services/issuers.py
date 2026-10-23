from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.enums import CredentialStatus, IssuerVerificationStatus
from app.services.audit import record_audit
from app.db.models import (
    Document,
    DocumentVersion,
    IssuedCredential,
    IssuerKey,
    IssuerVerification,
    User,
)

DEMO_ISSUER_CODE = "DEMO-AICTE-ISSUER"


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def _generate_key_pair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def get_or_create_demo_issuer(db: Session) -> IssuerKey:
    key = db.scalar(select(IssuerKey).where(IssuerKey.issuer_code == DEMO_ISSUER_CODE))
    if key:
        return key
    private_pem, public_pem = _generate_key_pair()
    key = IssuerKey(
        issuer_code=DEMO_ISSUER_CODE,
        issuer_name="Synthetic Demo Issuer (not AICTE)",
        algorithm="Ed25519",
        public_key_pem=public_pem,
        private_key_pem=private_pem,
        synthetic=True,
    )
    db.add(key)
    db.flush()
    return key


def issue_demo_credential(
    db: Session,
    *,
    version: DocumentVersion,
    actor: User,
    subject_reference: str | None,
    claims: dict[str, Any],
    expires_at: datetime | None,
) -> IssuedCredential:
    document = db.get(Document, version.document_id)
    if not document:
        raise ApiError(404, "NOT_FOUND", "Document not found.")
    key = get_or_create_demo_issuer(db)
    if not key.private_key_pem:
        raise ApiError(409, "ISSUER_KEY_UNAVAILABLE", "The demo issuer signing key is unavailable.")
    issued_at = datetime.now(timezone.utc)
    credential_id = f"urn:uuid:{uuid.uuid4()}"
    payload = {
        "credential_id": credential_id,
        "issuer_code": key.issuer_code,
        "issuer_name": key.issuer_name,
        "synthetic": True,
        "document_sha256": version.sha256,
        "subject_reference": subject_reference,
        "claims": claims,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
    }
    private_key = serialization.load_pem_private_key(key.private_key_pem.encode(), password=None)
    assert isinstance(private_key, Ed25519PrivateKey)
    signature = base64.b64encode(private_key.sign(_canonical(payload))).decode()
    credential = IssuedCredential(
        credential_id=credential_id,
        issuer_key_id=key.id,
        document_version_id=version.id,
        document_sha256=version.sha256,
        subject_reference=subject_reference,
        claims=claims,
        canonical_payload=payload,
        signature=signature,
        status=CredentialStatus.ACTIVE,
        synthetic=True,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    db.add(credential)
    db.flush()
    record_audit(
        db,
        event_type="issuer.demo_credential_issued",
        actor=actor,
        application_id=document.application_id,
        entity_type="issued_credential",
        entity_id=credential.id,
        payload={"credential_id": credential_id, "synthetic": True},
    )
    db.commit()
    db.refresh(credential)
    return credential


def _verify_signature(credential: IssuedCredential, key: IssuerKey) -> bool:
    try:
        public_key = serialization.load_pem_public_key(key.public_key_pem.encode())
        assert isinstance(public_key, Ed25519PublicKey)
        public_key.verify(
            base64.b64decode(credential.signature), _canonical(credential.canonical_payload)
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _record_verification(
    db: Session,
    *,
    version: DocumentVersion,
    adapter_code: str,
    status: IssuerVerificationStatus,
    message: str,
    evidence: dict[str, Any],
    simulated_source: bool,
    credential: IssuedCredential | None,
    actor: User | None,
) -> IssuerVerification:
    verification = IssuerVerification(
        document_version_id=version.id,
        issuer_credential_id=credential.id if credential else None,
        adapter_code=adapter_code,
        status=status,
        message=message,
        evidence=evidence,
        simulated_source=simulated_source,
        verified_by=actor.id if actor else None,
    )
    db.add(verification)
    db.flush()
    record_audit(
        db,
        event_type="issuer.verification_recorded",
        actor=actor,
        application_id=db.get(Document, version.document_id).application_id,
        entity_type="issuer_verification",
        entity_id=verification.id,
        payload={
            "status": status.value,
            "adapter_code": adapter_code,
            "simulated_source": simulated_source,
            "credential_id": credential.credential_id if credential else None,
        },
    )
    db.commit()
    db.refresh(verification)
    return verification


def verify_demo_credential(
    db: Session,
    *,
    version: DocumentVersion,
    credential_id: str | None,
    actor: User | None,
) -> IssuerVerification:
    credential: IssuedCredential | None = None
    if credential_id:
        credential = db.scalar(
            select(IssuedCredential).where(IssuedCredential.credential_id == credential_id)
        )
    else:
        credential = db.scalar(
            select(IssuedCredential)
            .where(
                IssuedCredential.document_version_id == version.id,
                IssuedCredential.status == CredentialStatus.ACTIVE,
            )
            .order_by(IssuedCredential.issued_at.desc())
            .limit(1)
        )
    if credential is None:
        return _record_verification(
            db,
            version=version,
            adapter_code="demo",
            status=IssuerVerificationStatus.NOT_FOUND,
            message="No synthetic demo credential is registered for this document version.",
            evidence={"synthetic": True, "credential_id": credential_id},
            simulated_source=True,
            credential=None,
            actor=actor,
        )
    key = db.get(IssuerKey, credential.issuer_key_id)
    evidence = {
        "synthetic": True,
        "credential_id": credential.credential_id,
        "issuer_code": key.issuer_code if key else None,
        "document_sha256_match": credential.document_sha256 == version.sha256,
        "document_version_id": str(version.id),
    }
    if key is None or not _verify_signature(credential, key):
        return _record_verification(
            db,
            version=version,
            adapter_code="demo",
            status=IssuerVerificationStatus.MISMATCH,
            message="The synthetic demo credential signature did not verify.",
            evidence=evidence,
            simulated_source=True,
            credential=credential,
            actor=actor,
        )
    if credential.status is not CredentialStatus.ACTIVE:
        return _record_verification(
            db,
            version=version,
            adapter_code="demo",
            status=IssuerVerificationStatus.MISMATCH,
            message=f"The synthetic demo credential is {credential.status.value.lower()}.",
            evidence=evidence,
            simulated_source=True,
            credential=credential,
            actor=actor,
        )
    if credential.expires_at and credential.expires_at < datetime.now(timezone.utc):
        return _record_verification(
            db,
            version=version,
            adapter_code="demo",
            status=IssuerVerificationStatus.MISMATCH,
            message="The synthetic demo credential has expired.",
            evidence=evidence,
            simulated_source=True,
            credential=credential,
            actor=actor,
        )
    if credential.document_sha256 != version.sha256:
        return _record_verification(
            db,
            version=version,
            adapter_code="demo",
            status=IssuerVerificationStatus.MISMATCH,
            message="The synthetic demo credential is bound to different document content.",
            evidence=evidence,
            simulated_source=True,
            credential=credential,
            actor=actor,
        )
    return _record_verification(
        db,
        version=version,
        adapter_code="demo",
        status=IssuerVerificationStatus.VERIFIED,
        message="Ed25519 signature and document hash verified against the synthetic demo issuer key. This is not an AICTE or external issuer confirmation.",
        evidence=evidence,
        simulated_source=True,
        credential=credential,
        actor=actor,
    )


def verify_external_issuer(
    db: Session,
    *,
    version: DocumentVersion,
    actor: User | None,
) -> IssuerVerification:
    return _record_verification(
        db,
        version=version,
        adapter_code="external-simulated",
        status=IssuerVerificationStatus.SOURCE_UNAVAILABLE,
        message="No authorised external issuer source is configured. This result is simulated and is not a verification outcome.",
        evidence={"synthetic": True, "external_source_configured": False},
        simulated_source=True,
        credential=None,
        actor=actor,
    )


def list_verifications(db: Session, version_id: uuid.UUID) -> list[IssuerVerification]:
    return list(
        db.scalars(
            select(IssuerVerification)
            .where(IssuerVerification.document_version_id == version_id)
            .order_by(IssuerVerification.created_at.desc())
        )
    )


def revoke_demo_credential(
    db: Session, credential: IssuedCredential, actor: User | None = None
) -> IssuedCredential:
    credential.status = CredentialStatus.REVOKED
    credential.revoked_at = datetime.now(timezone.utc)
    record_audit(
        db,
        event_type="issuer.demo_credential_revoked",
        actor=actor,
        entity_type="issued_credential",
        entity_id=credential.id,
        payload={"credential_id": credential.credential_id, "synthetic": True},
    )
    db.commit()
    db.refresh(credential)
    return credential
