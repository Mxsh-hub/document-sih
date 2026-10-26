# Demo runbook — AICTE Extension of Approval prototype

This is the operator script for demonstrating the compliance console end to end.
It is written for a **controlled prototype demo**, not a production deployment.

Everything shown is synthetic: institutions, records, documents, issuer keys,
and rule thresholds. The system is advisory. No AICTE, DigiLocker, or issuer API
is contacted, and no automated approval or rejection exists.

---

## 1. What the demo proves

| Claim | Where it is visible | Honest limit |
|---|---|---|
| A submitted application is validated against versioned rules | `/compliance` → Human review → findings | Rules and thresholds are synthetic |
| Findings are evidence-linked | Evidence workspace: page, bounding box, rule | OCR/extraction is heuristic |
| Applicant declarations are compared three ways | Declaration form + consistency findings | Declared values are never verified |
| Evidence can be previewed and QR/signature structures inspected | Document viewer + Technical inspection | Advisory only; nothing is fetched or cryptographically verified |
| Reviewers can acknowledge/resolve alerts with a disposition | Alert panel | A disposition is human judgement, never a decision |
| A report can be exported for a human reviewer | JSON / Markdown / HTML export | No PDF, no signature, not an official document |
| Applicants can preview the submission gate | Self-check panel | Does not run the rule engine or predict approval |
| Every action is attributable | Audit history + hash-chain verification | Local database only |

---

## 2. Pre-flight (about 5 minutes)

```bash
# 1. PostgreSQL
docker start astra-postgres        # or create it, see README

# 2. Backend
cd backend
./venv/bin/alembic upgrade head
./venv/bin/python -m app.seed      # idempotent
./venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 3. Frontend (second terminal)
npm --prefix frontend run dev      # http://localhost:5173
```

Check before the audience arrives:

```bash
curl http://localhost:8000/health
# {"status":"healthy", ...}
```

Open `http://localhost:5173/compliance`. It should show the sign-in card with the
note *“Seeded users · synthetic records · advisory findings.”*

If the console shows a blank page, the built assets are stale: run
`npm --prefix frontend run build` (or use `npm run dev`).

### Accounts

| Account | Role | Use in the demo |
|---|---|---|
| `applicant@example.test` | Applicant | Upload evidence, declare, self-check, submit |
| `reviewer@example.test` | Reviewer | Review overview, technical inspection, alerts, report export |
| `approver@example.test` | Approver | Final decision (only role allowed besides admin) |
| `admin@example.test` | Admin | User/rule administration, audit verification |
| `auditor@example.test` | Auditor | Read-only oversight |

Password: `ChangeMe123!` unless `SEED_PASSWORD` was set.

---

## 3. The 12-minute demo script

Timings assume the seeded database. Speak the bold lines; they are the honest
framing and they also protect against over-claiming.

### 0:00 — Frame it (30 s)

Sign in as **Applicant**.

> **“This is a decision-support prototype for AICTE Extension of Approval. It
> validates an application, surfaces evidence-linked findings, and leaves every
> decision to an authorised official. All data here is synthetic.”**

### 0:30 — Create an application (1 min)

In the left rail, keep the cycle (`2026-27`) and click **Create**. A reference
number appears and the evidence checklist lists five items (four required).

> **“The checklist is snapshotted from a versioned template, so a later template
> change cannot rewrite the checklist this application is judged against.”**

### 1:30 — Show the gate before evidence (1 min)

Scroll to the **Pre-submission self-check** panel.

> **“Before uploading anything, the applicant can see the real gate: these
> checklist items would block submission. This preview reads nothing but the
> same check that `submit` enforces.”**

Point at the blocking entries, then click **Submit for validation** in the header
and let it fail with a `VALIDATION_FAILED`-style message.

> **“Submission is refused. The preview and the gate cannot disagree because
> they call the same function.”**

### 2:30 — Upload evidence (2 min)

Upload the four required PDFs. If the demo pack is not prepared, use
`backend/scripts/demo_smoke.py --help` output and the same synthetic text; the
expected outcome is all-`PASS` findings.

After each upload, the checklist row flips to `SATISFIED` and the self-check
panel refreshes.

> **“Each upload is an immutable version with a SHA-256 digest. Extraction runs
> synchronously here, and the bounding boxes are stored so a reviewer can see
> exactly which part of which page produced a value.”**

### 4:30 — Fill the structured declaration (1 min)

In the **Structured declaration** form, set the affiliation number, validity
date, two programmes (CSE 120, ECE 60), total intake 180, faculty count 2. Save.

> **“These are the institution’s claims. They are never verified. Validation
> compares the claim, the extracted document, and the synthetic institutional
> record — three-way consistency. A `PASS` here means two sources agree, not
> that the claim is true.”**

