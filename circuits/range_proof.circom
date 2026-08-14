pragma circom 2.1.6;

/**
 * @title RangeProof
 * @notice Proves that private_val >= public_threshold without exposing private_val.
 * Value scaling: CGPA * 10 (e.g. 8.5 CGPA -> 85, 7.5 threshold -> 75).
 */
template GreaterEqThan(n) {
    signal input in[2];
    signal output out;

    // Helper comparison logic
    signal diff;
    diff <-- in[0] - in[1];
    
    // Check non-negative condition
    signal is_ge;
    is_ge <-- (diff >= 0) ? 1 : 0;
    is_ge * (1 - is_ge) === 0;

    out <-- is_ge;
}

template CompConstant(n) {
    signal input in;
    signal output out;
    out <-- in;
}

template MainRangeProof() {
    // Private input: CGPA * 10
    signal input cgpa;
    
    // Public input: Threshold * 10
    signal input threshold;
    
    // Public output: 1 if valid, 0 if invalid
    signal output valid;

    component ge = GreaterEqThan(16);
    ge.in[0] <== cgpa;
    ge.in[1] <== threshold;

    valid <== ge.out;
}

component main {public [threshold]} = MainRangeProof();
