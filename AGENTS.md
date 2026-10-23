# AGENTS.md

## Read this first
- The repository is an **AICTE application-validation and compliance platform prototype**, adapted from the original AstraVerify consumer credential wallet. The MVP category is **Extension of Approval (EoA)**.
- Phases 1–10 of `IMPLEMENTATION_ROADMAP.md` are implemented and locally verified. Phase 11 documentation/demo hardening is in progress. Do not describe the system as production-ready or officially integrated with AICTE.
- Current requirement status: `docs/REQUIREMENTS_TRACEABILITY.md`. Historical audit of the original wallet: `docs/REPOSITORY_AUDIT.md`. Target specification: `SPEC.md`. Design docs: `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, `docs/TEST_PLAN.md`.
- The user authorized continued implementation across phases on 2026-10-24. Still ask before broad refactoring, destructive changes, security-sensitive changes, database migrations that rewrite data, or changes to cryptographic circuits/contracts.

## Layout
- `backend/` — FastAPI app (`app/main.py`), PostgreSQL models, Alembic migrations, services, tests, evaluation harness.
- `backend/circuits/faculty_threshold/` — pinned sound-circuit artifacts used for server-side verification.
- `frontend/` — React/Vite/Tailwind app. `/compliance` is the new workflow console; legacy `/wallet`, `/verifier`, `/issuer` remain.
- `frontend/landing/` — separate Vite marketing app, not imported by the main app. Ignore unless asked.
- `frontend/dist/` — committed build output. Rebuild with `npm run build`; do not hand-edit.
- `blockchain/` — Hardhat project. New path: `AstraVerifyAnchorV2.sol` + generated `FacultyThresholdVerifier.sol`; legacy `AstraVerifyAnchor.sol`/`Groth16Verifier.sol` remain for history.
- `circuits/` — Circom source and build tooling for `faculty_threshold.circom`; legacy unsound `range_proof.circom` remains but is disabled.

## Commands

### PostgreSQL
Default local container and port:
```bash
docker run -d --name astra-postgres \
  -e POSTGRES_USER=astra -e POSTGRES_PASSWORD=astra -e POSTGRES_DB=astra \
  -p 55432:5432 postgres:16
```
URL: `postgresql+psycopg://astra:astra@localhost:55432/astra`. Test DB: `astra_test`. Migration-only DB: `astra_migrate`. Evaluation DB: `astra_evaluation`.

### Backend (run from `backend/`)
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # set JWT_SECRET and DOWNLOAD_SIGNING_KEY, each >= 32 chars
./venv/bin/alembic upgrade head
python -m app.seed
python -m uvicorn app.main:app --reload --port 8000
```
- `backend/requirements.txt` is now UTF-8. `requirements-dev.txt` contains pytest.
- Tesseract must be installed and on `PATH` (or set `TESSERACT_CMD`), otherwise OCR returns an error state.
- `validate_security_config()` runs when `app.main` imports. Importing without test env/secrets will fail by design.
- Alembic head: `4eeaf2dbd8cc` (ZK challenges). Upgrade/downgrade/re-upgrade of the ZK migrations was verified on 2026-10-24.

Tests (require PostgreSQL):
```bash
cd backend
./venv/bin/pytest
```
**Last run 2026-10-24: 61 passed, 2 warnings.** Per-file counts: phase3 applications 9, auth 7, documents 7, records/admin 3; phase4 4; phase5 5; phase6 5; phase7 4; phase8 4; phase9 7; phase10 ZKP 5; phase10 e2e 1.

Synthetic evaluation:
```bash
cd backend
./venv/bin/python evaluation/run_evaluation.py
```
Creates and drops `astra_evaluation`. Never point it at `astra`/`astra_test`. Results are synthetic-only.

### Frontend
```bash
npm --prefix frontend run dev     # port 5173
npm --prefix frontend run build
```
- No Vite proxy and no checked-in `.env`. `VITE_API_BASE_URL` defaults to `http://localhost:8000`.
- `snarkjs` is loaded globally from a CDN in `frontend/index.html` and used as `window.snarkjs`; `/compliance` browser proving needs network access.
- `npm run lint` fails: the script exists but there is no ESLint config.
- Build verified 2026-10-24. `/compliance` has not been browser-automation tested.

### Blockchain
```bash
cd blockchain
npx hardhat node
npx hardhat run scripts/deploy_v2.js --network localhost
npx hardhat test
```
- Last contract test run 2026-10-24: **5 passed**.
- Deploy prints `FacultyThresholdVerifier` and `AstraVerifyAnchorV2` addresses; copy them manually.
- Networks: `hardhat`/`localhost` (chain 31337) and `polygonAmoy` (needs funded `POLYGON_RPC_URL`/`PRIVATE_KEY`). Amoy was not deployed.
- Live backend anchoring verified once against local Hardhat: `chain_status=ANCHORED`, real tx hash. Backend anchoring is disabled by default and non-blocking.
- On-chain revocation and backend retry queue are **not implemented**.

