# SPEC — AstraVerify (AICTE Adaptation)

**Status:** implemented prototype specification (Phases 1–10 verified locally; Phase 11 documentation in progress).
**Version:** 3.0
**Last updated:** 2026-10-24
**Official problem title (supplied by user):** *AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification*
**Requirements source:** Full official SIH problem statement supplied 2026-10-23, plus `IMPLEMENTATION_ROADMAP.md`. Official requirements are mapped to implementation requirements in [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md).

Related documents:
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)
- [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md)
- [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md)
- [`docs/REPOSITORY_AUDIT.md`](docs/REPOSITORY_AUDIT.md)

---

## 1. Decision log (approved inputs)

| Decision | Value | Status |
|---|---|---|
| MVP application category | **Extension of Approval (EoA)** under the AICTE Approval Process Handbook | Approved |
| Persistence | PostgreSQL 16 | Approved |
| Object storage | S3-compatible (MinIO locally) | Approved |
| Authentication | Local accounts + JWT (access/refresh), Argon2id | Approved |
| Backend | Retain FastAPI (Python 3.13) | Approved |
| Frontend | Retain React 18 + Vite + Tailwind | Approved |
| ZKP / blockchain | **Retained in MVP** as a privacy-preserving faculty-eligibility proof + tamper-evidence anchoring | Approved |
| MVP document types | Affiliation/recognition certificate, land/lease document, faculty degree certificate, institutional undertaking | Approved |
| MVP structured records | Synthetic AICTE-style records: previous EoA/approval status, programmes/intake, faculty, compliance deficiencies, TER payment, accreditation/NOC | Approved |
| Infrastructure evidence | Photo/video/floor-plan attachments checked for presence/completeness only; computer vision deferred | Approved |
| Simulated issuer integrations | Required for MVP, explicitly labeled | Approved |
| Requirements baseline | Official SIH statement supplied; regulatory rule sources still pending | Provisional |

---

## 2. Purpose and scope

The platform supports competent authorities in validating institutional applications by:

1. Managing institutions, applications, checklists, and document versions as durable records.
2. Extracting structured information from submitted documents with page-level evidence and confidence.
3. Evaluating applications against **versioned, configurable** rules and available institutional records.
4. Facilitating verification through authorized issuing authorities, with clearly labeled simulations where access does not exist.
5. Detecting duplicate and inconsistent evidence as **advisory** signals.
6. Giving reviewers an evidence-linked case view, workflow actions, alerts, and an immutable audit trail.
7. Offering a privacy-preserving eligibility proof for faculty credentials, and tamper-evident anchoring of document and credential hashes.

**Decision support only.** The platform never approves, rejects, or accuses anyone automatically. Statutory scrutiny, inspections, and final decisions remain with authorized officials.

---

## 3. Non-negotiable principles

1. Findings are advisory; each states reason, evidence, rule ID/version, and recommended action.
2. An anomaly score is never proof of forgery.
3. `NOT_AVAILABLE` and `INCONCLUSIVE` are distinct from `FAIL`.
4. Simulated integrations are labeled `simulated: true` in the API and visibly in the UI.
5. A hash match proves integrity, not authenticity.
6. Regulatory rules are versioned configuration with citations; no hardcoded thresholds.
7. Every state change is attributable to an authenticated actor or a named system process.
8. Only synthetic or authorized anonymized data is used. No assumption of AICTE database or restricted issuer access.
9. RBAC, confidentiality, and human review are enforced server-side.
10. No AI component makes a final decision or emits accusatory language.

---

## 4. Roles and permissions

