# AstraVerify — AICTE Application Validation Prototype

**Status: working prototype for controlled demonstration. Not production-ready. All institutions, records, issuer responses, and sample documents are synthetic.**

AstraVerify adapts the original privacy-preserving credential-wallet demo into a regulatory decision-support platform for the SIH problem statement:

> **AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification**

The MVP category is **Extension of Approval (EoA)**. The platform is **advisory**: it does not prove forgery, does not authenticate documents by itself, and never records an approval or rejection without an authorized human decision.

The implementation follows [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md). Phases 1–10 are implemented and verified locally; Phase 11 documentation and demo controls are in this repository, together with post-MVP hardening milestones M0–M6 (credibility containment, evidence viewer, structured declaration + three-way consistency, advisory QR/signature inspection, report export + alert dispositions, pre-submission self-check, and demo hardening + evaluation).

New here? Jump to [Run the site locally](#run-the-site-locally) and [Pages and functionality](#pages-and-functionality).

---

## What is implemented

| Area | Status | Evidence |
|---|---|---|
| PostgreSQL persistence, migrations, seed data | **Working** | SQLAlchemy 2 models + Alembic; head `c3d5e7f9a1b2` |
| Authentication, refresh tokens, RBAC, tenant isolation | **Working** | Argon2id, JWT, object-level checks; pytest |
| EoA applications, checklist snapshots, submission gate | **Working** | `/api/v1/applications`, checklist and state machine |
| Document upload, immutable versions, SHA-256, local/S3 storage | **Working** | `/api/v1/applications/{id}/documents`, signed downloads |
| OCR and evidence-linked extraction | **Working** | pdfplumber → PyMuPDF → Tesseract; page/bbox/confidence |
| Versioned rules, validation runs, findings, record snapshots | **Working** | Configurable synthetic rules; no auto-rejection |
| Demo issuer with real Ed25519 signatures | **Working** | `/api/v1/issuers/*`; simulated responses labelled |
| Advisory anomaly and duplicate signals | **Working** | Heuristics only; never a forgery claim |
| Infrastructure evidence presence/completeness | **Working** | No computer-vision claims in the MVP |
| Review queue, assignment, rectification, escalation, decisions, alerts | **Working** | `/api/v1/review`, `/api/v1/applications/*/review-actions` |
| Alert dispositions and stale-alert supersede | **Working** | `alerts.payload.disposition`; `FALSE_POSITIVE`/`ACCEPTED_RISK` require a note |
| Structured declaration + three-way consistency | **Working, advisory** | `application_declarations`; declared vs extracted vs synthetic record |
| Evidence workspace with document rendering | **Working** | `/compliance` renders the cited page and bounding box |
| Advisory QR and PDF signature-structure inspection | **Working, advisory** | Local decode only; no fetch, no CMS/certificate/trust-chain verification |
| Advisory JSON/Markdown/HTML report export | **Working, advisory** | `GET /api/v1/applications/{id}/report`; audited, unsigned, no PDF |
| Read-only pre-submission self-check | **Working** | `GET /api/v1/applications/{id}/self-check`; same gate as `submit` |
| Hash-chained audit trail with verification | **Working** | `/api/v1/admin/audit-events/verify` |
| Sound Groth16 faculty-threshold proof | **Working** | `circuits/faculty_threshold.circom`; server-side snarkjs verification |
| Tamper-evidence anchoring on local Hardhat | **Working, optional** | `AstraVerifyAnchorV2`; hash-only anchoring; disabled by default |
| Compliance demo UI | **Working** | `/compliance` route in the React app |
| Scripted demo walkthrough | **Working** | `backend/scripts/demo_smoke.py` (live HTTP) and [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) |
| Synthetic evaluation harness | **Working** | `backend/evaluation/run_evaluation.py` (includes advisory controls) |
| Real AICTE/DigiLocker/issuer API access | **Not implemented** | No authorized credentials exist |
| ML deepfake/forgery detection | **Not implemented** | Legacy stubs remain, clearly not used as evidence |
| Playwright browser tests / CI | **Not implemented** | Backend, contract and build checks were run manually |

Full requirement status: [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md). Historical audit of the original wallet code: [`docs/REPOSITORY_AUDIT.md`](docs/REPOSITORY_AUDIT.md).

---

## Run the site locally

Three processes, plus an optional fourth:

| Process | Port | Purpose |
|---|---|---|
| PostgreSQL 16 (Docker) | `55432` | All persistent data |
| FastAPI backend (uvicorn) | `8000` | REST API, OCR, extraction, rules, review, audit, anchoring |
| React frontend (Vite) | `5173` | The UI |
| Hardhat node (optional) | `8545` | Local chain for hash-only anchoring and the legacy issuer demo |

The repository defaults are already wired to these ports, so the only file you must edit is `backend/.env`, and only to set two secrets.

> **Windows notes.** Use `.\venv\Scripts\Activate.ps1` to activate the venv, run tools as `.\venv\Scripts\python.exe -m <module>` (for example `.\venv\Scripts\python.exe -m alembic upgrade head`), and replace `cp` with `Copy-Item`. PowerShell does not accept `&&` between commands — run them one per line.

### Prerequisites

- Python 3.10+ (verified on 3.10.11 on Windows; `backend/app/db/enums.py` carries a `StrEnum` shim for 3.10)
- Node.js 18+ and npm
- PostgreSQL 16 — Docker is the simplest route (below)
- Tesseract OCR on `PATH`, or set `TESSERACT_CMD`. Without it, scanned pages report `OCR_ENGINE_UNAVAILABLE`; text PDFs still extract normally.
- Optional: a local Hardhat node for anchoring and the legacy issuer portal

### 1. Start PostgreSQL

```bash
docker run -d --name astra-postgres \
  -e POSTGRES_USER=astra -e POSTGRES_PASSWORD=astra -e POSTGRES_DB=astra \
  -p 55432:5432 postgres:16
```

Default connection string, already in `.env.example`:

```text
postgresql+psycopg://astra:astra@localhost:55432/astra
```

If the container already exists from an earlier session, `docker start astra-postgres` is enough.

### 2. Start the backend (terminal 1)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate            # Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                # Windows: Copy-Item .env.example .env
```

Open `backend/.env` and set both secrets to **at least 32 characters** — the app refuses to import otherwise, so a plain `uvicorn` start fails by design:

```text
JWT_SECRET=<32 or more characters>
DOWNLOAD_SIGNING_KEY=<32 or more characters>
```

Create the schema, seed the synthetic data, then run the API:

```bash
./venv/bin/alembic upgrade head
./venv/bin/python -m app.seed
./venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

```powershell
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m app.seed
.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

`python -m app.seed` is idempotent. It creates the synthetic institutions, the EoA checklist and rule set, the demo issuer key, and these accounts (password `ChangeMe123!` unless `SEED_PASSWORD` is set):

| Account | Role |
|---|---|
| `applicant@example.test` | Applicant |
| `applicant2@example.test` | Applicant (second institution) |
| `reviewer@example.test` | Reviewer |
| `approver@example.test` | Approver |
| `admin@example.test` | Admin |
| `auditor@example.test` | Auditor |

### 3. Start the frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

`npm --prefix frontend run dev` works from the repository root too.

- Site: `http://localhost:5173`
- Compliance console: `http://localhost:5173/compliance`

There is no Vite proxy: the app calls `VITE_API_BASE_URL`, which defaults to `http://localhost:8000`. If the backend is not running, the console reports `Failed to fetch`. `frontend/.env` is optional and only needed to override defaults:

```text
VITE_API_BASE_URL=http://localhost:8000
VITE_RPC_URL=http://127.0.0.1:8545
VITE_CONTRACT_ADDRESS=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
```

`VITE_*` values are baked in when the dev server starts, so restart Vite after editing that file.

### 4. Optional: local Hardhat chain

Only needed to demo hash-only anchoring (the console's proof panel then shows `chain_status`) and the legacy `/issuer` portal. Both degrade explicitly when the chain is absent.

```bash
cd blockchain
npm install
npx hardhat node                                            # terminal 3
npx hardhat run scripts/deploy.js    --network localhost    # terminal 4
npx hardhat run scripts/deploy_v2.js --network localhost
```

A fresh node always produces the same deterministic addresses. [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) §4 lists them with the `backend/.env` and `frontend/.env` values. Restarting the node wipes chain state, so re-run both deploy scripts.

### 5. Stop and reset

`Ctrl+C` stops the backend and Vite; `docker stop astra-postgres` stops the database.

To wipe local demo data and start clean:

```bash
docker exec -it astra-postgres psql -U astra -d astra -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
cd backend
./venv/bin/alembic upgrade head
./venv/bin/python -m app.seed
```

---

## Pages and functionality

One React app serves five routes. `/compliance` is the product; `/`, `/wallet`, `/verifier`, and `/issuer` are the explainer page and the preserved legacy wallet demo.

| Route | Page | Primary user | Role |
|---|---|---|---|
| `/` | Landing / explainer | anyone | Marketing surface for the prototype |
| `/compliance` | AICTE compliance console | all six seeded roles | **The EoA workflow** |
| `/wallet` | Consumer credential wallet | legacy demo | Not part of EoA |
| `/verifier` | Verifier portal | legacy demo | Not part of EoA |
| `/issuer` | Issuer portal | legacy demo | Not part of EoA |

### `/` — Landing page

Explains the prototype and routes visitors into the console.

- Hero with the framing line and an **Open Compliance Console** button.
- **Live ZKP demo** — a CGPA slider compared against a fixed 7.5 threshold in the browser. It is an interactive illustration of the threshold idea, **not** a proof being generated or verified; real proving happens in the console.
- **The workflow** — ingest → extract → validate → review.
- A closing "decision support, not automated decisions" section.

Copy on this page is illustrative. The authoritative status is [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md).

### `/compliance` — AICTE compliance console

The only page that implements the EoA workflow. Panels appear according to role.

**Sign-in.** Pick one of the seeded accounts; there is no self-registration. The session is stored in `localStorage` as `astra-session`.

**Dashboard.** Counters per application status from `GET /api/v1/dashboard/summary`, scoped to the caller's role.

**Application list.** Only applications the caller may see. An applicant creates one per cycle (`YYYY-MM`, validated); a second active application for the same institution + category + cycle returns `409 STATE_CONFLICT`. Reviewers see submitted/unassigned work; approver, admin, and auditor get broader staff scope. An applicant never sees another institution's application.

**Structured declaration.** Affiliation, programmes and intake, faculty count, and previous-approval reference. Editable only by the applicant while the application is `DRAFT`, read-only otherwise. Each save bumps a version and is audited (`application.declaration_saved`). The declaration is **never verified** — validation only compares it against documents and synthetic records.

**Pre-submission self-check.** Applicant-only, on `DRAFT` or `RECTIFICATION_REQUESTED`. Lists blocking items using the same helper that gates `submit`, so the preview cannot disagree with the real gate, plus advisory warnings that never block. It is read-only: no rule run, no alerts, no audit event, and no prediction of approval.

**Evidence checklist.** The checklist snapshotted at creation, with per-item status and, for an applicant, an upload control. Uploads return `202 Accepted` while processing runs inline by default, so findings are usually visible as soon as the request returns. Submission requires every required item to have a document or a justification.

**Faculty threshold proof.** Optional Groth16 proof against a server-issued challenge, generated in the browser with `snarkjs` loaded from a CDN. Only the commitment, nullifier, threshold, request hash, and `valid` bit are public. Needs network access for the CDN; the rest of the console does not.

**Human review (staff only).** Assign to me, add a note, request rectification, verify the audit hash chain, and export the advisory report as JSON, Markdown, or HTML — every export is audited and none is signed or official. Approver and admin additionally record an explicit approve/reject with a rationale. The system never records a decision on its own.

**Evidence workspace.** Findings from a validation run, each with the cited field and a bounding box drawn on the rendered document (pdf.js for PDFs, plain raster for OCR'd scans). PDF boxes are in points; raster boxes are in pixels.

**Alert panel (staff only).** Acknowledge and resolve alerts. Resolution requires a disposition, and `FALSE_POSITIVE` or `ACCEPTED_RISK` additionally requires a note. Stale finding/anomaly alerts are auto-superseded with a system actor. Resolving an alert changes no finding and no decision.

**Technical inspection (staff only, advisory).** Decodes a QR payload locally (OpenCV, up to 10 pages at 150 dpi) and records the preview, digest, and host — the payload is **never fetched**. Separately, inspects a PDF's signature dictionary and `ByteRange` structurally. CMS, certificates, revocation, and the trust chain are **not** verified, and the panel refuses to describe a result as verified.

**Anomalies, issuer verification, audit history.** Advisory anomaly signals (cross-application hash reuse, shared identifiers, PDF metadata heuristics), issuer adapter results labelled `simulated source` where applicable, and recent audit events with sequence and hash prefix.

Every panel ends at a human decision. No finding, score, hash match, or proof changes an application's status by itself.

### `/wallet` — Legacy credential wallet

The original consumer wallet, kept for history. Credentials exist only in `localStorage` (`astra_wallet_credentials`) alongside a locally generated `did:web:astraverify:user:…`; there is no backend wallet.

- **Dashboard** — your DID and stored credentials.
- **Import** — a simulated import path; DigiLocker-style responses and `AstraSimulatedProof` placeholders are fabricated and labelled.
- **Credential detail** — the stored credential JSON.
- **Prove** — a browser Groth16 flow over the legacy artifacts.

None of this represents a real credential, a real issuer response, or a verified identity.

### `/verifier` — Legacy verifier portal

- **Criteria builder** — assemble a criteria payload and generate its JSON. The JSON is produced in the browser and is not evaluated by the backend.
- **Proof validator** — paste a Groth16 proof, check it with `snarkjs` against the pinned verification key, and optionally ask MetaMask to call the legacy `AstraVerifyAnchor.verifyZKProof`. It reports the mathematical check and, separately, whether the anchor call succeeded. It does not decide compliance.

### `/issuer` — Legacy issuer portal

Synthetic credential issuance with an optional on-chain anchor:

1. The form posts to `POST /api/v1/issuer/issue`, which builds a W3C-shaped credential and attaches a demo HMAC-SHA256 integrity tag, explicitly typed `AstraDemoHmacIntegrity` — it is **not** a signature. The response includes the SHA3-256 hash of the credential as `blockchain_anchor`.
2. The page then asks MetaMask to send `anchorDocument(bytes32,string)` to the legacy `AstraVerifyAnchor` on chain `31337`, writing that hash to the local test chain.

This route is **off by default**: the legacy routers mount only when `LEGACY_API_ENABLED=true` in `backend/.env`, and credentials are kept in an in-memory dict, so restarting the backend forgets them. The endpoint is unauthenticated and its integrity tag is a demo HMAC, not a signature. Setup, deterministic contract addresses, and MetaMask notes are in [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) §4.

---

## Verifying the install

### Backend test suite

Requires PostgreSQL; the suite creates and uses the `astra_test` database.

```bash
cd backend
./venv/bin/pytest
```

**Last run: 2026-10-25 — 86 passed, 0 failures, 0 errors.** The suite uses PostgreSQL database `astra_test` and local storage. It covers authorization, uploads, extraction, rules, issuers, anomalies, review/audit, security, declarations, technical inspection, report export, alert dispositions, self-check, ZKP, and an end-to-end application-to-decision flow.

### Contract tests

```bash
cd blockchain
npm install
npx hardhat test
```

**Last run: 2026-10-24 — 5 passed.** Contract tests cover access control, hash-only anchoring, nullifier reuse, and proof verification failure.

### Frontend build

```bash
cd frontend
npm run build
```

**Last run: 2026-10-25 — succeeded.** `npm run lint` still fails because no ESLint config exists.

### Synthetic evaluation

```bash
cd backend
./venv/bin/python evaluation/run_evaluation.py
```

The script creates and drops a dedicated `astra_evaluation` database. **Never point it at `astra` or `astra_test`.** Results are written to `backend/evaluation/results.json`.

Last measured synthetic results (2026-10-25, runtime 14.0 s):

| Metric | Result |
|---|---|
| OCR field exact match | 100/100 fields across 20 synthetic documents |
| OCR processing time | median 104.21 ms, p95 128.18 ms (varies 90–130 ms run to run on the dev laptop) |
| Rule outcomes | 48/48 labels across 4 cases |
| Declaration consistency labels | 12/12 (supplied → `PASS`, absent → `NOT_AVAILABLE`, mismatched → `FAIL`) |
| Anomaly signals | precision 1.0, recall 1.0 over 3 synthetic applications |
| Issuer scenarios | 3/3 expected states |
| Advisory controls | 39/39 (self-check parity, no-write preview, report safety, dispositions, supersede) |
| Disclaimer | Metrics describe only the synthetic corpus; they are **not** AICTE accuracy claims |

### Scripted demo walkthrough

With the backend running:

```bash
cd backend
./venv/bin/python scripts/demo_smoke.py
```

It drives the whole flow over real HTTP (health → login → self-check → uploads → declaration → submit → review → inspection → report export → alerts) and exits non-zero on the first divergence. See [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) for the spoken demo script and safe phrasing.

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
- [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) — demo startup, 12-minute script, safe phrasing, troubleshooting
- [`docs/REPOSITORY_AUDIT.md`](docs/REPOSITORY_AUDIT.md) — original audit, simulated capabilities, legacy risks

---

## License

Built for the Smart India Hackathon (SIH). All rights reserved.
