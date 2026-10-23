from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings


class Groth16VerificationError(Exception):
    pass


def _compute_vkey_hash(vkey_path: Path) -> str:
    data = vkey_path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _find_vkey_path(circuit_name: str) -> Path | None:
    if circuit_name == "faculty_threshold":
        if settings.ZKP_VKEY_PATH.exists():
            return settings.ZKP_VKEY_PATH
        # try alternative locations
        alt = Path(__file__).resolve().parents[2] / "circuits" / "faculty_threshold" / "verification_key.json"
        if alt.exists():
            return alt
    if circuit_name == "range_proof" and settings.ZKP_ALLOW_LEGACY_CIRCUIT:
        if settings.ZKP_LEGACY_VKEY_PATH.exists():
            return settings.ZKP_LEGACY_VKEY_PATH
        alt = Path(__file__).resolve().parents[3] / "circuits" / "verification_key.json"
        if alt.exists():
            return alt
    return None


def verify_groth16(
    circuit_name: str,
    proof: dict[str, Any],
    public_signals: list[str],
) -> tuple[bool, dict[str, Any], str | None]:
    """Verify a Groth16 proof using pinned verification key.

    For the sound faculty_threshold circuit, verification uses server-side
    snarkjs verification with the pinned verification_key.json. The legacy
    range_proof circuit is disabled by default due to known unsoundness and
    requires explicit opt-in.
    """
    warnings: list[str] = []
    if circuit_name == "range_proof":
        if not settings.ZKP_ALLOW_LEGACY_CIRCUIT:
            return False, {"error": "LEGACY_CIRCUIT_DISABLED", "message": "range_proof is disabled due to known unsound constraints."}, None
        warnings.append("LEGACY_UNSOUND: range_proof circuit is known to be unsound and must not be trusted.")

    vkey_path = _find_vkey_path(circuit_name)
    if vkey_path is None or not vkey_path.exists():
        return False, {"error": "VKEY_NOT_FOUND", "message": "Pinned verification key not found."}, None

    vkey_hash = _compute_vkey_hash(vkey_path)

    # Try snarkjs verification if available
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            proof_path = tmp / "proof.json"
            public_path = tmp / "public.json"
            proof_path.write_text(json.dumps(proof))
            public_path.write_text(json.dumps(public_signals))
            # find snarkjs
            candidates = [
                settings.SNARKJS_BIN,
                str(Path(__file__).resolve().parents[2] / "circuits" / "node_modules" / ".bin" / "snarkjs"),
                str(Path(__file__).resolve().parents[3] / "circuits" / "node_modules" / ".bin" / "snarkjs"),
            ]
            snarkjs_bin = next((item for item in candidates if item and Path(item).exists()), "snarkjs")
            result = subprocess.run(
                [snarkjs_bin, "groth16", "verify", str(vkey_path), str(public_path), str(proof_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = (result.stdout or "") + (result.stderr or "")
            verified = result.returncode == 0 and "OK" in output
            return verified, {"mode": "snarkjs", "output": output.strip(), "warnings": warnings}, vkey_hash
    except Exception as exc:
        # Fallback: for faculty_threshold with known structure do basic sanity checks only in development
        # Production should have snarkjs; but tests need to work without it installed globally
        if circuit_name == "faculty_threshold":
            # Try to use node with local snarkjs
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)
                    proof_path = tmp / "proof.json"
                    public_path = tmp / "public.json"
                    proof_path.write_text(json.dumps(proof))
                    public_path.write_text(json.dumps(public_signals))
                    verify_js = Path(__file__).resolve().parents[2] / "circuits" / "verify_proof.js"
                    if verify_js.exists():
                        result = subprocess.run(
                            ["node", str(verify_js), str(vkey_path), str(public_path), str(proof_path)],
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                        output = (result.stdout or "") + (result.stderr or "")
                        verified = result.returncode == 0 and "OK" in output
                        return verified, {"mode": "node-snarkjs-script", "output": output.strip(), "warnings": warnings}, vkey_hash
            except Exception:
                pass
        return False, {"error": "VERIFICATION_FAILED", "message": str(exc), "warnings": warnings}, vkey_hash


def export_solidity_calldata(proof: dict[str, Any], public_signals: list[str]) -> list[Any]:
    vkey_path = _find_vkey_path("faculty_threshold")
    if vkey_path is None:
        raise Groth16VerificationError("Verification key not found.")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        proof_path = tmp / "proof.json"
        public_path = tmp / "public.json"
        proof_path.write_text(json.dumps(proof))
        public_path.write_text(json.dumps(public_signals))
        candidates = [
            settings.SNARKJS_BIN,
            str(Path(__file__).resolve().parents[2] / "circuits" / "node_modules" / ".bin" / "snarkjs"),
            str(Path(__file__).resolve().parents[3] / "circuits" / "node_modules" / ".bin" / "snarkjs"),
        ]
        snarkjs_bin = next((item for item in candidates if item and Path(item).exists()), "snarkjs")
        result = subprocess.run(
            [snarkjs_bin, "zkey", "export", "soliditycalldata", str(public_path), str(proof_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise Groth16VerificationError(result.stderr or "Failed to export Solidity calldata.")
        # snarkjs emits comma-separated Solidity argument groups without an
        # outer JSON array ("[pA],[pB],[pC],[pub]"). Wrap it for parsing.
        return json.loads("[" + result.stdout.strip() + "]")