| Capability | Applicant | Reviewer | Approver | Admin | Auditor |
|---|---|---|---|---|---|
| Create/edit own institution application (draft) | ✅ own | — | — | — | — |
| Upload document versions | ✅ own | — | — | — | — |
| Submit / withdraw | ✅ own | — | — | — | — |
| View application + findings | ✅ own | ✅ assigned/scope | ✅ scope | ✅ all | ✅ all (read-only) |
| Trigger validation / revalidation | ✅ own (on submit) | ✅ assigned | ✅ scope | ✅ | — |
| Run issuer verification | — | ✅ assigned | ✅ scope | ✅ | — |
| Request rectification / add notes | — | ✅ assigned | ✅ scope | — | — |
| Escalate | — | ✅ assigned | ✅ scope | — | — |
| Record recommendation | — | ✅ assigned | ✅ scope | — | — |
| Record final decision | — | — | ✅ delegated authority | — | — |
| Manage users | — | — | — | ✅ | — |
| Manage categories / checklists | — | — | — | ✅ | — |
| Manage rule sets (draft/activate) | — | — | — | ✅ | — |
| View audit log | ✅ own events | ✅ assigned | ✅ scope | ✅ | ✅ all |
| Access ZKP request/verify | ✅ own credential | ✅ assigned | ✅ scope | ✅ | — |
| Anchor / revoke (chain) | — | — | — | ✅ service role | — |

Authorization is enforced per object and per route. Deny by default.

---

## 5. MVP scope

### 5.1 In scope

| Area | MVP implementation |
|---|---|
| Applications | EoA category, full lifecycle, durable versions, configurable checklist |
| Institutions | Profile + synthetic AICTE-style registry for cross-checks |
| Institutional records | Read-only synthetic source: previous EoA/approval status, programmes/intake, faculty, compliance deficiencies, TER payment, accreditation/NOC; frozen snapshot per validation run |
| Documents | Four OCR types; PDF/JPEG/PNG; 25 MB cap; magic-byte + structural validation; SHA-256; immutable storage |
| Infrastructure evidence | Photo/video/floor-plan/certificate attachments mapped to requirements; presence/completeness and advisory flags only; no CV claims in MVP |
| Extraction | Page-aware fields, confidence, provenance, explicit failure states |
| Rules | 15+ rules: required documents/evidence, expiry, name/identifier consistency, programme/intake, previous EoA validity, unresolved deficiencies, TER status where available, date ordering |
| Findings | Evidence-linked (document/field/record), deterministic, rule-version pinned |
| Issuer verification | Adapter interface; simulated AICTE/affiliation/university adapters; one Ed25519-signed local issuer; QR/signature path where a sample exists |
| Anomaly signals | Exact/perceptual duplicate detection, metadata editor, font inconsistency, mismatched identifiers, irregular dates; advisory only |
| ZKP | Sound Groth16 threshold proof over a Poseidon commitment; server-side verification; replay protection |
| Blockchain | Local Hardhat demo chain; document/credential/proof-result hashes anchored; access control + revocation; Amoy optional |
| Review | Queue, case view, notes, rectification, escalation, recommendation, decision, alerts |
| Audit | Append-only, hash-chained event log with attribution; rules/records/source responses/actions recorded |
| Security | JWT auth, RBAC, tenancy isolation, upload hardening, secret management, rate limits, retention |
| Quality | pytest, Playwright, Hardhat tests, circuit tests, golden rule cases, measured extraction/anomaly baseline, evaluation report |

### 5.2 Out of scope for MVP

- Real AICTE databases, real issuer APIs, or production DigiLocker. The MVP implements adapter boundaries and synthetic sources only; live integration requires authorized credentials and legal approval.
- AICTE portal write-back or automated submission; the platform is designed for integration, not connected to production.
- Automated approval/rejection or conclusive fraud determination.
- ML forgery/deepfake detection without labeled data and measured performance.
- Automated computer-vision assessment of infrastructure evidence (research spike only).
- Payments/fee reconciliation or approval-status integration without an authorized source.
- Mobile apps, multi-language OCR, production-scale deployment.
- Full W3C VC Data Integrity conformance (see §9.6).
- Production trusted-setup ceremony (dev ceremony only, clearly labeled).

---

## 6. Core workflows