### Circuits
```bash
cd circuits
npm install
./build_faculty_threshold.sh
```
- Uses `circom2@0.2.23` (circom 2.2.3) + snarkjs.
- Copy `faculty_threshold.wasm`, `faculty_threshold_final.zkey`, `verification_key.json` to `backend/circuits/faculty_threshold/` and `frontend/public/circuits/faculty_threshold/`; copy generated verifier to `blockchain/contracts/`.
- Trusted setup is development-only. Do not present artifacts as production trust material.
- Legacy `circuits/*.bat` hardcode Windows paths; do not use on Linux.

## Architecture facts
- PostgreSQL 16 with SQLAlchemy 2.x sync sessions, native enums, JSONB, UUIDs, Alembic.
- Argon2id password hashing; short-lived JWT access tokens plus rotating hashed refresh tokens.
- Storage abstraction: `local` for tests/dev; `s3` for MinIO/S3. Local downloads use HMAC-signed short-lived URLs.
- No self-registration. `app.seed` provisions demo users; admin APIs manage users/institutions/rules.
- Reviewer sees submitted/unassigned applications; applicant is scoped to own institution; approver/admin/auditor have broader staff scope.
- Checklist is snapshotted at application creation; submission requires every required item to have a document or justification.
- Validation runs inline by default (`PROCESS_DOCUMENTS_INLINE=true`) even though upload returns `202`.
- Findings are advisory. Decisions are explicit human actions and are audited.
- Audit events form a SHA-256 hash chain with a global sequence.
- ZK threshold is server-issued via a stored challenge; the applicant cannot choose it. Challenge TTL is 600 s. Verification uses a pinned vkey; submission requires five public signals and `valid == "1"`. Challenges are consumed only after successful verification; rejected attempts are audit-only.
- Anchoring is optional/advisory and hash-only. Disabled/failed states are explicit.
- CORS defaults to `http://localhost:5173`; production requires explicit origins and `STORAGE_BACKEND=s3`.

## Implemented vs simulated
Do not describe these as real capabilities in code, docs, or UI:
- **Real:** PostgreSQL/auth/RBAC, upload/versioning/storage, OCR (pdfplumber → PyMuPDF → Tesseract) and regex extraction, evidence bboxes, rules engine, demo Ed25519 issuer signatures, advisory anomaly heuristics, review/alerts/hash-chained audit, sound Groth16 circuit + server-side verification, hash-only V2 anchoring, synthetic evaluation harness.
- **Partial:** document classification is heuristic; infrastructure checks are presence/completeness only; ZKP is not bound to a verified credential or identity; no report export; no retention job/encryption-at-rest; no on-chain revocation/retries.
- **Simulated/stub (legacy, not new flow):** `services/deepfake.py`, `services/risk.py`, `Wallet/ImportOptions.jsx`, `digilocker.py`, legacy `attestation.py` (HMAC labelled Ed25519), legacy `validate-zk`, legacy `range_proof.circom`, legacy contract mismatches (`CriteriaBuilder`, `ZKProofGenerator`, `IssuerPortal` ABI, dead submit/camera options).

## Product constraints
- Findings are advisory; never present an anomaly score, hash match, or ZK proof as proof of forgery, authenticity, or compliance.
- Label simulated issuer/integration responses; never imply AICTE or issuer API access.
- Regulatory rules must be versioned and configurable; seeded thresholds/citations are synthetic until official sources are supplied.
- Preserve human-review and auditability. Final decisions remain with authorized officials.
- Use synthetic or authorized anonymized data only.

## Workflow
1. Read the roadmap and relevant docs.
2. Inspect actual implementation and tests; do not rely on README claims.
3. Explain proposed changes, affected files, dependencies, and risks before implementation.
4. Ask before broad refactoring, destructive changes, security-sensitive changes, or circuit/contract changes.
5. Work on one coherent milestone at a time; preserve existing functionality and API contracts unless approved.
6. Add/update tests for behavior changes. Run relevant backend, contract, and frontend checks.
7. Inspect `git diff` before declaring completion.
8. Never claim a test/build/integration/security check succeeded unless it was actually executed and its result verified.

## Milestone reporting
Report: implemented/documented items; files changed; preserved/affected functionality; commands actually run and results; remaining risks/assumptions/limitations; recommended next milestone. Do not automatically proceed without explicit approval.

## Security-sensitive legacy components
Treat existing cryptographic circuits, proof verification, signature schemes, issuer integrations, and blockchain anchoring as untrusted until independently checked. Do not present a legacy component as production-ready because it executes successfully. The new ZKP/anchoring flow is isolated from the legacy wallet components.
