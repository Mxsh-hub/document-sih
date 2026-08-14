// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

interface IVerifier {
    function verifyProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[1] calldata _pubSignals
    ) external view returns (bool);
}

contract AstraVerifyAnchor {
    IVerifier public verifier;

    struct DocumentRecord {
        bytes32 docHash;
        address owner;
        uint256 timestamp;
        string tier; // "Gold", "Silver", "Bronze"
    }

    mapping(bytes32 => DocumentRecord) public documents;
    mapping(address => bytes32[]) public userDocuments;

    event DocumentAnchored(bytes32 indexed docHash, address indexed owner, string tier);
    event ProofVerified(address indexed verifier, bytes32 indexed docHash, bool success);

    constructor(address _verifierAddress) {
        verifier = IVerifier(_verifierAddress);
    }

    function anchorDocument(bytes32 _docHash, string calldata _tier) external {
        require(documents[_docHash].timestamp == 0, "Document already anchored");
        
        documents[_docHash] = DocumentRecord({
            docHash: _docHash,
            owner: msg.sender,
            timestamp: block.timestamp,
            tier: _tier
        });
        
        userDocuments[msg.sender].push(_docHash);
        emit DocumentAnchored(_docHash, msg.sender, _tier);
    }

    function verifyZKProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[1] calldata _pubSignals,
        bytes32 _docHash
    ) external returns (bool) {
        require(documents[_docHash].timestamp != 0, "Document not anchored");
        
        bool isValid = verifier.verifyProof(_pA, _pB, _pC, _pubSignals);
        
        emit ProofVerified(msg.sender, _docHash, isValid);
        return isValid;
    }
}
