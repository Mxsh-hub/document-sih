#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

BUILD=build/faculty_threshold
mkdir -p "$BUILD"

./node_modules/.bin/circom2 faculty_threshold.circom \
  --r1cs --wasm --sym -l node_modules -o "$BUILD"

./node_modules/.bin/snarkjs groth16 setup \
  "$BUILD/faculty_threshold.r1cs" \
  powersOfTau28_hez_final_12.ptau \
  "$BUILD/faculty_threshold_0000.zkey"

./node_modules/.bin/snarkjs zkey contribute \
  "$BUILD/faculty_threshold_0000.zkey" \
  "$BUILD/faculty_threshold_final.zkey" \
  --name="AstraVerify synthetic development contribution" \
  -e="astraverify-development-only-entropy-not-a-trusted-ceremony" <<< "y"

./node_modules/.bin/snarkjs zkey export verificationkey \
  "$BUILD/faculty_threshold_final.zkey" \
  "$BUILD/verification_key.json"

./node_modules/.bin/snarkjs zkey export solidityverifier \
  "$BUILD/faculty_threshold_final.zkey" \
  FacultyThresholdVerifier.sol

cp "$BUILD/faculty_threshold_js/faculty_threshold.wasm" \
  "$BUILD/faculty_threshold.wasm"

echo "Built circuit artifacts in $BUILD"
echo "IMPORTANT: the development contribution is not a trusted ceremony."
