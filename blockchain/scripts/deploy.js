const hre = require("hardhat");

async function main() {
  console.log("Deploying Verifier...");
  const Verifier = await hre.ethers.getContractFactory("Groth16Verifier");
  const verifier = await Verifier.deploy();
  await verifier.waitForDeployment();
  const verifierAddress = await verifier.getAddress();
  console.log(`Verifier deployed to: ${verifierAddress}`);

  console.log("Deploying AstraVerifyAnchor...");
  const Anchor = await hre.ethers.getContractFactory("AstraVerifyAnchor");
  const anchor = await Anchor.deploy(verifierAddress);
  await anchor.waitForDeployment();
  const anchorAddress = await anchor.getAddress();
  console.log(`AstraVerifyAnchor deployed to: ${anchorAddress}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
