from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ApiError
from app.db.enums import ZkChainStatus, ZkProofStatus
from app.db.models import Application, ZkChallenge, ZkProof
from app.services.audit import record_audit
from app.services.zkp_verifier import _compute_vkey_hash, _find_vkey_path, verify_groth16


def _can_access_application(actor, application: Application) -> bool:
    if application.institution_id == actor.institution_id:
        return True
    return actor.role.value in {"REVIEWER", "APPROVER", "ADMIN", "AUDITOR"}


def create_challenge(db: Session, *, actor, application_id, audience: str) -> ZkChallenge:
    if not settings.ZKP_ENABLED:
        raise ApiError(503, "ZKP_DISABLED", "Zero-knowledge proof support is disabled in this deployment.")
    application = db.get(Application, application_id)
    if not application:
        raise ApiError(404, "NOT_FOUND", "Application not found.")
    if not _can_access_application(actor, application):
        raise ApiError(403, "FORBIDDEN", "Not permitted to request a proof for this application.")
    if application.institution_id != actor.institution_id and actor.role.value != "ADMIN":
        raise ApiError(403, "FORBIDDEN", "Only the applicant institution or an administrator can request a proof.")

    request_hash = str(secrets.randbits(126) + 1)
    challenge = ZkChallenge(
        application_id=application.id,
        created_by=actor.id,
        request_hash=request_hash,
        audience=audience.strip(),
        threshold=str(settings.FACULTY_THRESHOLD_SCALED),
        circuit_name="faculty_threshold",
        circuit_version="2.0.0",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.ZKP_CHALLENGE_TTL_SECONDS),
    )
    db.add(challenge)
    db.flush()
    record_audit(
        db,
        event_type="zkp.challenge_created",
        actor=actor,
        entity_type="zk_challenge",
        entity_id=challenge.id,
        application_id=application.id,
        payload={
            "request_hash": request_hash,
            "audience": challenge.audience,
            "threshold": challenge.threshold,
            "expires_at": challenge.expires_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(challenge)
    return challenge


def submit_proof(
    db: Session,
    *,
    actor,
    challenge_id,
    document_version_id,
    proof: dict,
    public_signals: list[str],
) -> ZkProof:
    if not settings.ZKP_ENABLED:
        raise ApiError(503, "ZKP_DISABLED", "Zero-knowledge proof support is disabled in this deployment.")
    challenge = db.get(ZkChallenge, challenge_id)
    if not challenge:
        raise ApiError(404, "NOT_FOUND", "Proof challenge not found.")
    application = db.get(Application, challenge.application_id)
    if not application:
        raise ApiError(404, "NOT_FOUND", "Application not found.")
    if not _can_access_application(actor, application):
        raise ApiError(403, "FORBIDDEN", "Not permitted to attach proof to this application.")
    now = datetime.now(timezone.utc)
    if challenge.consumed_at is not None:
        raise ApiError(409, "CONFLICT", "This proof challenge has already been used.")
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise ApiError(400, "CHALLENGE_EXPIRED", "This proof challenge has expired.")
    if challenge.circuit_name != "faculty_threshold":
        raise ApiError(400, "VALIDATION_FAILED", "Unsupported circuit for this challenge.")

    if len(public_signals) != 5:
        raise ApiError(400, "VALIDATION_FAILED", "public_signals must have 5 elements: [valid, nullifier, commitment, threshold, requestHash].")
    if any(not isinstance(value, str) for value in public_signals):
        raise ApiError(400, "VALIDATION_FAILED", "public_signals must be decimal strings.")
    if public_signals[3] != challenge.threshold or public_signals[4] != challenge.request_hash:
        raise ApiError(400, "VALIDATION_FAILED", "Public signals must match the server-issued threshold and requestHash.")
    if public_signals[0] != "1":
        raise ApiError(400, "PROOF_INVALID", "The proof does not establish the required threshold.")
    if len(public_signals[1]) > 200 or len(public_signals[2]) > 200:
        raise ApiError(400, "VALIDATION_FAILED", "Invalid public signal length.")

    vkey_path = _find_vkey_path(challenge.circuit_name)
    if not vkey_path:
        raise ApiError(500, "CONFIG_ERROR", "Pinned verification key not available.")
    vkey_hash = _compute_vkey_hash(vkey_path)

    verified, verification_result, vkey_hash_res = verify_groth16(
        challenge.circuit_name, proof, public_signals
    )
    vkey_hash = vkey_hash_res or vkey_hash

    nullifier = public_signals[1]
    commitment = public_signals[2]
    existing = db.scalar(select(ZkProof).where(ZkProof.nullifier == nullifier))
    if existing:
        record_audit(
            db,
            event_type="zkp.proof_rejected",
            actor=actor,
            entity_type="zk_challenge",
            entity_id=challenge.id,
            application_id=application.id,
            payload={"reason": "duplicate_nullifier", "nullifier": nullifier},
        )
        db.commit()
        raise ApiError(409, "CONFLICT", "This nullifier has already been used.")

    if not verified:
        record_audit(
            db,
            event_type="zkp.proof_rejected",
            actor=actor,
            entity_type="zk_challenge",
            entity_id=challenge.id,
            application_id=application.id,
            payload={"reason": "verification_failed", "result": verification_result},
        )
        db.commit()
        raise ApiError(400, "PROOF_INVALID", "Groth16 verification failed.")

    zk = ZkProof(
        application_id=application.id,
        document_version_id=document_version_id,
        circuit_name=challenge.circuit_name,
        circuit_version=challenge.circuit_version,
        request_hash=challenge.request_hash,
        commitment=commitment,
        nullifier=nullifier,
        threshold=challenge.threshold,
        public_signals=public_signals,
        proof_json=proof,
        status=ZkProofStatus.VERIFIED,
        vkey_hash=vkey_hash,
        verified_by=actor.id,
        verified_at=now,
        verification_result=verification_result,
        chain_status=ZkChainStatus.NOT_REQUESTED,
    )
    challenge.consumed_at = now
    db.add(zk)
    db.flush()
    record_audit(
        db,
        event_type="zkp.proof_verified",
        actor=actor,
        entity_type="zk_proof",
        entity_id=zk.id,
        application_id=application.id,
        payload={
            "circuit_name": challenge.circuit_name,
            "circuit_version": challenge.circuit_version,
            "threshold": challenge.threshold,
            "request_hash": challenge.request_hash,
            "commitment": commitment,
            "nullifier": nullifier,
            "vkey_hash": vkey_hash,
        },
    )
    db.commit()
    db.refresh(zk)
    return zk


def list_proofs(db: Session, *, actor, application_id):
    application = db.get(Application, application_id)
    if not application:
        raise ApiError(404, "NOT_FOUND", "Application not found.")
    if not _can_access_application(actor, application):
        raise ApiError(403, "FORBIDDEN", "Not permitted to view proofs for this application.")
    return db.scalars(select(ZkProof).where(ZkProof.application_id == application_id).order_by(ZkProof.created_at.desc())).all()


def get_proof(db: Session, *, actor, proof_id):
    zk = db.get(ZkProof, proof_id)
    if not zk:
        raise ApiError(404, "NOT_FOUND", "Proof not found.")
    if not _can_access_application(actor, zk.application):
        raise ApiError(403, "FORBIDDEN", "Not permitted to view this proof.")
    return zk


def anchor_proof(db: Session, *, actor, zk_proof_id: str):
    zk = db.get(ZkProof, zk_proof_id)
    if not zk:
        raise ApiError(404, "NOT_FOUND", "Proof not found.")
    if zk.status != ZkProofStatus.VERIFIED:
        raise ApiError(400, "VALIDATION_FAILED", "Only verified proofs can be anchored.")
    if actor.role.value not in {"REVIEWER", "APPROVER", "ADMIN"}:
        raise ApiError(403, "FORBIDDEN", "Only staff can request anchoring.")
    from app.services.blockchain_anchor import request_proof_anchor

    return request_proof_anchor(db, zk=zk, actor=actor)
