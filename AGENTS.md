# AGENTS.md

## Read this first
- The repository is an **AICTE application-validation and compliance platform prototype**, adapted from the original AstraVerify consumer credential wallet. The MVP category is **Extension of Approval (EoA)**.
- Phases 1–10 of `IMPLEMENTATION_ROADMAP.md` are implemented and locally verified. Phase 11 documentation/demo hardening is in progress; post-MVP milestones M0 (credibility containment), M1 (evidence viewer), M2 (structured declaration + three-way consistency), M3 (advisory QR/signature inspection), M4 (report export + alert dispositions), M5 (pre-submission self-check), and M6 (demo hardening + evaluation) are complete. Do not describe the system as production-ready or officially integrated with AICTE.
- Current requirement status: `docs/REQUIREMENTS_TRACEABILITY.md`. Historical audit of the original wallet: `docs/REPOSITORY_AUDIT.md`. Target specification: `SPEC.md`. Design docs: `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, `docs/TEST_PLAN.md`.
- The user authorized continued implementation across phases on 2026-10-24. Still ask before broad refactoring, destructive changes, security-sensitive changes, database migrations that rewrite data, or changes to cryptographic circuits/contracts.

## Layout
- `backend/` — FastAPI app (`app/main.py`), PostgreSQL models, Alembic migrations, services, tests, evaluation harness, and `scripts/demo_smoke.py` (live-HTTP demo walkthrough).
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
- Alembic head: `c3d5e7f9a1b2` (structured `application_declarations`; previous head `b7f1c9a2d4e0` added evidence geometry on `extracted_fields`). The ZK migrations round-tripped on 2026-10-24; `b7f1c9a2d4e0` and `c3d5e7f9a1b2` were downgrade/re-upgrade verified on 2026-10-25.

Tests (require PostgreSQL):
```bash
cd backend
./venv/bin/pytest
```
**Last run 2026-10-25 (Windows, Python 3.10): 86 passed, 0 failures, 0 errors, 0 skipped** (`--junit-xml=test-m6.xml`, 171.64 s). Per-file counts: phase3 applications 9, auth 7, documents 7, records/admin 3; phase4 4; phase5 5; phase6 5; phase7 4; phase8 4; phase9 7; phase10 ZKP 5; phase10 e2e 1; phase11 declarations 4; phase12 technical verification 6; phase13 report/alerts 6; phase14 self-check 7; legacy attestation 2.

Test environment notes:
- Version pins were reconciled in M6: `requirements.txt` now allows `SQLAlchemy>=2.0.55,<2.1` (2.1.x needs Python >= 3.11 and is untested here) and `requirements-dev.txt` allows `pytest>=8.4,<10`. The committed venv is Python 3.10.11 with SQLAlchemy 2.0.55 and pytest 8.4.2.
- The phase 10 ZKP tests shell out to `circuits/node_modules/.bin/snarkjs`, so run `cd circuits && npm install` once. On Windows the test resolves `snarkjs.cmd`.
- `BLOCKCHAIN_ENABLED`/`BLOCKCHAIN_PROOF_ANCHORING_ENABLED` are forced to `false` in `tests/conftest.py` so a developer `.env` cannot change test outcomes.
- Tesseract is optional for the suite: without it, blank/scanned pages report `OCR_ENGINE_UNAVAILABLE` instead of `NO_TEXT`, and `test_blank_document_is_unreadable_and_blocks_submission` accepts either.

Synthetic evaluation:
```bash
cd backend
./venv/bin/python evaluation/run_evaluation.py
```
Creates and drops `astra_evaluation`. Never point it at `astra`/`astra_test`. Results are synthetic-only. Last run 2026-10-25: OCR 100/100 fields, rules 48/48, declaration consistency 12/12, anomalies precision/recall 1.0, issuer 3/3, **advisory controls 39/39**, 14.0 s. The `advisory_controls` section asserts self-check/submit parity, preview no-write behaviour, report claim safety (no "is forged"/"is authentic"-style phrasing in any format), export auditability, disposition gating, and stale-alert supersede.

Live demo walkthrough (backend must be running):
```bash
cd backend
./venv/bin/python scripts/demo_smoke.py     # --base-url http://localhost:8000
```
Talks only to the HTTP API, creates applications in cycles `2099-01`…`2099-12`, and exits non-zero on the first divergence. The spoken demo script, safe phrasing, and troubleshooting table live in `docs/DEMO_RUNBOOK.md`.

### Frontend
```bash
npm --prefix frontend run dev     # port 5173
npm --prefix frontend run build
```
- No Vite proxy and no checked-in `.env`. `VITE_API_BASE_URL` defaults to `http://localhost:8000`.
- `snarkjs` is loaded globally from a CDN in `frontend/index.html` and used as `window.snarkjs`; `/compliance` browser proving needs network access.
- `pdfjs-dist@4.10.38` renders the evidence viewer. It is dynamically imported (worker via `?url`) so the renderer is a separate lazy chunk, not part of the initial bundle.
- `npm run lint` fails: the script exists but there is no ESLint config.
- Build verified 2026-10-25 after the evidence workspace, the declaration form, the technical inspection panel, the report export buttons, the alert panel, and the self-check panel. `/compliance` has not been browser-automation tested; the evidence path was smoke-tested over real HTTP (upload → submit → review-overview → signed download).
- `/compliance` renders `<DeclarationForm>` (loads/saves the declaration; editable only for an applicant on a `DRAFT`, read-only otherwise), `<EvidenceWorkspace>` (findings + evidence + rendered document), `<VerificationTools>` (staff-only advisory QR/PDF-signature inspection; refuses to describe a result as verified), `<AlertPanel>` (staff alert queue: acknowledge/resolve with disposition + note gating), and `<SelfCheckPanel>` (applicant pre-submission preview, refreshed after upload/declaration save). The Human review header has JSON/Markdown/HTML advisory report export buttons.

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
- One structured declaration per application (`application_declarations`), applicant-supplied and never verified: `GET`/`PUT /applications/{id}/declaration`, draft-only, audited as `application.declaration_saved` with a version increment per save.
- Three declaration-consistency rules (`AFFILIATION_DECLARATION_MATCH`, `PROGRAMME_DECLARATION_MATCH`, `FACULTY_COUNT_DECLARATION_MATCH`) return `NOT_AVAILABLE` when there is no declaration, compare declared values with extracted fields and synthetic records, and never auto-reject. The EoA rule set has 12 rules; the seeder archives an older rule set and publishes a new active version instead of mutating one historical runs reference.
- Extracted fields store `page`, `bbox`, `page_width`, `page_height`; validation copies them into `finding_evidence.metadata_json`, and `/compliance` draws the box on the rendered page. PDF boxes are points, OCR'd raster boxes are pixels.
- Audit events form a SHA-256 hash chain with a global sequence.
- Technical inspection is advisory and lives in existing `issuer_verifications` rows (`adapter_code` `qr-payload` / `pdf-signature`), reached via `POST /document-versions/{id}/technical-verifications` (REVIEWER/APPROVER/ADMIN; PDF/image only). QR payloads are decoded locally (OpenCV, ≤10 pages at 150 dpi), recorded as preview/digest/host, and **never fetched**. PDF signature dictionaries/`ByteRange` are inspected structurally; CMS, certificate, revocation, and trust chain are **not** verified. States map to `NOT_FOUND`/`SOURCE_UNAVAILABLE`/`MISMATCH`/`ERROR`; `review-overview.technical_verifications` shows the newest row per `(document_version_id, adapter_code)` and full history stays in the list endpoint. No schema change.
- `GET /applications/{id}/report?format=json|markdown|html` (staff-only, synchronous, `application-report-1.0`) returns a self-contained advisory report as an attachment and audits `application.report_exported`. No PDF renderer and no signature: an export is never an official or signed artefact.
- Alert dispositions live in `alerts.payload` (no migration): `ADDRESSED`/`FALSE_POSITIVE`/`DUPLICATE`/`SUPERSEDED`/`ACCEPTED_RISK`/`ESCALATED`; `FALSE_POSITIVE` and `ACCEPTED_RISK` require a note. `sync_alerts` resolves stale finding/anomaly alerts as `SUPERSEDED` with a system actor. Alert detail/acknowledge/resolve re-check application scope (`404` out of scope).
- `GET /applications/{id}/self-check` (`self-check-1.0`, `DRAFT`/`RECTIFICATION_REQUESTED` only) is a read-only pre-submission preview: no validation run, no alerts, no audit event. Its blocking checks reuse the same `missing_required_items` helper as `submit`, so it cannot disagree with the real gate; warnings are advisory and never block.
- ZK threshold is server-issued via a stored challenge; the applicant cannot choose it. Challenge TTL is 600 s. Verification uses a pinned vkey; submission requires five public signals and `valid == "1"`. Challenges are consumed only after successful verification; rejected attempts are audit-only.
- Anchoring is optional/advisory and hash-only. Disabled/failed states are explicit.
- CORS defaults to `http://localhost:5173`; production requires explicit origins and `STORAGE_BACKEND=s3`.
- The legacy consumer-wallet routers (`upload`, `digilocker`, `issuer`, `verify`, `verifier`) mount only when `LEGACY_API_ENABLED=true` (default `false`). The `/issuer` portal therefore needs that flag **plus** a running Hardhat node: it calls `POST /api/v1/issuer/issue`, then anchors the returned hash via MetaMask to legacy `AstraVerifyAnchor.anchorDocument(bytes32,string)` (permissionless). See `docs/DEMO_RUNBOOK.md` §4; tests pin the flag to `false` in `tests/conftest.py`.

