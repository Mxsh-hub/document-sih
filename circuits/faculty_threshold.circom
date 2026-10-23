pragma circom 2.0.0;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";

// Sound faculty-eligibility threshold proof.
//
// Public signals, in order:
//   [valid, nullifier, commitment, threshold, requestHash]
//
// Private inputs: value (scaled CGPA / eligibility score), blinding, secret.
// The circuit enforces value >= threshold. The commitment binds value without
// revealing it, and the nullifier is domain-separated by requestHash.
//
// This demonstrates the mechanism only. It does not establish the truth of the
// private value or bind a nullifier to a verified real-world identity.
template FacultyThresholdProof() {
    signal input value;
    signal input blinding;
    signal input secret;
    signal input threshold;
    signal input requestHash;

    signal output valid;
    signal output nullifier;
    signal output commitment;

    component commitmentHasher = Poseidon(2);
    commitmentHasher.inputs[0] <== value;
    commitmentHasher.inputs[1] <== blinding;
    commitment <== commitmentHasher.out;

    component nullifierHasher = Poseidon(2);
    nullifierHasher.inputs[0] <== secret;
    nullifierHasher.inputs[1] <== requestHash;
    nullifier <== nullifierHasher.out;

    component thresholdCheck = GreaterEqThan(32);
    thresholdCheck.in[0] <== value;
    thresholdCheck.in[1] <== threshold;
    valid <== thresholdCheck.out;
}

component main {public [threshold, requestHash]} = FacultyThresholdProof();