### 6.1 Application lifecycle

1. Applicant creates an EoA application for the active category/cycle.
2. System identifies the applicable category checklist, snapshots it onto the application, and retrieves the available institutional-record snapshot (previous approvals, programmes/intake, faculty, deficiencies, TER, accreditation/NOC) with source and timestamp.
3. Applicant uploads document versions against checklist items.
4. Each upload is validated, hashed, stored, and queued for processing.
5. Applicant submits; mandatory items must be satisfied or explicitly justified (recorded).
6. System queues a validation run against the active rule set version.
7. Reviewer reviews findings, evidence, issuer results, anomaly signals, and ZKP results.
8. Reviewer requests rectification or records a recommendation; approver records the decision.
9. New document versions trigger revalidation; prior runs and findings remain immutable.
10. Every transition emits an audit event.

### 6.2 Document processing

`validate → SHA-256 → immutable store → classify → extract (page-aware) → normalize → confidence/state → index`

Failure states (`UNREADABLE`, `LOW_CONFIDENCE`, `FAILED`) are explicit and never treated as verified facts.

### 6.3 Validation

`run (pinned rule set) → evaluate rules → findings + evidence → summary`

Outcomes per finding: `PASS`, `FAIL`, `INCONCLUSIVE`, `NOT_AVAILABLE`, `NOT_APPLICABLE`.

### 6.4 Issuer verification

`document → adapter selection → request → recorded response (source, time, status, simulated flag) → verification state`

States: `VERIFIED`, `MISMATCH`, `EXPIRED`, `PENDING`, `SOURCE_UNAVAILABLE`, `MANUAL_REVIEW`.

### 6.5 Faculty eligibility ZK proof (implemented)

1. An authorized applicant or staff member requests a challenge for an application. The server stores a random `requestHash`, a server-issued threshold (`FACULTY_THRESHOLD_SCALED`, default `700`), the circuit/version, and a 600-second expiry. The applicant cannot choose the threshold.
2. The holder generates a Groth16 proof locally from `(value, blinding, secret)`. The browser console uses snarkjs and the pinned artifacts.
3. The backend recomputes and matches the request binding and threshold, verifies the proof with a pinned verification key via snarkjs, and requires all five public signals with `valid == "1"`.
4. The challenge is consumed only after successful verification. Nullifiers are globally unique; rejected attempts are audit-only and are not stored as proof rows.
5. The verified proof row records circuit name/version, vkey hash, commitment, nullifier, threshold, and status. Raw private inputs and raw proof JSON are not exposed.
6. The reviewer sees that the threshold was satisfied — never the exact private value.

**Implemented limitation:** the proof is **not bound to an issuer-issued Poseidon credential or a verified real-world identity**. It proves that a committed private value meets the server threshold. The demo issuer uses real Ed25519 signatures but does not issue the commitment/private payload described in §9.2.

### 6.6 Anchoring (implemented, optional)

`proof row → export Solidity calldata → submit verifyAndAnchor (service signer) → persist tx hash/status → anchor record on-chain`

- Anchoring is hash-only and disabled by default (`BLOCKCHAIN_PROOF_ANCHORING_ENABLED=false`).
- The backend submits one attempt; failures are stored as `FAILED` with an error message. There is no durable retry queue.
- Chain unavailability never blocks application processing, review, or decisions.
- `ANCHORED` means a transaction was mined; it is tamper-evidence, not authority or authenticity.

---

## 7. Application state model

```
DRAFT ──submit──▶ SUBMITTED ──assign──▶ UNDER_REVIEW
  │                  │                       │
  │                  │                       ├─request rectification─▶ RECTIFICATION_REQUESTED
  │                  │                       │                              │
  │                  │                       │                         resubmit
  │                  │                       │                              ▼
  │                  │                       │                        UNDER_REVIEW
  │                  │                       ├─recommend approve/reject─▶ (approver)
  │                  │                       │                              │
  │                  │                       │                       APPROVED | REJECTED
  │                  └─withdraw─▶ WITHDRAWN  │
  └─delete draft──▶ (hard delete, audited)   │
```