### 5:30 — Self-check turns green (30 s)

The pre-submission panel now shows no blocking checks.

> **“Warnings remain — those are advisory observations about likely findings.
> They never block.”**

### 6:00 — Submit and show findings (1 min)

Click **Submit for validation**. Then switch to **Reviewer** in a second browser
window (or sign out and back in) and open the same application.

> **“Submission is a human act. It starts validation; it does not approve
> anything.”**

### 7:00 — Evidence workspace (1.5 min)

Click **Load review overview**, then open a finding in the evidence workspace to
render the document at the cited page and box.

> **“Every `FAIL` or `INCONCLUSIVE` can be traced to a rule, a page, and a
> region. Nothing is a black-box score.”**

### 8:30 — Technical inspection (1 min)

In **Technical inspection**, run the inspection on the affiliation certificate.

> **“This decodes QR payloads locally and inspects PDF signature structures. It
> records what it found, and deliberately does not fetch anything or verify a
> certificate, revocation status, or trust chain. So the result is ‘no signature
> found’ or ‘present but unverified’ — never ‘authentic’.”**

### 9:30 — Alerts and disposition (1 min)

A fully clean application raises no alerts, so open the **second** application
for this step: create one and upload an affiliation certificate that has already
expired (or naming a different institution), then submit it. Findings fail and
alerts appear.

In the **Review alerts** panel, acknowledge an alert, then resolve it with an
`ADDRESSED` disposition. Show that `FALSE_POSITIVE` is refused without a note.

> **“Resolving an alert is documented human judgement, with an actor, a time, and
> a reason. It does not change the finding, the status, or the decision.”**

### 10:30 — Export the report (1 min)

In the **Human review** header, click **JSON**, then **Markdown**.

> **“This is an advisory review aid. It repeats its own limitations, it is not
> signed, and it is not an AICTE document.”**

### 11:30 — Close honestly (30 s)

Sign in as **Admin**, click **Verify audit chain**.

> **“Every action is in a hash-chained audit log. What this prototype does not
> have: real AICTE data, real issuer verification, a production trusted setup,
> retention or encryption-at-rest guarantees, and browser E2E. Those are listed
> in the repository’s traceability document.”**

---

## 4. Command-line walkthrough

For a scripted, repeatable verification of the same flow over real HTTP:

```bash
cd backend
./venv/bin/python scripts/demo_smoke.py
# optional:
./venv/bin/python scripts/demo_smoke.py --base-url http://localhost:8000
```

It prints one line per step and exits non-zero on the first divergence. It talks
only to the running API; it never imports the app or writes to the database
directly.

The walkthrough covers 44 steps in two applications:

1. **A clean application** — self-check blocked, submit refused, four required
   uploads, structured declaration, self-check clear, submit, findings, technical
   inspection, three report formats, and no alert.
2. **A deliberately inconsistent application** — an expired affiliation in the
   name of a different institution. It submits (submission is not gated on
   findings), fails `AFFILIATION_VALIDITY`, raises alerts, and is then used to
   demonstrate acknowledgement, the `FALSE_POSITIVE`-without-a-note refusal, and
   an `ADDRESSED` disposition that leaves the findings untouched.

The clean application uses a unique affiliation number derived from its
reference number, so a re-run does not trip the cross-application
identifier-reuse anomaly. Both applications are left in the database (cycles
`2099-01` … `2099-12`), so re-run against a clean dev database or drop those
applications; after six runs the cycles are exhausted.

### Optional — legacy issuer portal on Hardhat localhost

The legacy consumer-wallet routes (`/issuer`, `/upload`, `/verify`, …) are off by
default. They are a synthetic demo surface, **not** part of the EoA workflow, and
they store credentials in process memory (restarting the backend forgets them).

1. Enable the routes in `backend/.env` and restart the backend:

   ```bash
   LEGACY_API_ENABLED=true
   ```

2. Start a local chain and deploy **in this order** (a fresh `npx hardhat node`
   always produces these addresses):

   ```bash
   cd blockchain
   npx hardhat node                                   # terminal A
   npx hardhat run scripts/deploy.js    --network localhost   # Groth16Verifier, AstraVerifyAnchor
   npx hardhat run scripts/deploy_v2.js --network localhost   # FacultyThresholdVerifier, AstraVerifyAnchorV2
   ```

   | Contract | Address |
   |---|---|
   | `Groth16Verifier` | `0x5FbDB2315678afecb367f032d93F642f64180aa3` |
   | `AstraVerifyAnchor` (legacy, used by the issuer portal) | `0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512` |
   | `FacultyThresholdVerifier` | `0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0` |
   | `AstraVerifyAnchorV2` | `0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9` |

