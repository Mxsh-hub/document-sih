from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from helpers import create_application

BACKEND = Path(__file__).resolve().parents[1]
# npm writes both a POSIX shim and Windows `.cmd` wrapper into `.bin`. Windows
# cannot exec the extensionless shell script directly.
SNARKJS = BACKEND.parent / "circuits" / "node_modules" / ".bin" / "snarkjs"
if os.name == "nt":
    SNARKJS = SNARKJS.with_name("snarkjs.cmd")
WASM = BACKEND / "circuits" / "faculty_threshold" / "faculty_threshold.wasm"
ZKEY = BACKEND / "circuits" / "faculty_threshold" / "faculty_threshold_final.zkey"


def make_proof(tmp_path, *, value: int, threshold: str, request_hash: str, secret: int = 424242, blinding: int = 31337):
    proof_path = tmp_path / "proof.json"
    public_path = tmp_path / "public.json"
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(
        json.dumps(
            {
                "value": str(value),
                "blinding": str(blinding),
                "secret": str(secret),
                "threshold": str(threshold),
                "requestHash": str(request_hash),
            }
        )
    )
    result = subprocess.run(
        [
            str(SNARKJS),
            "groth16",
            "fullprove",
            str(inputs_path),
            str(WASM),
            str(ZKEY),
            str(proof_path),
            str(public_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(proof_path.read_text()), json.loads(public_path.read_text())


def challenge(client, headers, application_id):
    response = client.post(
        "/api/v1/zkp/challenges",
        headers=headers,
        json={"application_id": application_id, "audience": "synthetic-reviewer"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_valid_threshold_proof_is_verified_and_not_reusable(client, applicant_headers, reviewer_headers, tmp_path):
    application = create_application(client, applicant_headers)
    issued = challenge(client, applicant_headers, application["id"])
    assert issued["threshold"] == "700"

    proof, public_signals = make_proof(
        tmp_path, value=850, threshold=issued["threshold"], request_hash=issued["request_hash"]
    )
    response = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={
            "challenge_id": issued["id"],
            "proof": proof,
            "public_signals": public_signals,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "VERIFIED"
    assert body["circuit_name"] == "faculty_threshold"
    assert "proof_json" not in body
    assert body["nullifier"] == public_signals[1]

    replay = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={"challenge_id": issued["id"], "proof": proof, "public_signals": public_signals},
    )
    assert replay.status_code == 409

    listing = client.get(
        f"/api/v1/zkp/applications/{application['id']}/proofs", headers=applicant_headers
    )
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1

    # Applicant from another institution cannot read it.
    from conftest import login

    other = login(client, "applicant2@example.test")
    denied = client.get(f"/api/v1/zkp/applications/{application['id']}/proofs", headers=other)
    assert denied.status_code == 403

    reviewer_view = client.get(
        f"/api/v1/zkp/applications/{application['id']}/proofs", headers=reviewer_headers
    )
    assert reviewer_view.status_code == 200


def test_threshold_below_required_is_rejected(client, applicant_headers, tmp_path):
    application = create_application(client, applicant_headers)
    issued = challenge(client, applicant_headers, application["id"])
    proof, public_signals = make_proof(
        tmp_path, value=600, threshold=issued["threshold"], request_hash=issued["request_hash"]
    )
    assert public_signals[0] == "0"
    response = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={"challenge_id": issued["id"], "proof": proof, "public_signals": public_signals},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROOF_INVALID"


def test_tampered_public_signals_and_proof_are_rejected(client, applicant_headers, tmp_path):
    application = create_application(client, applicant_headers)
    issued = challenge(client, applicant_headers, application["id"])
    proof, public_signals = make_proof(
        tmp_path, value=800, threshold=issued["threshold"], request_hash=issued["request_hash"]
    )

    wrong_threshold = list(public_signals)
    wrong_threshold[3] = "1"
    response = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={"challenge_id": issued["id"], "proof": proof, "public_signals": wrong_threshold},
    )
    assert response.status_code == 400

    tampered = json.loads(json.dumps(proof))
    tampered["pi_a"][0] = "1"
    response = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={"challenge_id": issued["id"], "proof": tampered, "public_signals": public_signals},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROOF_INVALID"


def test_expired_challenge_and_cross_institution_challenge_are_rejected(
    client, applicant_headers, applicant2_headers, monkeypatch
):
    application = create_application(client, applicant_headers)
    denied = client.post(
        "/api/v1/zkp/challenges",
        headers=applicant2_headers,
        json={"application_id": application["id"], "audience": "other"},
    )
    assert denied.status_code == 403

    monkeypatch.setattr("app.config.settings.ZKP_CHALLENGE_TTL_SECONDS", -1)
    expired = challenge(client, applicant_headers, application["id"])
    from pathlib import Path as _Path

    proof, public_signals = make_proof(
        _Path("/tmp"), value=800, threshold=expired["threshold"], request_hash=expired["request_hash"]
    )
    response = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={"challenge_id": expired["id"], "proof": proof, "public_signals": public_signals},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHALLENGE_EXPIRED"


def test_anchoring_is_advisory_and_explicit_when_disabled(client, applicant_headers, reviewer_headers, tmp_path):
    application = create_application(client, applicant_headers)
    issued = challenge(client, applicant_headers, application["id"])
    proof, public_signals = make_proof(
        tmp_path, value=850, threshold=issued["threshold"], request_hash=issued["request_hash"]
    )
    verified = client.post(
        "/api/v1/zkp/proofs",
        headers=applicant_headers,
        json={"challenge_id": issued["id"], "proof": proof, "public_signals": public_signals},
    ).json()
    anchored = client.post(
        "/api/v1/zkp/anchor",
        headers=reviewer_headers,
        json={"zk_proof_id": verified["id"]},
    )
    assert anchored.status_code == 200
    assert anchored.json()["chain_status"] == "FAILED"
    assert "disabled" in anchored.json()["error_message"].lower()