Rules:
- Transitions are explicit, validated server-side, and audited.
- A completed validation run is immutable and references its rule set version.
- Rectification preserves prior document versions, runs, and findings.

---

## 8. Functional requirements

Requirement IDs `O1–O18` (official), `R1–R52` (implementation), and `X1–X23` (cross-cutting) are defined in [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md). ZKP and chain requirements `Z1–Z8`, `B1–B5` are defined in §9.

Additional MVP behaviors:

| ID | Requirement |
|---|---|
| F1 | Application reference numbers are human-readable and unique (`APP-YYYY-NNNNNN`). |
| F2 | Checklist instantiation is snapshot-based; later category edits do not alter existing applications. |
| F3 | Upload is idempotent per `(application_id, checklist_item_id, sha256)` with a client idempotency key. |
| F4 | Every finding is either evidence-linked or explicitly `NOT_AVAILABLE`/`NOT_APPLICABLE`. |
| F5 | Raw document text is visible only to roles authorized for the case; never in list endpoints or logs. |
| F6 | Reviewer actions require a rationale (minimum 10 characters). |
| F7 | Decisions require an approver role and record scope, rationale, and timestamp. |
| F8 | Alerts are generated idempotently from findings/status transitions and are resolvable. |
| F9 | Audit events are append-only and hash-chained; tampering is detectable. |
| F10 | Simulated responses are distinguishable in both API and UI. |
| F11 | Institutional records are frozen into an immutable snapshot per validation run, with source, retrieval time, and `synthetic` flag. |
| F12 | Previous-EoA, programme/intake, faculty, deficiency, accreditation/NOC, and TER checks emit `NOT_AVAILABLE` when the authorized source is absent — never a silent pass. |
| F13 | Infrastructure evidence is checked for presence, type, recency, and requirement mapping; missing/inconclusive evidence recommends further evidence or inspection. No CV-based compliance conclusion is produced in MVP. |
| F14 | Every anomaly flag records its method/version, evidence reference, and reason, and is labeled as a preliminary indicator. |

---

## 9. ZKP and blockchain specification (MVP)

### 9.1 Purpose and limits

ZKP provides **privacy-preserving faculty eligibility** checks: proving a threshold on a committed value without revealing the exact value. It is **not** document authentication and must never be described as proving a document is genuine.

**Implemented boundary:** the proof demonstrates that a committed private value meets a server-issued threshold. It does **not** prove the value is true, that it came from an issuer-signed credential, or that the holder is a real person. The nullifier prevents replay within the challenge lifecycle but is not identity-bound.

The reviewer still receives the document, extraction evidence, and issuer verification. ZKP supplements evidence; it does not replace it.

### 9.2 Credential and commitment (partial)

- Demo issuer credentials use **real Ed25519** signatures over canonical JSON and bind a document version by SHA-256.
- The credential payload records issuer, document hash, subject reference, claims, timestamps, and `synthetic: true`.
- **Not implemented:** an issuer-issued Poseidon commitment, separately delivered `(value, blinding)` payload, and ZKP verification against that credential. The current ZKP flow accepts holder-provided private inputs.

### 9.3 Circuit (implemented)

`circuits/faculty_threshold.circom`, built with circom 2.2.3 and circomlib:

- Private inputs: `value`, `blinding`, `secret`, `threshold`, `requestHash`.
- Outputs: `valid`, `nullifier`, `commitment`.
- Constraints:
  1. `commitment = Poseidon(value, blinding)`.
  2. `nullifier = Poseidon(secret, requestHash)`.
  3. `valid = GreaterEqThan(32)(value, threshold)`.