## Implemented vs simulated
Do not describe these as real capabilities in code, docs, or UI:
- **Real:** PostgreSQL/auth/RBAC, upload/versioning/storage, OCR (pdfplumber → PyMuPDF → Tesseract) and regex extraction, evidence bboxes with page geometry, rules engine with three-way declared-vs-extracted-vs-record consistency (advisory), demo Ed25519 issuer signatures, advisory anomaly heuristics, review/alerts/hash-chained audit, sound Groth16 circuit + server-side verification, hash-only V2 anchoring, evidence workspace with document rendering, applicant declaration form, local QR decoding (OpenCV), PDF signature-structure (`/Type /Sig`, `/ByteRange`) inspection, advisory JSON/Markdown/HTML report export, alert dispositions with auto-supersede, read-only pre-submission self-check, synthetic evaluation harness.
- **Partial:** document classification is heuristic; infrastructure checks are presence/completeness only; the structured declaration is applicant-supplied and never verified, so a consistency `PASS` only means two sources agree; `previous_approval_reference` is stored but not compared; ZKP is not bound to a verified credential or identity; QR payloads are recorded but never resolved against an authorised source; PDF signatures are never cryptographically verified (no CMS, certificate, revocation, or trust-chain check), so `PDF_SIGNATURE_COVERAGE_INCOMPLETE` is a structural observation only; report exports have no PDF/signature/presigned artefact and are advisory only; the self-check previews the submission gate but does not run the rule engine or predict approval; no retention job/encryption-at-rest; no on-chain revocation/retries.
- **Simulated/stub (legacy, not new flow):** `services/deepfake.py`, `services/risk.py`, `Wallet/ImportOptions.jsx`, `digilocker.py`, legacy `attestation.py` (real Ed25519, demo-only key + non-W3C proof value), legacy `validate-zk`, legacy `range_proof.circom`, legacy contract mismatches (`CriteriaBuilder`, `ZKProofGenerator`, `IssuerPortal` ABI, dead submit/camera options).

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
