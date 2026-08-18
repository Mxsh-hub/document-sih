# AstraVerify

**Privacy-Preserving, AI-Driven Decentralized Identity & Verification Protocol**

AstraVerify is a next-generation document verification system built for the modern web. It combines the power of **Zero-Knowledge Proofs (ZKPs)**, **Artificial Intelligence**, and **Blockchain Technology** to allow users to prove things about their credentials (e.g., "My CGPA is > 7.5") without ever revealing the actual underlying document or data.

## Key Features

*   **Zero-Knowledge Proofs (ZKP)**: Uses `snarkjs` and WebAssembly (WASM) to generate mathematical proofs directly in the user's browser. Privacy is mathematically guaranteed.
*   **AI Verification Swarm**: An intelligent multi-agent pipeline (Forensics, Deepfake Detection, Risk Scoring) that automatically analyzes and authenticates user-uploaded documents.
*   **Blockchain Anchoring**: Every verified document is issued as a W3C Verifiable Credential and cryptographically anchored to a Polygon-compatible smart contract for immutable trust.
*   **Tiered Trust Architecture**:
    *   **Gold**: Natively trusted documents (e.g., via DigiLocker OAuth).
    *   **Silver**: Uploaded PDFs forensically authenticated by the AI Swarm.
    *   **Bronze**: Physical document photos processed via OCR and AI.
*   **Triple-Portal System**:
    *   **User Wallet**: Secure local storage for credentials and the Prover Engine.
    *   **Verifier Portal**: Dynamic criteria builder and ZK Proof validator.
    *   **Issuer Portal**: Institutional dashboard to issue and anchor credentials to the blockchain.

---

## Tech Stack

*   **Frontend**: React, Vite, Tailwind CSS, Framer Motion, `lucide-react`.
*   **Cryptography**: `snarkjs`, `circom`, `ethers.js`.
*   **Backend**: Python, FastAPI, OpenCV, PyTesseract, PyMuPDF.
*   **Blockchain**: Solidity, Hardhat, local RPC.

---

## Getting Started

To run the AstraVerify stack locally, you will need three terminal windows to run the Blockchain, Backend, and Frontend concurrently.

### 1. Blockchain (Hardhat Node)
Start the local Ethereum-compatible blockchain and deploy the smart contracts.
```bash
cd blockchain
npm install
npx hardhat node
```
*(Leave this terminal running. The RPC will be available at `http://127.0.0.1:8545`)*

### 2. Backend (FastAPI & AI Swarm)
Start the AI analysis and attestation server.
```bash
cd backend
python -m venv venv
# Activate virtual environment
# Windows: .\venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```
*(Leave this terminal running. The API will be available at `http://localhost:8000`)*

### 3. Frontend (React / Vite)
Start the User Wallet, Verifier, and Issuer portals.
```bash
cd frontend
npm install
npm run dev
```
*(Open your browser to `http://localhost:5173`)*

---

## How to Test the Flow

1.  **Issue a Credential**: Navigate to the **Issuer Portal** (`/issuer`). Issue a B.Tech Degree. You will see a blockchain transaction hash generated as it anchors to the Hardhat node.
2.  **Generate a Request**: Navigate to the **Verifier Portal** (`/verifier`). Use the Criteria Builder to set a requirement (e.g., `cgpa > 8.0`). Click "Generate Request Payload" and copy the JSON.
3.  **Prove it**: Open the **User Wallet** (`/wallet`). Click on your imported Degree credential. Paste the JSON from the Verifier Portal.
4.  **Zero-Knowledge Magic**: Click "Compute Witness & Prove". The browser will execute the `.wasm` circuit locally and generate a Groth16 payload.
5.  **Verify**: Copy the generated ZKP payload, go back to the Verifier Portal, and paste it. The system will mathematically verify the proof and query the smart contract to ensure the credential's anchor is valid!

---

## License
This project is built for the Smart India Hackathon (SIH). All rights reserved.