- Public-signal order (fixed): `[valid, nullifier, commitment, threshold, requestHash]`.
- Curve: BN254. Proving system: Groth16. Circuit version: `2.0.0`.
- The old `range_proof.circom` uses `<--` with a boolean-only constraint and is unsound. It is disabled by default (`ZKP_ALLOW_LEGACY_CIRCUIT=false`) and must not be used.
- The trusted setup is **development-only**, not a multi-party ceremony.

### 9.4 Challenge and verification (implemented)

1. `POST /api/v1/zkp/applications/{application_id}/challenge` creates a stored challenge with a random `request_hash`, server threshold, circuit name/version, audience, and TTL (`ZKP_CHALLENGE_TTL_SECONDS=600`). The threshold comes from configuration, not the client.
2. `POST /api/v1/zkp/proofs` accepts exactly five public signals and the proof.
3. The backend checks challenge ownership, pending state, expiry, request hash, threshold, circuit name/version, public-signal consistency, and a pinned vkey.
4. snarkjs Groth16 verification must return `true`; `valid == "1"` is required.
5. The nullifier must be unique. The challenge is consumed only after successful verification.
6. Failure returns a typed error; rejected attempts are audit-only and do not create proof rows.
7. Success stores `VERIFIED` (optionally `ANCHORED`) and an audit event. Raw private inputs and raw proof JSON are not returned.
8. `GET /api/v1/zkp/verify-status` reports pinned-vkey availability/hash, circuit version, legacy-circuit policy, and explicit warnings.

### 9.5 Blockchain anchoring (implemented, optional)

- Contract: `blockchain/contracts/AstraVerifyAnchorV2.sol` using OpenZeppelin `AccessControl`.
- Roles actually implemented: `DEFAULT_ADMIN_ROLE`, `ANCHOR_ROLE`, `VERIFIER_ROLE`.
- Functions: `anchorPayload(bytes32 payloadHash, bytes32 nullifier)`, `verifyAndAnchor(pA, pB, pC, pubSignals, payloadHash)`, `recordExists(bytes32)`.
- Stored on-chain: payload hash, nullifier, threshold, request hash, submitter, timestamp, existence.
- Events: `PayloadAnchored`, `ProofVerified`. Custom errors reject zero hashes, duplicates, reused nullifiers, invalid public signals, and failed proofs.
- The backend exports Solidity calldata via snarkjs, converts hex strings to integers, and submits one transaction using a configured service key. It persists tx hash and status; failure is explicit and non-blocking.
- `BLOCKCHAIN_ENABLED=false` and `BLOCKCHAIN_PROOF_ANCHORING_ENABLED=false` are the defaults. Local Hardhat is the demo default; Amoy requires a funded key.
- **Not implemented:** on-chain revocation and a durable retry queue.
- Chain anchoring proves a hash existed at a point in time. It does not prove document authenticity or regulatory compliance.

### 9.6 Cryptographic honesty

- Demo issuer signatures are real Ed25519 over canonical JSON; the legacy HMAC-labelled-Ed25519 path is not used by the new flow.
- API and UI distinguish document integrity (SHA-256), demo issuer signature verification, threshold-proof verification, and simulated issuer source status.
- No field or label collapses these into “authentic”.
- Dev trusted setup and synthetic thresholds are labelled; production requires an MPC ceremony and approved rule sources.
- ZKP is not credential-bound; see §9.2.

### 9.7 ZKP requirement IDs and current status

| ID | Requirement | Status |
|---|---|---|
| Z1 | Sound threshold circuit | Working |
| Z2 | Issuer-issued Poseidon commitment + separate private payload | Partial; not credential-bound |
| Z3 | Server-side Groth16 verification with pinned vkey | Working |
| Z4 | Request binding, nonce, nullifier uniqueness, expiry | Working |
| Z5 | Client-side proving with pinned artifacts | Working (`/compliance`) |
| Z6 | Proof request/verify APIs with audit events | Working |
| Z7 | No raw value leakage in API, logs, chain, or UI | Working |
| Z8 | Circuit/artifact provenance per proof | Working |
| B1 | Access-controlled anchoring + revocation | Partial; ACL working, revocation absent |
| B2 | Backend anchoring service with durable retry queue | Partial; single attempt only |
| B3 | Confirmation tracking and non-blocking fallback | Working |
| B4 | Hash-only on-chain payloads (no PII) | Working |
| B5 | On-chain proof verification and event emission | Working |

