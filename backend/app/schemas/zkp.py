from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ZkChallengeCreate(BaseModel):
    application_id: uuid.UUID
    audience: str = Field(min_length=3, max_length=200)


class ZkChallengeOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    request_hash: str
    audience: str
    threshold: str
    circuit_name: str
    circuit_version: str
    expires_at: datetime


class ZkProofSubmitRequest(BaseModel):
    challenge_id: uuid.UUID
    document_version_id: uuid.UUID | None = None
    proof: dict[str, Any]
    public_signals: list[str]


class ZkProofOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    document_version_id: uuid.UUID | None = None
    circuit_name: str
    circuit_version: str
    request_hash: str
    commitment: str
    nullifier: str
    threshold: str
    public_signals: list[str]
    status: str
    chain_status: str
    chain_tx_hash: str | None = None
    chain_network: str | None = None
    anchored_at: datetime | None = None
    verified_at: datetime | None = None
    verification_result: dict[str, Any]
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ZkProofListOut(BaseModel):
    items: list[ZkProofOut]


class ZkAnchorRequest(BaseModel):
    zk_proof_id: uuid.UUID


class ZkVerifyStatusOut(BaseModel):
    circuit_name: str
    circuit_version: str
    vkey_pinned: bool
    vkey_hash: str | None = None
    legacy_circuit_allowed: bool
    verification_mode: str
    warnings: list[str]
