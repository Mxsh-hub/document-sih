# AstraVerify — AICTE Application Validation Prototype

**Status: working prototype for controlled demonstration. Not production-ready. All institutions, records, issuer responses, and sample documents are synthetic.**

AstraVerify adapts the original privacy-preserving credential-wallet demo into a regulatory decision-support platform for the SIH problem statement:

> **AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification**

The MVP category is **Extension of Approval (EoA)**. The platform is **advisory**: it does not prove forgery, does not authenticate documents by itself, and never records an approval or rejection without an authorized human decision.

The implementation follows [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md). Phases 1–10 are implemented and verified locally; Phase 11 documentation and demo controls are in this repository.

---

## What is implemented

| Area | Status | Evidence |
|---|---|---|
| PostgreSQL persistence, migrations, seed data | **Working** | SQLAlchemy 2 models + Alembic; head `4eeaf2dbd8cc` |
| Authentication, refresh tokens, RBAC, tenant isolation | **Working** | Argon2id, JWT, object-level checks; pytest |
| EoA applications, checklist snapshots, submission gate | **Working** | `/api/v1/applications`, checklist and state machine |
| Document upload, immutable versions, SHA-256, local/S3 storage | **Working** | `/api/v1/applications/{id}/documents`, signed downloads |
| OCR and evidence-linked extraction | **Working** | pdfplumber → PyMuPDF → Tesseract; page/bbox/confidence |
| Versioned rules, validation runs, findings, record snapshots | **Working** | Configurable synthetic rules; no auto-rejection |
| Demo issuer with real Ed25519 signatures | **Working** | `/api/v1/issuers/*`; simulated responses labelled |
| Advisory anomaly and duplicate signals | **Working** | Heuristics only; never a forgery claim |
| Infrastructure evidence presence/completeness | **Working** | No computer-vision claims in the MVP |
| Review queue, assignment, rectification, escalation, decisions, alerts | **Working** | `/api/v1/review`, `/api/v1/applications/*/review-actions` |
| Hash-chained audit trail with verification | **Working** | `/api/v1/admin/audit-events/verify` |
| Sound Groth16 faculty-threshold proof | **Working** | `circuits/faculty_threshold.circom`; server-side snarkjs verification |
| Tamper-evidence anchoring on local Hardhat | **Working, optional** | `AstraVerifyAnchorV2`; hash-only anchoring; disabled by default |
| Compliance demo UI | **Working** | `/compliance` route in the React app |
| Synthetic evaluation harness | **Working** | `backend/evaluation/run_evaluation.py` |
| Real AICTE/DigiLocker/issuer API access | **Not implemented** | No authorized credentials exist |
| ML deepfake/forgery detection | **Not implemented** | Legacy stubs remain, clearly not used as evidence |
| Playwright browser tests / CI | **Not implemented** | Backend, contract and build checks were run manually |

Full requirement status: [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md). Historical audit of the original wallet code: [`docs/REPOSITORY_AUDIT.md`](docs/REPOSITORY_AUDIT.md).

---

## Prerequisites

- Python 3.11+ (verified on 3.13)
- Node.js 18+ and npm
- PostgreSQL 16 (local Docker container `astra-postgres` on port `55432` is used below)
- Tesseract OCR on `PATH`, or set `TESSERACT_CMD`
- Optional: local Hardhat node for anchoring; a funded Amoy key only if deploying there

---

## Quick start

### 1. PostgreSQL

```bash
docker run -d --name astra-postgres \
  -e POSTGRES_USER=astra -e POSTGRES_PASSWORD=astra -e POSTGRES_DB=astra \
  -p 55432:5432 postgres:16
```

The default connection string is:

```text
postgresql+psycopg://astra:astra@localhost:55432/astra
```

### 2. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit JWT_SECRET and DOWNLOAD_SIGNING_KEY; each must be at least 32 characters.

./venv/bin/alembic upgrade head
python -m app.seed