---

## 10. Data model and modules

- Full schema: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)
- Module boundaries and flows: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

Core entities: `users`, `refresh_tokens`, `institutions`, `applications`, `application_categories`, `checklist_templates`, `checklist_template_items`, `application_checklist_items`, `documents`, `document_versions`, `extractions`, `extracted_fields`, `infrastructure_evidence`, `approval_history`, `programmes`, `faculty_records`, `compliance_deficiencies`, `ter_payments`, `accreditation_records`, `nocs_permissions`, `institutional_record_snapshots`, `rule_sets`, `rules`, `validation_runs`, `findings`, `finding_evidence`, `issuer_verifications`, `anomaly_signals`, `credentials`, `issuer_keys`, `zk_proof_requests`, `zk_proofs`, `chain_anchors`, `review_actions`, `decisions`, `alerts`, `audit_events`, `jobs`, `outbox_events`.

---

## 11. API

Full contracts: [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md). Summary:

```
/auth/*                    login, refresh, logout, me
/categories, /checklists   read (admin write)
/applications/*            CRUD, submit, withdraw, validate, findings, audit
/documents/*, /document-versions/*
                           upload, versions, process, extraction
/issuer-verifications/*    run, list
/zkp/requests/*            create, get, submit proof, verify
/chain/anchors/*           status, retry (admin)
/review/*                  queue, notes, rectification, escalation, recommendation
/decisions/*               final decision (approver)
/alerts/*                  list, acknowledge, resolve
/audit/*                   per-application and global (scoped)
/admin/*                   users, rule sets, categories
```

All endpoints are authenticated except `/health` and `/auth/login`. Errors use a single envelope with a stable code and `request_id`.

---

## 12. Security, privacy, and data handling

- JWT access (15 min) + rotating refresh (7 days), revocation on logout/password change.
- Argon2id password hashing. Login rate limit 5/min/IP; generic error messages.
- Shared authorization dependency with role + object checks; deny by default.
- Upload: allowlist PDF/JPEG/PNG, 25 MB cap, magic-byte check, PDF structure validation, image decode, randomized keys, no execution, optional ClamAV scan.
- Object storage private; 5-minute presigned GET; no public bucket.
- PostgreSQL encrypted volume; TLS for non-local deployments.
- Secrets from env/secret store; startup fails if required secrets are missing; the current committed default key is removed and rotated.
- No document contents or tokens in logs; structured redaction.
- Uploaded content is untrusted; if an LLM is introduced, it has no tool access, schema-validated output, and prompt-injection tests.
- Retention configurable (demo default 90 days), deletion audited.
- Chain keys: demo-only env key; production KMS out of scope.
- Institutional isolation tests are release-blocking.

---

## 13. Non-functional requirements

| Area | Target |
|---|---|
| Persistence | Survives restart; PostgreSQL is the source of truth |
| Processing | 10-page text PDF < 30 s; scanned PDF < 90 s on demo hardware |
| Determinism | Same inputs + same rule set/version ⇒ identical findings |
| Traceability | 100% of findings evidence-linked or explicitly unavailable |
| Audit | 100% of transitions audited; hash chain verifiable |
| Availability | Chain/issuer outage degrades gracefully; no data loss |
| Proof verification | < 2 s off-chain for a single proof |
| Accessibility | Keyboard-navigable review flows; status not conveyed by color alone |
| Observability | Structured logs, request IDs, job metrics, health/readiness |

---

## 14. Acceptance criteria

