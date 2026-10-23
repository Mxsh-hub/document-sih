from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ApiError
from app.db.enums import ZkChainStatus
from app.db.models import ZkProof
from app.services.audit import record_audit
from app.services.zkp_verifier import export_solidity_calldata


def _payload_hash(zk: ZkProof) -> bytes:
    canonical = json.dumps(
        {
            "zk_proof_id": str(zk.id),
            "application_id": str(zk.application_id),
            "commitment": zk.commitment,
            "nullifier": zk.nullifier,
            "threshold": zk.threshold,
            "request_hash": zk.request_hash,
            "vkey_hash": zk.vkey_hash,
            "circuit_name": zk.circuit_name,
            "circuit_version": zk.circuit_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).digest()


def _finish(db: Session, zk: ZkProof, status: ZkChainStatus, *, actor, error: str | None = None, tx_hash: str | None = None) -> ZkProof:
    zk.chain_status = status
    zk.error_message = error
    if tx_hash:
        zk.chain_tx_hash = tx_hash
        zk.anchored_at = datetime.now(timezone.utc)
    db.add(zk)
    record_audit(
        db,
        event_type="zkp.anchor_completed" if status == ZkChainStatus.ANCHORED else "zkp.anchor_failed",
        actor=actor,
        entity_type="zk_proof",
        entity_id=zk.id,
        application_id=zk.application_id,
        payload={"status": status.value, "tx_hash": tx_hash, "error": error, "network": zk.chain_network},
    )
    db.commit()
    db.refresh(zk)
    return zk


def request_proof_anchor(db: Session, *, zk: ZkProof, actor) -> ZkProof:
    """Anchor a verified proof on the configured EVM chain.

    Only public signals and a canonical payload hash are submitted. Private
    witness values and raw documents never leave the backend. Anchoring is
    advisory tamper-evidence and is explicitly non-blocking.
    """
    if not settings.BLOCKCHAIN_ENABLED or not settings.BLOCKCHAIN_PROOF_ANCHORING_ENABLED:
        return _finish(
            db,
            zk,
            ZkChainStatus.FAILED,
            actor=actor,
            error="Blockchain anchoring is disabled in this configuration; verification remains advisory.",
        )
    if not settings.BLOCKCHAIN_PRIVATE_KEY or not settings.ASTRA_VERIFY_ANCHOR_ADDRESS:
        return _finish(
            db,
            zk,
            ZkChainStatus.FAILED,
            actor=actor,
            error="Blockchain is enabled but no funded key or anchor address is configured.",
        )

    try:
        from web3 import Web3
    except Exception:
        return _finish(
            db,
            zk,
            ZkChainStatus.FAILED,
            actor=actor,
            error="web3 is not installed; install requirements.txt to enable anchoring.",
        )

    try:
        artifact_path = settings.BLOCKCHAIN_ARTIFACT_PATH
        artifact = json.loads(artifact_path.read_text())
        w3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL))
        if not w3.is_connected():
            raise RuntimeError("RPC endpoint is unavailable.")
        account = w3.eth.account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(settings.ASTRA_VERIFY_ANCHOR_ADDRESS),
            abi=artifact["abi"],
        )
        calldata = export_solidity_calldata(zk.proof_json, zk.public_signals)
        payload_hash = _payload_hash(zk)
        public_signals = [int(value) for value in zk.public_signals]

        def _to_ints(value):
            if isinstance(value, str):
                return int(value, 16) if value.startswith("0x") else int(value)
            if isinstance(value, list):
                return [_to_ints(item) for item in value]
            return value

        proof_a, proof_b, proof_c = (_to_ints(item) for item in calldata[:3])
        zk.chain_network = settings.BLOCKCHAIN_NETWORK
        transaction = contract.functions.verifyAndAnchor(
            proof_a, proof_b, proof_c, public_signals, payload_hash
        ).build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "chainId": w3.eth.chain_id,
                "gas": 1_500_000,
                "maxFeePerGas": w3.to_wei(2, "gwei"),
                "maxPriorityFeePerGas": w3.to_wei(1, "gwei"),
            }
        )
        signed = account.sign_transaction(transaction)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError("Anchor transaction reverted.")
        return _finish(
            db,
            zk,
            ZkChainStatus.ANCHORED,
            actor=actor,
            tx_hash=tx_hash.hex(),
        )
    except Exception as exc:
        return _finish(
            db,
            zk,
            ZkChainStatus.FAILED,
            actor=actor,
            error=f"Anchoring failed: {str(exc)[:400]}",
        )
