// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";

interface IFacultyThresholdVerifier {
    function verifyProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[5] calldata _pubSignals
    ) external view returns (bool);
}

/// @title AstraVerifyAnchorV2
/// @notice Tamper-evidence and proof-anchoring registry. Only hashes and public
///         signals are stored on chain; private witness values never leave the
///         proving environment. Anchoring is advisory and does not by itself
///         establish authenticity or regulatory approval.
contract AstraVerifyAnchorV2 is AccessControl {
    bytes32 public constant ANCHOR_ROLE = keccak256("ANCHOR_ROLE");
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");

    IFacultyThresholdVerifier public immutable verifier;

    struct AnchorRecord {
        bytes32 payloadHash;
        bytes32 nullifier;
        uint256 threshold;
        uint256 requestHash;
        address submitter;
        uint64 anchoredAt;
        bool exists;
    }

    mapping(bytes32 => AnchorRecord) public anchors;
    mapping(bytes32 => bytes32) public nullifierToPayload;
    mapping(bytes32 => bool) public proofAnchored;

    event PayloadAnchored(
        bytes32 indexed payloadHash,
        bytes32 indexed nullifier,
        address indexed submitter,
        uint256 threshold,
        uint256 requestHash,
        uint64 anchoredAt
    );
    event ProofVerified(
        bytes32 indexed payloadHash,
        bytes32 indexed nullifier,
        address indexed verifier,
        bool success
    );

    error AlreadyAnchored(bytes32 payloadHash);
    error NullifierAlreadyUsed(bytes32 nullifier);
    error InvalidPublicSignals();
    error ProofVerificationFailed();
    error ZeroHash();

    constructor(address verifierAddress, address admin) {
        require(verifierAddress != address(0), "verifier required");
        require(admin != address(0), "admin required");
        verifier = IFacultyThresholdVerifier(verifierAddress);
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ANCHOR_ROLE, admin);
        _grantRole(VERIFIER_ROLE, admin);
    }

    function anchorPayload(bytes32 payloadHash, bytes32 nullifier) external onlyRole(ANCHOR_ROLE) {
        if (payloadHash == bytes32(0) || nullifier == bytes32(0)) revert ZeroHash();
        if (anchors[payloadHash].exists) revert AlreadyAnchored(payloadHash);
        if (nullifierToPayload[nullifier] != bytes32(0)) revert NullifierAlreadyUsed(nullifier);
        anchors[payloadHash] = AnchorRecord({
            payloadHash: payloadHash,
            nullifier: nullifier,
            threshold: 0,
            requestHash: 0,
            submitter: msg.sender,
            anchoredAt: uint64(block.timestamp),
            exists: true
        });
        nullifierToPayload[nullifier] = payloadHash;
        emit PayloadAnchored(payloadHash, nullifier, msg.sender, 0, 0, uint64(block.timestamp));
    }

    /// @notice Verify a Groth16 proof and anchor its public signals without
    ///         storing the proof or private inputs.
    function verifyAndAnchor(
        uint[2] calldata pA,
        uint[2][2] calldata pB,
        uint[2] calldata pC,
        uint[5] calldata pubSignals,
        bytes32 payloadHash
    ) external onlyRole(ANCHOR_ROLE) returns (bool) {
        if (payloadHash == bytes32(0)) revert ZeroHash();
        if (anchors[payloadHash].exists) revert AlreadyAnchored(payloadHash);
        if (pubSignals[0] != 1) revert InvalidPublicSignals();
        bytes32 nullifier = bytes32(pubSignals[1]);
        if (pubSignals[1] == 0 || pubSignals[2] == 0) revert InvalidPublicSignals();
        if (nullifierToPayload[nullifier] != bytes32(0)) revert NullifierAlreadyUsed(nullifier);

        bool success = verifier.verifyProof(pA, pB, pC, pubSignals);
        if (!success) revert ProofVerificationFailed();

        anchors[payloadHash] = AnchorRecord({
            payloadHash: payloadHash,
            nullifier: nullifier,
            threshold: pubSignals[3],
            requestHash: pubSignals[4],
            submitter: msg.sender,
            anchoredAt: uint64(block.timestamp),
            exists: true
        });
        nullifierToPayload[nullifier] = payloadHash;
        proofAnchored[payloadHash] = true;
        emit PayloadAnchored(
            payloadHash,
            nullifier,
            msg.sender,
            pubSignals[3],
            pubSignals[4],
            uint64(block.timestamp)
        );
        emit ProofVerified(payloadHash, nullifier, msg.sender, success);
        return success;
    }

    function recordExists(bytes32 payloadHash) external view returns (bool) {
        return anchors[payloadHash].exists;
    }
}