1. Applicant can register/login, create an application from the category, upload all four document types, submit, and track status; data survives restart.
2. Applicant A cannot read or mutate Applicant B’s application, documents, findings, proofs, or audit events (403/404 as appropriate).
3. Reviewer sees only assigned/scope applications; auditor is read-only; applicant cannot access review endpoints.
4. Checklist snapshot is enforced at submission; exceptions require a recorded justification.
5. Extraction returns page-aware fields with confidence; low-confidence/unreadable states are visible and never treated as verified.
6. Validation runs against a pinned rule set version and produces identical results for golden cases.
7. Every finding shows reason, evidence, rule ID/version, and recommended action; none asserts forgery.
8. `NOT_AVAILABLE` and `INCONCLUSIVE` are displayed distinctly from `FAIL`.
9. Issuer verification handles all six states; every simulated response is labeled in API and UI.
10. A valid ZK proof is accepted; tampered proof, wrong commitment, wrong threshold, reused nullifier, and expired request are rejected.
11. No raw private value appears in API responses, logs, chain payloads, or UI.
12. Document/credential hashes and proof results are anchored on the demo chain with recorded tx/block/chain IDs; chain outage does not block processing.
13. Unauthorized anchoring/revocation is rejected by the contract.
14. Reviewer notes, rectification, escalation, recommendation, and decision are recorded and attributable.
15. Audit history is retrievable and hash-chain verification passes.
16. Upload abuse cases (wrong type, oversized, spoofed MIME, malformed PDF) are rejected safely.
17. Automated tests cover lifecycle, authorization, rules, upload hardening, ZKP, chain, and audit; results are reported.
18. The system identifies the EoA category and applies the configured checklist and rule set.
19. Institutional-record checks use a frozen snapshot; unavailable TER, approval, programme, faculty, or deficiency records are reported as `NOT_AVAILABLE`, never as a pass.
20. Infrastructure evidence (photo/video/floor plan/certificate) can be attached and mapped to requirements; missing or inconclusive evidence yields an advisory finding recommending additional evidence or inspection.
21. The evaluation metrics defined in [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) are measured on the synthetic dataset and reported; no metric is claimed without a run.

---

## 15. Simulated and synthetic components

| Component | Behavior | Labeling |
|---|---|---|
| Institution registry | Curated synthetic records | `synthetic: true` |
| AICTE-style institutional records | Previous EoA, programmes, faculty, deficiencies, TER, accreditation/NOC | `synthetic: true`, `source: "synthetic-aicte-records"` |
| Issuer adapter | External source explicitly reports `SOURCE_UNAVAILABLE` | `simulated_source: true`, source label |
| Local Ed25519 issuer | Real Ed25519 signature over a synthetic, document-bound credential | `synthetic: true`, “Synthetic Demo Issuer (not AICTE)” |
| ZKP threshold | Server-issued synthetic threshold, dev trusted setup | Configuration and docs label; not an official eligibility rule |
| DigiLocker | Disabled in MVP; if enabled, labeled | Explicit banner |
| Anomaly signals | Deterministic heuristics | `method_version`, advisory language |
| Blockchain | Hardhat local (Amoy optional) | Chain ID + “demo network” label |
| Trusted setup | Dev ceremony | `setup: "dev"` in artifact metadata |

---

## 16. Technology choices and justification

| Choice | Justification |
|---|---|
| Retain FastAPI | Existing OCR/forensics code and tests; fast iteration |
| Retain React/Vite/Tailwind | Working portals and design system; minimal rewrite |
| Add PostgreSQL | Transactions, constraints, concurrency, audit integrity |
| Add MinIO | S3-compatible private object storage; easy local demo |
| Add SQLAlchemy 2 + Alembic | Typed models, migrations, testability |
| JWT + Argon2id | Simple, demonstrable RBAC without external IdP dependency |
| Retain Hardhat | Existing contracts and deployment scripts |
| circomlib + snarkjs | Standard, auditable Groth16 toolchain |
| Ed25519 via `cryptography` | Correct signature scheme; already available |
| pytest + Hardhat tests | API/E2E backend and contract coverage; no browser automation yet |