python -m uvicorn app.main:app --reload --port 8000
```

API: `http://localhost:8000` · Swagger: `http://localhost:8000/docs` · Health: `/health`

`app.seed` is idempotent. It creates the synthetic institutions, EoA checklist and rules, demo issuer key, and these accounts (password `ChangeMe123!` unless `SEED_PASSWORD` is set):

| Account | Role |
|---|---|
| `applicant@example.test` | Applicant |
| `applicant2@example.test` | Applicant (second institution) |
| `reviewer@example.test` | Reviewer |
| `approver@example.test` | Approver |
| `admin@example.test` | Admin |
| `auditor@example.test` | Auditor |

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173/compliance` for the new workflow console. The legacy `/wallet`, `/verifier`, and `/issuer` routes are preserved but are not the compliance workflow.

The console uses `VITE_API_BASE_URL` (default `http://localhost:8000`). There is no Vite proxy.

### 4. Tests

```bash
cd backend
./venv/bin/pytest
```

**Last run: 2026-10-24 — 61 passed.** The suite uses PostgreSQL database `astra_test` and local storage. It covers authorization, uploads, extraction, rules, issuers, anomalies, review/audit, security, ZKP, and an end-to-end application-to-decision flow.

```bash
cd blockchain
npm install
npx hardhat test
```

**Last run: 2026-10-24 — 5 passed.** Contract tests cover access control, hash-only anchoring, nullifier reuse, and proof verification failure.

```bash
cd frontend
npm run build
```

**Last run: 2026-10-24 — succeeded.** `npm run lint` still fails because no ESLint config exists.

### 5. Synthetic evaluation

```bash
cd backend
./venv/bin/python evaluation/run_evaluation.py
```

The script creates and drops a dedicated `astra_evaluation` database. **Never point it at `astra` or `astra_test`.** Results are written to `backend/evaluation/results.json`.

Last measured synthetic results (2026-10-23):

| Metric | Result |
|---|---|
| OCR field exact match | 100/100 fields across 20 synthetic documents |
| OCR processing time | median 43.94 ms, p95 47.66 ms |
| Rule outcomes | 27/27 labels across 3 cases |
| Anomaly signals | precision 1.0, recall 1.0 over 3 synthetic applications |
| Issuer scenarios | 3/3 expected states |
| Disclaimer | Metrics describe only the synthetic corpus; they are **not** AICTE accuracy claims |

---

## ZKP and blockchain

### Sound faculty-threshold circuit

`circuits/faculty_threshold.circom` replaces the unsound legacy range proof. It:

- Commits to `value` with `Poseidon(value, blinding)`.
- Proves `value >= threshold` with `GreaterEqThan(32)`.
- Derives a request-bound nullifier from `Poseidon(secret, requestHash)`.
- Exposes `[valid, nullifier, commitment, threshold, requestHash]`.

The server issues a short-lived challenge with a random `requestHash` and a configured threshold, verifies the proof with snarkjs and a pinned verification key, rejects `valid != 1`, and enforces globally unique nullifiers and one-time challenges. Raw private inputs and raw proof JSON are not exposed by the API.

**Limits:** the proof shows the committed private value meets the threshold. It does **not** prove that the value is true, that it came from a verified credential, or that the holder is a real person. The demo issuer and threshold are synthetic.

Rebuild artifacts:

```bash
cd circuits
npm install
./build_faculty_threshold.sh
```

Copy `faculty_threshold.wasm`, `faculty_threshold_final.zkey`, and `verification_key.json` to `backend/circuits/faculty_threshold/` and `frontend/public/circuits/faculty_threshold/`. Copy `FacultyThresholdVerifier.sol` to `blockchain/contracts/`.

### Tamper-evidence anchoring

`blockchain/contracts/AstraVerifyAnchorV2.sol` uses OpenZeppelin `AccessControl` and stores only:

- A SHA-256 payload hash of the proof record.
- The nullifier, threshold, and request hash.
- Submitter and timestamp.

