const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deployer:", deployer.address);

  const Verifier = await hre.ethers.getContractFactory("FacultyThresholdVerifier");
  const verifier = await Verifier.deploy();
  await verifier.waitForDeployment();
  const verifierAddress = await verifier.getAddress();
  console.log("FacultyThresholdVerifier:", verifierAddress);

  const Anchor = await hre.ethers.getContractFactory("AstraVerifyAnchorV2");
  const anchor = await Anchor.deploy(verifierAddress, deployer.address);
  await anchor.waitForDeployment();
  const anchorAddress = await anchor.getAddress();
  console.log("AstraVerifyAnchorV2:", anchorAddress);

  console.log("\nSet backend/frontend environment variables:");
  console.log(`FACULTY_THRESHOLD_VERIFIER_ADDRESS=${verifierAddress}`);
  console.log(`ASTRA_VERIFY_ANCHOR_ADDRESS=${anchorAddress}`);
  console.log("Then set BLOCKCHAIN_ENABLED=true and BLOCKCHAIN_PROOF_ANCHORING_ENABLED=true.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
