const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AstraVerifyAnchorV2", function () {
  async function deploy() {
    const [admin, anchor, outsider] = await ethers.getSigners();
    const Verifier = await ethers.getContractFactory("MockFacultyThresholdVerifier");
    const verifier = await Verifier.deploy();
    const Anchor = await ethers.getContractFactory("AstraVerifyAnchorV2");
    const contract = await Anchor.deploy(await verifier.getAddress(), admin.address);
    await contract.waitForDeployment();
    await contract.connect(admin).grantRole(await contract.ANCHOR_ROLE(), anchor.address);
    return { contract, verifier, admin, anchor, outsider };
  }

  const payload = ethers.keccak256(ethers.toUtf8Bytes("synthetic-application-payload"));
  const nullifier = ethers.keccak256(ethers.toUtf8Bytes("synthetic-nullifier"));
  const proofA = [1, 2];
  const proofB = [[1, 2], [3, 4]];
  const proofC = [5, 6];

  it("anchors hash-only payloads and rejects duplicates", async function () {
    const { contract, anchor } = await deploy();
    await expect(contract.connect(anchor).anchorPayload(payload, nullifier))
      .to.emit(contract, "PayloadAnchored");

    const record = await contract.anchors(payload);
    expect(record.payloadHash).to.equal(payload);
    expect(record.nullifier).to.equal(nullifier);
    expect(record.exists).to.equal(true);
    expect(await contract.recordExists(payload)).to.equal(true);

    await expect(contract.connect(anchor).anchorPayload(payload, nullifier))
      .to.be.revertedWithCustomError(contract, "AlreadyAnchored");
  });

  it("restricts anchoring to ANCHOR_ROLE", async function () {
    const { contract, outsider } = await deploy();
    await expect(contract.connect(outsider).anchorPayload(payload, nullifier))
      .to.be.revertedWithCustomError(contract, "AccessControlUnauthorizedAccount");
  });

  it("verifies and anchors public signals only", async function () {
    const { contract, anchor } = await deploy();
    const signals = [1, BigInt(nullifier), 9, 700, 42];
    await expect(contract.connect(anchor).verifyAndAnchor(proofA, proofB, proofC, signals, payload))
      .to.emit(contract, "ProofVerified")
      .withArgs(payload, nullifier, anchor.address, true);

    const record = await contract.anchors(payload);
    expect(record.threshold).to.equal(700);
    expect(record.requestHash).to.equal(42);
    expect(record.submitter).to.equal(anchor.address);
    expect(await contract.proofAnchored(payload)).to.equal(true);
  });

  it("rejects invalid threshold signal and reused nullifier", async function () {
    const { contract, anchor } = await deploy();
    await expect(
      contract.connect(anchor).verifyAndAnchor(proofA, proofB, proofC, [0, nullifier, 9, 700, 42], payload)
    ).to.be.revertedWithCustomError(contract, "InvalidPublicSignals");

    const signals = [1, BigInt(nullifier), 9, 700, 42];
    await contract.connect(anchor).verifyAndAnchor(proofA, proofB, proofC, signals, payload);
    const otherPayload = ethers.keccak256(ethers.toUtf8Bytes("other"));
    await expect(
      contract.connect(anchor).verifyAndAnchor(proofA, proofB, proofC, signals, otherPayload)
    ).to.be.revertedWithCustomError(contract, "NullifierAlreadyUsed");
  });

  it("rejects a proof that fails verifier", async function () {
    const { contract, verifier, anchor } = await deploy();
    await verifier.setResult(false);
    const signals = [1, BigInt(nullifier), 9, 700, 42];
    await expect(
      contract.connect(anchor).verifyAndAnchor(proofA, proofB, proofC, signals, payload)
    ).to.be.revertedWithCustomError(contract, "ProofVerificationFailed");
  });
});