The backend exports Solidity calldata from snarkjs and submits `verifyAndAnchor` with a configured service key. Anchoring is non-blocking; failure is recorded as `FAILED` and never blocks review or decisions. It is disabled by default.

```bash
cd blockchain
npx hardhat node                         # terminal 1
npx hardhat run scripts/deploy_v2.js --network localhost   # terminal 2
```

Set the printed addresses and a funded local key in `backend/.env`:

```text
BLOCKCHAIN_ENABLED=true
BLOCKCHAIN_PROOF_ANCHORING_ENABLED=true
BLOCKCHAIN_NETWORK=hardhat
BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545
BLOCKCHAIN_PRIVATE_KEY=0x...
ASTRA_VERIFY_ANCHOR_ADDRESS=0x...
FACULTY_THRESHOLD_VERIFIER_ADDRESS=0x...
```

**Last verified end-to-end: 2026-10-24** against a local Hardhat node, deployment at `0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512`, proof anchored with `chain_status=ANCHORED` and a real transaction hash. Amoy was not deployed because no funded test key was provided.

Chain anchoring proves that a hash existed at a point in time. It does not prove document authenticity or regulatory compliance.

---

## Important limitations

1. **No real authority integration.** No AICTE portal, AICTE database, DigiLocker production access, or issuer API credentials exist. Synthetic adapters are labelled.
2. **Synthetic rules.** Approval Process Handbook checklists, thresholds, and citations were not supplied. Seeded thresholds and citations are synthetic and configurable; they are not official AICTE rules.
3. **Advisory findings.** Anomaly scores and hash matches are never proof of forgery or authenticity. Final decisions require an authorized official.
4. **ZKP identity binding.** The nullifier prevents replay within a challenge but is not bound to a verified real-world identity or an issued credential.
5. **Dev trusted setup.** The Groth16 setup is a development ceremony, not a production MPC ceremony.
6. **Retention/encryption.** A configurable retention job, field-level encryption for sensitive extracts, and a formal data-handling policy are not implemented. Local storage is used by default; S3/MinIO is supported by configuration.
7. **Legacy code remains.** The original wallet components, `services/deepfake.py`, `services/risk.py`, `attestation.py`, and `validate-zk` are preserved but are not part of the new compliance flow. Do not present them as real capabilities. The old `range_proof.circom` is unsound and blocked by default.
8. **No browser automation suite or CI.** The backend test suite, contract tests, frontend build, and one live anchor flow were executed; full browser E2E and CI are not set up.

---

## Repository layout

```text
backend/              FastAPI app, PostgreSQL models, Alembic, services, tests, evaluation
backend/circuits/     Pinned sound-circuit artifacts used by server-side verification
frontend/             React/Vite app: /compliance plus legacy /wallet, /verifier, /issuer
blockchain/           Hardhat project, AstraVerifyAnchorV2, generated verifier, tests
circuits/             Circom source and build tooling for faculty_threshold
docs/                 Audit, traceability, architecture, data model, API contracts, test plan
SPEC.md               Target-system specification and MVP boundary
IMPLEMENTATION_ROADMAP.md   Phased plan and acceptance criteria
AGENTS.md             Working rules for contributors and AI agents
```

---

## Documentation

- [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) — phased plan, mandatory rules, acceptance criteria
- [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md) — current requirement status with evidence and gaps
- [`SPEC.md`](SPEC.md) — roles, scope, workflows, circuit/chain specification, acceptance criteria
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — containers, modules, data flows, security, deployment
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — schema, constraints, audit chain, new ZKP tables
- [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md) — endpoint catalog, authorization matrix, errors
- [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) — test levels, golden cases, executed results, evaluation metrics
- [`docs/REPOSITORY_AUDIT.md`](docs/REPOSITORY_AUDIT.md) — original audit, simulated capabilities, legacy risks

---

## License

Built for the Smart India Hackathon (SIH). All rights reserved.
