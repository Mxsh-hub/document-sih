from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.config import settings
from app.db.base import get_db
from app.schemas.zkp import (
    ZkAnchorRequest,
    ZkChallengeCreate,
    ZkChallengeOut,
    ZkProofListOut,
    ZkProofOut,
    ZkProofSubmitRequest,
    ZkVerifyStatusOut,
)
from app.services import zkp as zkp_service
from app.services.zkp_verifier import _compute_vkey_hash, _find_vkey_path

router = APIRouter()


@router.get("/status", response_model=ZkVerifyStatusOut)
def zkp_status(user: CurrentUser):
    warnings = []
    if settings.ZKP_ALLOW_LEGACY_CIRCUIT:
        warnings.append("Legacy range_proof circuit is explicitly enabled.")
    vkey_path = _find_vkey_path("faculty_threshold")
    if not vkey_path and not settings.ZKP_ALLOW_LEGACY_CIRCUIT:
        warnings.append("Pinned verification key for faculty_threshold not found.")
    if not settings.ZKP_ENABLED:
        warnings.append("ZKP support is disabled by configuration.")
    return ZkVerifyStatusOut(
        circuit_name="faculty_threshold",
        circuit_version="2.0.0",
        vkey_pinned=bool(vkey_path and vkey_path.exists()),
        vkey_hash=_compute_vkey_hash(vkey_path) if vkey_path and vkey_path.exists() else None,
        legacy_circuit_allowed=settings.ZKP_ALLOW_LEGACY_CIRCUIT,
        verification_mode="server-side-groth16-pinned-vkey" if settings.ZKP_ENABLED else "disabled",
        warnings=warnings,
    )


@router.post("/challenges", response_model=ZkChallengeOut)
def create_challenge(
    payload: ZkChallengeCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    return zkp_service.create_challenge(
        db,
        actor=user,
        application_id=payload.application_id,
        audience=payload.audience,
    )


@router.post("/proofs", response_model=ZkProofOut)
def submit_proof(
    payload: ZkProofSubmitRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    return zkp_service.submit_proof(
        db,
        actor=user,
        challenge_id=payload.challenge_id,
        document_version_id=payload.document_version_id,
        proof=payload.proof,
        public_signals=payload.public_signals,
    )


@router.get("/applications/{application_id}/proofs", response_model=ZkProofListOut)
def list_proofs(
    application_id,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    items = zkp_service.list_proofs(db, actor=user, application_id=application_id)
    return ZkProofListOut(items=items)


@router.get("/proofs/{proof_id}", response_model=ZkProofOut)
def get_proof(
    proof_id,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    return zkp_service.get_proof(db, actor=user, proof_id=proof_id)


@router.post("/anchor", response_model=ZkProofOut)
def anchor(
    payload: ZkAnchorRequest,
    user: Annotated[CurrentUser, Depends(require_roles("REVIEWER", "APPROVER", "ADMIN"))],
    db: Annotated[Session, Depends(get_db)],
):
    return zkp_service.anchor_proof(db, actor=user, zk_proof_id=payload.zk_proof_id)
