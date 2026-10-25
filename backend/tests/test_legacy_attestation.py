"""Legacy demo attestation (gated behind LEGACY_API_ENABLED).

The point of these checks is honesty, not interoperability: the proof is a real
Ed25519 signature over the canonical payload, but it is clearly labelled as a
demo proof type rather than a W3C Data Integrity proof.
"""

from __future__ import annotations

from app.services.attestation import generate_attestation_vc, verify_attestation_vc


def _vc():
    return generate_attestation_vc(
        holder_did="did:example:synthetic-holder",
        holder_name="Synthetic Holder",
        extracted_data={"degree": "B.Tech", "cgpa": 8.1},
        original_issuer="Synthetic University",
    )


def test_demo_attestation_verifies_and_is_labelled_as_demo():
    vc = _vc()
    assert vc.proof.type == "AstraEd25519Signature"
    assert vc.credentialSubject.additional_data["synthetic"] is True
    assert vc.credentialSubject.additional_data["verification_method"] == "synthetic_demo_pipeline"
    assert verify_attestation_vc(vc) is True


def test_demo_attestation_detects_tampering():
    vc = _vc()
    tampered = vc.model_copy(deep=True)
    tampered.credentialSubject.name = "Someone Else"
    assert verify_attestation_vc(tampered) is False