3. Point the frontend at them in `frontend/.env`:

   ```bash
   VITE_CONTRACT_ADDRESS=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
   VITE_RPC_URL=http://127.0.0.1:8545
   ```

   Restart Vite — `VITE_*` values are baked in at dev-server start.

4. In MetaMask, import a funded Hardhat account (e.g. account #0
   `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`, 10000 ETH) and, if prompted,
   approve network `127.0.0.1:8545` (chain id `31337`).

The portal then calls `POST /api/v1/issuer/issue` and, after a 200, asks
MetaMask to send `anchorDocument(bytes32,string)` to `AstraVerifyAnchor`. That
function is **permissionless** — any account can anchor — so no role grant is
needed. Anchoring the same hash twice reverts with
`Document already anchored`, which is the contract behaving correctly.

> Say: “the credential content is a synthetic demo; the backend hashes it and the
> browser writes that hash to a local test chain so the flow is end-to-end
> visible.” Do not say the credential is verified, trusted, or on Polygon
> mainnet.

Set `LEGACY_API_ENABLED=false` (or remove the line) to hide the legacy routes
again.

---

## 5. Evaluation harness

```bash
cd backend
./venv/bin/python evaluation/run_evaluation.py
```

Creates and drops the dedicated `astra_evaluation` database, then measures OCR
extraction, rule outcomes, anomaly precision/recall, issuer states, declaration
consistency, and the advisory controls (self-check parity, report safety, alert
dispositions, stale-alert supersede). Results go to
`backend/evaluation/results.json`.

**Never point this at `astra` or `astra_test`.** The numbers describe a synthetic
corpus only.

---

## 6. Safe phrasing

| Instead of | Say |
|---|---|
| “The system detects forged documents” | “The system records advisory anomalies and structural observations for human review” |
| “The document is authentic” | “The QR payload was recorded but not resolved; the signature structure was inspected but not cryptographically verified” |
| “The AI approved the application” | “The applicant submitted; validation produced advisory findings” |
| “This is an AICTE report” | “This is an advisory review aid exported from the prototype” |
| “The proof proves the faculty count” | “The proof shows the committed private value meets a configured threshold; the value itself is not verified” |
| “We integrate with AICTE/DigiLocker” | “Adapters exist and are explicitly labelled synthetic/unavailable” |

---

## 7. Reset and troubleshooting

Reset the demo database (destroys local demo data only):

```bash
docker exec -it astra-postgres psql -U astra -d astra -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
cd backend && ./venv/bin/alembic upgrade head && ./venv/bin/python -m app.seed
```

| Symptom | Cause | Action |
|---|---|---|
| `ImportError: StrEnum` | Python < 3.11 without the shim | Use the committed venv (3.10 shim is present) |
| Backend exits on start with a config error | `JWT_SECRET` / `DOWNLOAD_SIGNING_KEY` shorter than 32 chars | Copy `backend/.env.example` to `.env` and set both |
| Console shows `Failed to fetch` | Backend not running on port 8000 | Start uvicorn; check `/health` |
| Upload returns `OCR_ENGINE_UNAVAILABLE` | Tesseract not on `PATH` | Install Tesseract or set `TESSERACT_CMD`; text-PDF extraction still works |
| Create application returns `STATE_CONFLICT` | An active application already exists for that category and cycle | Change the cycle or reset the database |
| Self-check returns `409` | Application is no longer `DRAFT`/`RECTIFICATION_REQUESTED` | Expected; the gate is closed after submission |
| Proof generation fails | `snarkjs` CDN blocked | Use a network-enabled browser; the rest of the demo is unaffected |
| `npm run lint` fails | No ESLint config in the repo | Do not claim lint passed; use `npm run build` |
| Issuer portal: “Failed to issue credential from backend” | Legacy routes are unmounted (`LEGACY_API_ENABLED` false → `POST /api/v1/issuer/issue` returns 404), or the backend was not restarted after editing `.env` | Set `LEGACY_API_ENABLED=true` in `backend/.env` and restart uvicorn; confirm with `curl -o /dev/null -w "%{http_code}"` on that route |
| Issuer portal: MetaMask transaction reverts / nothing anchors | Hardhat node not running, or contracts not deployed on the current chain | Start `npx hardhat node`, run `deploy.js` then `deploy_v2.js`, restart Vite so `VITE_CONTRACT_ADDRESS` is picked up |
| MetaMask shows the wrong network or account | Chain reset or a non-Hardhat account selected | Import Hardhat account #0 and switch to chain id `31337` |
| `Document already anchored` revert | The same hash was already written to the local chain | Expected; re-issue a new credential (a new UUID produces a new hash) |