---

## 17. Open items

1. **Approved regulatory rule sources.** The official statement is supplied, but the actual Approval Process Handbook checklists, thresholds, and citations are not. Until supplied, MVP rules are synthetic and labeled as such.
2. **Authorized source access.** No AICTE portal/API credentials exist; the MVP uses synthetic record and issuer adapters. Live integration requires authorization.
3. **Retention period and data-handling policy** confirmation.
4. **`frontend/landing/`** disposition (rebuild or remove).
5. **Amoy deployment** only if a funded test key is provided; otherwise local Hardhat.
6. **Document and infrastructure samples** for the four OCR types plus photo/video/floor-plan examples to build the labeled corpus.
7. **Interpretation confirmation** of any AICTE-specific terminology in the official statement (e.g., TER, EoA cycle) used in the synthetic model.

---

## 18. Phase gate

Phases 1–10 have been implemented and locally verified as recorded in `docs/REQUIREMENTS_TRACEABILITY.md` and `docs/TEST_PLAN.md`. Phase 11 documentation/demo hardening is in progress. Remaining work is limited to the gaps in §17 and the limitations in §9 and §15; no production or official-integration claim is made.

---

## 19. Official statement mapping (summary)

| ID | Official requirement (condensed) | MVP approach | Phase |
|---|---|---|---|
| O1 | Identify application category and applicable checklist | EoA category + versioned checklist templates | 3 |
| O2 | Retrieve authorized institutional records (previous EoA, programmes/intake, faculty, deficiencies, TER, accreditation/NOC, application history) | Synthetic `AICTE` record source behind an adapter; frozen snapshots; labeled synthetic | 3 |
| O3 | Validate fields/documents using OCR, classification, extraction | Existing OCR pipeline + four document types; page-aware fields | 4 |
| O4 | Find missing, incomplete, expired, inconsistent information | Versioned rule engine; `NOT_AVAILABLE` distinct | 5 |
| O5 | Structured validation report and rectification | Findings + report export; rectification workflow | 5, 8 |
| O6 | Detect alterations, duplication, metadata inconsistencies, mismatched identifiers, irregular dates | Deterministic anomaly signals with evidence; advisory only | 7 |
| O7 | Verify through issuing authorities; record source/time/result; six statuses | Adapter interface + simulated adapters; QR/signature where sample exists | 6 |
| O8 | Configurable checklists from Handbook/regulations | Versioned rule sets with citations; no hardcoded thresholds | 5 |
| O9 | Infrastructure evidence review; CV where feasible; recommend evidence/inspection | Attachment model + presence/completeness checks; CV research spike only | 7 |
| O10 | Validation dashboard, deficiencies, verification, pending actions | Reviewer queue + case view | 8 |
| O11 | Alerts for missing/expired/pending/anomalies | Alert engine with dedupe and resolution | 8 |
| O12 | Audit trail of rules, records, source responses, alerts, actions | Hash-chained append-only audit log | 8 |
| O13 | RBAC, secure handling, confidentiality, human review | JWT + per-object authorization; upload hardening; approver gate | 3, 8, 9 |
| O14 | Configurable checks; no bypass/assumed access | Config-driven rules; adapter capability reporting; no restricted access assumptions | 5, 6, 9 |
| O15 | Data protection, access logging, retention | Encryption, redacted logs, retention policy | 9 |
| O16 | Explainable flags; decision-support only | Evidence-linked findings; non-conclusive wording; no auto-decisions | 5, 7, 8 |
| O17 | Prototype designed for AICTE portal integration | Explicit `AICTE` adapter boundary + OpenAPI contracts | 2–3 |
| O18 | Evaluation metrics | Measured per `docs/TEST_PLAN.md` §9 | 10 |
