npx snarkjs groth16 setup range_proof.r1cs powersOfTau28_hez_final_12.ptau range_proof_0000.zkey
npx snarkjs zkey contribute range_proof_0000.zkey range_proof_final.zkey --name="AstraVerify" -v -e="entropy123"
npx snarkjs zkey export verificationkey range_proof_final.zkey verification_key.json
npx snarkjs zkey export solidityverifier range_proof_final.zkey Verifier.sol
