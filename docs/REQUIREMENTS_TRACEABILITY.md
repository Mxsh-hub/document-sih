# Requirements Traceability — AstraVerify / AICTE Adaptation

**Date:** 2026-10-25
**Version:** 3.1 (post-implementation; adds structured declaration and three-way consistency)
**Sources:**
1. Official SIH problem statement — *AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification* (supplied 2026-10-23).
2. `IMPLEMENTATION_ROADMAP.md`.
3. Repository inspection: `docs/REPOSITORY_AUDIT.md`, source, migrations, tests, and executed checks.

**Approved scope:** EoA category; PostgreSQL + S3/MinIO + JWT/Argon2id; sound faculty-eligibility ZKP and hash-only anchoring retained; four OCR document types; synthetic AICTE-style records; infrastructure evidence limited to presence/completeness checks.

**Status legend:** `WORKING`, `PARTIAL`, `N/A` (deferred or not applicable). `MOCKED`/`ABSENT` no longer describe the new compliance flow; legacy stubs are listed separately in §11.

> **Advisory boundary:** no status here means a document is authentic, an application is compliant, or AICTE has taken a decision. All seeded rules, records, institutions, issuer responses, and metrics are synthetic or demo-only unless explicitly stated.

---

## 1. Coverage summary

| Group | Count | Working | Partial | N/A |
|---|---:|---:|---:|---:|
| Official requirements (O1–O18) | 18 | 10 | 8 | 0 |
| Implementation requirements (R1–R56) | 56 | 52 | 3 | 1 |
| ZKP / blockchain (Z1–Z8, B1–B5) | 13 | 10 | 3 | 0 |
| Cross-cutting (X1–X23) | 23 | 21 | 1 | 1 |
| Post-MVP additions (M4–M6) | 3 | 3 | 0 | 0 |
| **Total** | **113** | **96** | **15** | **2** |

No official requirement is met through real AICTE integration. Working items are prototype capabilities proven against synthetic data, local PostgreSQL, local storage, a local Hardhat chain, and an automated pytest/contract suite.

---

## 2. Official requirements matrix

| ID | Official requirement | Status | Evidence | Remaining limitation |
|---|---|---|---|---|
| O1 | Identify category and applicable checklist | WORKING | EoA category; versioned checklist template snapshotted at application creation | Only EoA seeded |
| O2 | Retrieve records from authorized AICTE systems | PARTIAL | `InstitutionRecord` model, synthetic `AICTE` adapter, frozen snapshots | No authorized AICTE source |
| O3 | Validate fields/documents with OCR, classification, extraction | WORKING | Four OCR document types; evidence-linked extraction; validation rules | Classification is heuristic; declared type wins |
| O4 | Identify missing, incomplete, expired, inconsistent items | WORKING | Versioned rules with `NOT_AVAILABLE`/`INCONCLUSIVE`; declared-vs-extracted-vs-record consistency rules | Synthetic rule definitions; declarations are applicant-supplied, not verified |
| O5 | Structured report and rectification | WORKING | Findings, evidence, review actions, rectification state, alerts with dispositions, and an advisory JSON/Markdown/HTML report export (`GET /applications/{id}/report`) | No PDF renderer, no signature, no queued export; the report is a review aid, not an official AICTE document |
| O6 | Alteration, duplication, metadata, identifier, date anomaly analysis | WORKING | Cross-application hash reuse, shared identifiers, PDF metadata heuristics | Heuristics are advisory, not calibrated against real labels |
| O7 | Verify with issuing authorities; source/time/result; six states | PARTIAL | Adapter interface, six states, demo Ed25519 issuer, provenance | No real AICTE/issuer authority access; external adapter returns `SOURCE_UNAVAILABLE` |
| O8 | Compare against configurable Handbook/regulatory checklists | PARTIAL | DB-backed versioned rule sets, activation, citations | Seeded thresholds/citations are synthetic; official sources not supplied |
| O9 | Infrastructure evidence review; flag for evidence/inspection | PARTIAL | Infrastructure evidence registration and presence/completeness assessment | No image/video CV analysis (explicitly deferred) |
| O10 | Validation dashboard with status and pending actions | WORKING | `/api/v1/review/overview`, dashboard summary, `/compliance` console | Demo UI, not usability-tested |
| O11 | Alerts for missing, expiry, pending verification, anomalies | WORKING | Alert engine, dedupe, resolution on decision | Synthetic triggers |
| O12 | Audit trail of rules, sources, responses, alerts, actions | WORKING | SHA-256 chain, global sequence, verification endpoint | Chain is DB-local; no external timestamping |
| O13 | RBAC, secure handling, confidentiality, human review | WORKING | JWT/refresh tokens, Argon2id, object-level checks, approver-only decisions | No MFA; no field-level encryption |
| O14 | Configurable checks; no bypass or assumed restricted access | PARTIAL | Config-driven rule activation and explicit adapter capability labels | No real restricted source exists to exercise |
| O15 | Data protection, access logging, retention safeguards | PARTIAL | Security headers, request IDs, access/audit events, signed downloads | Retention job and field-level encryption absent |
| O16 | Explainable, evidence-supported, decision-support-only flags | WORKING | Finding evidence, non-conclusive wording, human decision gate | — |
| O17 | Integrated with, or designed for, AICTE portal/sources | PARTIAL | Explicit adapter boundary and API contracts | No AICTE portal integration |
| O18 | Evaluate accuracy, anomalies, verification, alerts, effort | PARTIAL | Synthetic evaluation harness and `results.json` | Metrics are synthetic-only; no real-world accuracy claim |

---

## 3. Application and institutional records (Phase 3)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Application-centered create/edit/submit/status | WORKING | `Application`, state machine, CRUD/submit APIs |
| R2 | Category-specific checklists | WORKING | Versioned template + immutable application snapshot |
| R3 | Institution profiles and synthetic records | WORKING | `Institution` + seeded synthetic records |
| R4 | Documents linked to application and checklist item | WORKING | FK validation and ownership checks |
| R5 | Document versions and rectification | WORKING | `DocumentVersion`, current pointer, reprocess; new uploads after rectification |
| R6 | Persistence across sessions | WORKING | PostgreSQL 16 + Alembic; local/S3 storage abstraction |
| R7 | Server-side RBAC for applications/records | WORKING | Role dependencies and object-level authorization tests |
| R45 | Retrieve and freeze institutional records | WORKING | Synthetic `AICTE` adapter; `institutional_record_snapshots` |
| R46 | Validate against fetched records | WORKING | Cross-record rules with evidence references |
| R47 | Validate previous approval status/expiry | WORKING | `approval_history` rule; `NOT_AVAILABLE` when absent |
| R48 | Validate programmes/courses/intake | WORKING | `programmes` table and comparison rule |
| R49 | Validate faculty records/qualifications | WORKING | `faculty_records` rules plus optional threshold ZKP |
| R50 | Check unresolved compliance deficiencies | WORKING | `compliance_deficiencies` rule |
| R51 | Check TER payment status where authorized data exists | WORKING | `ter_payments` rule and `NOT_AVAILABLE` semantics |
| R52 | Infrastructure evidence mapping and checks | WORKING | `infrastructure_evidence`; presence/completeness only |

---

## 4. Document processing (Phase 4)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| R8 | Process PDFs and images | WORKING | pdfplumber → PyMuPDF → Tesseract; explicit unreadable/failed states |
| R9 | Classify document types | PARTIAL | Heuristic classification with confidence; never overrides declared type |
| R10 | Extract fields, identifiers, dates, institution details | WORKING | Type-specific extractors and normalization |
| R11 | Retain page, confidence, source evidence | WORKING | Page/bbox/page dimensions/confidence per evidence item; `/compliance` renders the source page with the box drawn |
| R12 | Handle unreadable/missing/low confidence | WORKING | `UNREADABLE`, `LOW_CONFIDENCE`, `FAILED`, `OCR_ENGINE_UNAVAILABLE`; review visibility |
| R13 | Store document hashes and secure originals | WORKING | SHA-256 at intake; immutable versions; signed local downloads |
| R14 | Measure extraction performance | WORKING | Synthetic harness: 100/100 fields, median 43.94 ms, p95 47.66 ms |

---

## 5. Rules and validation (Phase 5)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| R15 | Versioned, configurable rules | WORKING | `RuleSet`/`Rule`, activation by admin, immutable referenced versions |
| R16 | Category-specific required checklists | WORKING | EoA snapshot plus required-item submission gate |
| R17 | Detect missing/incomplete/expired/inconsistent information | WORKING | Rule predicates over extraction, documents, records |
| R18 | Cross-check names, identifiers, dates, fields | WORKING | Normalizers and comparison rules |
| R19 | Compare with institutional records | WORKING | Frozen record snapshots used by rules |
| R20 | Payment/approval-status checks where supported | WORKING | TER and approval rules; `NOT_AVAILABLE` otherwise |
| R21 | Rectification and revalidation | WORKING | New versions, new validation run, history retained |
| R22 | Findings explain reason, evidence, rule, next action | WORKING | Finding + evidence records and review API |
| R23 | Distinguish unavailable from failure | WORKING | `NOT_AVAILABLE`, `INCONCLUSIVE`, `NOT_APPLICABLE` |
| R24 | Deterministic outcomes for known cases | WORKING | Rule fixtures and automated tests |
| R53 | Structured applicant declaration (affiliation, programmes/intake, faculty count, previous approval) | WORKING | `application_declarations` (one row per application, versioned); `GET`/`PUT /applications/{id}/declaration`; draft-only, applicant-only, audited as `application.declaration_saved` |
| R54 | Three-way consistency: declared affiliation vs extracted certificate | WORKING | `AFFILIATION_DECLARATION_MATCH` compares normalised number and validity date; `NOT_AVAILABLE` without declaration or extraction; mismatch is advisory `FAIL` |
| R55 | Three-way consistency: declared programmes/intake vs synthetic records | WORKING | `PROGRAMME_DECLARATION_MATCH` flags declared programmes missing from records, intake differences on shared codes, and an inconsistent declared total |
| R56 | Three-way consistency: declared faculty count vs synthetic records | WORKING | `FACULTY_COUNT_DECLARATION_MATCH` compares against synthetic `faculty_records` count within a configurable tolerance (default 0) |

> R53–R56 were added after the initial matrix. The declaration is applicant-supplied and never verified by these rules: a match means two sources agree, a mismatch means a human should inspect both, and no rule changes application status.

---

## 6. Authentication and issuer verification (Phase 6)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| R25 | Separate integrity, authenticity, consistency | PARTIAL | Findings, issuer states, and anomaly signals are separate; no single unified authenticity verdict by design |
| R26 | Verify QR codes and digital signatures | PARTIAL | Real Ed25519 verification and document-hash binding; `qr-payload` decodes QR payloads (OpenCV) but never fetches or resolves them; `pdf-signature` inspects signature/`ByteRange` structure without CMS, certificate, revocation, or trust-chain verification |
| R27 | Adapter interface for authorized issuer APIs | WORKING | Adapter code, capability/status reporting, external unavailable path |
| R28 | Record source, timestamp, response, result | WORKING | `IssuerVerification` with adapter code, evidence, `simulated_source`, and inspection engine version |
| R29 | Six verification states | WORKING | Enum enforced end to end |
| R30 | Clearly labeled simulated issuer services | WORKING | Demo issuer named “Synthetic Demo Issuer (not AICTE)” and flagged |
| R31 | Never present hash match as authenticity proof | WORKING | Wording rules, UI copy, and test assertions |

> R26 stays **PARTIAL** after M3. Local QR decoding and PDF signature-structure inspection are implemented and tested, but the payload is never resolved against an authorised source and the CMS/certificate/revocation/trust chain is never verified. The API and UI state this limit on every result; no authenticity verdict is produced.

---

## 7. Anomaly and infrastructure compliance (Phase 7)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| R32 | Detect duplicate documents/identifiers | WORKING | SHA-256 reuse across applications; shared identifier signals |
| R33 | Detect inconsistent metadata/suspicious differences | WORKING | PDF metadata/font heuristics with evidence and method version |
| R34 | Evaluate CV for infrastructure evidence | N/A | Deferred by approved MVP scope |
| R35 | Associate media with requirements; flag insufficiency | WORKING | Registration, checklist mapping, presence/completeness |
| R36 | Recommend evidence or inspection | WORKING | Finding action types, including inspection recommendation |
| R37 | Explainable, non-conclusive anomaly findings | WORKING | Evidence-linked advisory wording; no forgery claim |

---

## 8. Review, alerts, audit (Phase 8)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| R38 | Search, filters, status summaries | WORKING | Reviewer queue, filters, dashboard counters |
| R39 | Application-level review view | WORKING | Review overview API and `/compliance` case view |
| R40 | Alerts | WORKING | Generated from findings/anomalies; unique `(application_id, alert_type, source_ref)`; staff dispositions (`FALSE_POSITIVE`/`ACCEPTED_RISK` require a note); stale finding/anomaly alerts auto-`SUPERSEDED` |
| R41 | Notes, rectification, escalation, decisions | WORKING | Review-action APIs with rationale and audit |
| R42 | Traceable history of rules, sources, actions | WORKING | Hash-chained `audit_events` |
| R43 | Historical explainability against rule versions | WORKING | Immutable rule sets + validation run references |
| R44 | Human control of final decisions | WORKING | Approver/admin-only decision endpoint; advisory system |

### 8.1 Post-MVP additions

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| M4 | Advisory report export and alert dispositions | WORKING | `GET /applications/{id}/report?format=json|markdown|html` (`application-report-1.0`, every export audited as `application.report_exported`); dispositions stored in `alerts.payload`; stale alerts auto-superseded; `/compliance` export buttons and alert panel. No PDF/signature/presigned artefact; the report is never an AICTE decision. |
| M5 | Read-only pre-submission self-check | WORKING | `GET /applications/{id}/self-check` (`self-check-1.0`) for `DRAFT`/`RECTIFICATION_REQUESTED`; blocking parity with `missing_required_items`, no writes; `/compliance` self-check panel. Advisory preview only: it does not run the rule engine and does not predict approval. |
| M6 | Demo hardening and evaluation | WORKING | `backend/scripts/demo_smoke.py` (live-HTTP walkthrough), `docs/DEMO_RUNBOOK.md` (script + safe phrasing + troubleshooting), advisory-controls section in `evaluation/run_evaluation.py` (39 checks incl. gate parity, report claim safety, disposition gating, supersede), dependency pins reconciled for Python 3.10. Still no browser automation or CI. |

---

## 9. ZKP and blockchain

| ID | Requirement | Status | Evidence | Remaining limitation |
|---|---|---|---|---|
| Z1 | Sound threshold circuit | WORKING | `faculty_threshold.circom`: Poseidon commitment, `GreaterEqThan`, nullifier | Proves only the committed value comparison |
| Z2 | Poseidon commitment + private payload delivery | PARTIAL | Demo issuer signs document-bound Ed25519 credentials | No issuer-issued Poseidon credential/private payload; ZKP is not credential-bound |
| Z3 | Server-side Groth16 with pinned vkey | WORKING | snarkjs verification; pinned vkey path/hash | Development trusted setup |
| Z4 | Request binding, nonce, nullifier, expiry | WORKING | Stored challenge, `requestHash`, TTL, unique nullifier, consume-on-success | Nullifier is not identity-bound |
| Z5 | Client-side proving with pinned artifacts | WORKING | `/compliance` browser proving via snarkjs and copied artifacts | Requires CDN/network |
| Z6 | Proof request/verify APIs + audit | WORKING | `/api/v1/zkp/*`, audit events | — |
| Z7 | No raw value leakage | WORKING | API does not expose witness/raw proof; tests check sentinel leakage | — |
| Z8 | Artifact/version provenance | WORKING | Circuit name/version, vkey hash recorded per proof | — |
| B1 | Access-controlled anchoring + revocation | PARTIAL | `AccessControl`, `ANCHOR_ROLE`, verifier role | On-chain revocation function absent |
| B2 | Backend anchoring service with retries | PARTIAL | Real `verifyAndAnchor` submission from backend | Single attempt, no retry queue |
| B3 | Confirmation tracking + non-blocking fallback | WORKING | Persisted tx hash/status; failures recorded, review not blocked | — |
| B4 | Hash-only on-chain payloads | WORKING | Contract stores hash/nullifier/public signals only | — |
| B5 | On-chain proof verification + event | WORKING | `verifyAndAnchor`, `PayloadAnchored`, `ProofVerified`; Hardhat test 5/5 | Local chain only |

---

## 10. Cross-cutting requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| X1 | Audit repository before changing it | WORKING | `docs/REPOSITORY_AUDIT.md` |
| X2 | Reuse working components | WORKING | OCR/extraction, FastAPI, React, Circom/snarkjs, Hardhat retained |
| X3 | Distinguish implemented/mock/planned | WORKING | README, audit, this matrix, runtime flags |
| X4 | No unapproved removal | N/A | Legacy routes/code preserved |
| X5 | No assumed restricted access | WORKING | External adapter explicitly returns simulated `SOURCE_UNAVAILABLE` |
| X6 | Configurable/versioned rules | WORKING | R15 |
| X7 | Evidence-linked findings | WORKING | Evidence records and review API |
| X8 | No anomaly score as proof of forgery | WORKING | Advisory copy and tests |
| X9 | Preserve RBAC/confidentiality/audit/human review | WORKING | R7/R42/R44 |
| X10 | Incremental delivery with tests/diff review | WORKING | Phase tests, full suite, contract tests |
| X11 | Meet phase criteria before proceeding | WORKING | Phase 1–10 deliverables executed and recorded |
| X12 | Role-based authorization | WORKING | Auth dependencies and isolation tests |
| X13 | Secure upload/storage/preview/download | WORKING | Allowlist, size limit, signed downloads, ownership |
| X14 | Validate file types/sizes/content | WORKING | Extension/MIME/size/magic checks |
| X15 | Protect secrets/config | WORKING | No committed secrets; startup validation requires ≥32-char secrets |
| X16 | Encryption/retention/access logging | PARTIAL | Access/audit logging exists; encryption-at-rest policy and retention job absent |
| X17 | Isolation/permission tests | WORKING | Cross-institution and role tests |
| X18 | Prompt-injection protection | WORKING | Extracted text treated as data; not sent to tools/LLM; raw text not exposed |
| X19 | Observability/audit integrity | WORKING | Request IDs, structured errors, audit-chain verification |
| X20 | E2E + synthetic dataset | WORKING | `test_phase10_e2e.py`, seed data, synthetic evaluation corpus |
| X21 | Measured metrics | WORKING | Synthetic evaluation results |
| X22 | Document limitations | WORKING | README, SPEC, this matrix |
| X23 | Reproducible demo with labeled simulations | WORKING | Seed, `/compliance`, `.env.example`, labelled demo issuer |

---

## 11. Legacy components explicitly excluded

These remain in the repository for historical reasons and **must not be presented as compliance capabilities**:

| Component | State | Rule |
|---|---|---|
| `services/deepfake.py`, `services/risk.py` | Hardcoded stubs | Not used by new validation |
| `Wallet/ImportOptions.jsx`, `digilocker.py` | Simulated upload/DigiLocker; proofs are `AstraSimulatedProof` placeholders | Legacy routes only; labelled simulations |
| `attestation.py` | Real Ed25519 over the canonical payload, honestly typed `AstraEd25519Signature`; demo key derived from config, not a published DID, not W3C Data Integrity | Not used by new issuer flow; covered by `test_legacy_attestation.py` |
| `routers/issuer.py` | HMAC-SHA256 integrity tag, typed `AstraDemoHmacIntegrity` | Legacy route only; not a signature |
| Legacy wallet routers (`upload`, `digilocker`, `issuer`, `verify`, `verifier`) | Unmounted unless `LEGACY_API_ENABLED=true` | Off by default |
| legacy `validate-zk` | Does not verify proofs | Not used by new flow |
| `circuits/range_proof.circom` | Unsound | Disabled; `ZKP_ALLOW_LEGACY_CIRCUIT=false` |
| `AstraVerifyAnchor.sol` | Legacy contract | V2 contract is used for new anchoring |

---

## 12. Remaining gaps and risks

1. **No official sources.** Handbook checklists, thresholds, citations, TER semantics, and retention policy were not supplied. Seeded rules are synthetic and configurable.
2. **No authority integration.** No AICTE portal/API, DigiLocker production access, or issuer credentials. External verification is explicitly unavailable/simulated.
3. **ZKP is not credential-bound.** The proof shows a committed private value meets a threshold; it does not prove the value is true or that the holder is a verified person. The demo credential uses Ed25519 but not a Poseidon commitment.
4. **Development trusted setup.** The Groth16 setup is not a production multi-party ceremony.
5. **Anchoring limitations.** Access control exists but revocation and retries do not; local Hardhat only; Amoy requires a funded key.
6. **No encryption-at-rest/retention job.** S3/MinIO is supported by configuration; field-level encryption and automated retention are absent.
7. **No CI/browser E2E.** Backend, contract, build, and one live anchor flow were run manually; `/compliance` was build-verified but not browser-automated.
8. **Synthetic metrics only.** Any measured performance describes the generated corpus and must be labelled as such.
9. **Declarations are unverified input.** The structured declaration (R53–R56) is applicant-supplied. Consistency rules only compare sources; they cannot detect a declaration that agrees with a wrong document or record, and the previous-approval reference is stored but not compared.

---

## 13. Phase gate status

| Phase | Acceptance criterion | Status |
|---|---|---|
| 1 | Audit, requirements mapping, dispositions, no app code modified | Met |
| 2 | SPEC, architecture, data model, API contracts, test plan | Met |
| 3 | Applications, persistence, document association, access control | Met; API/auth smoke tests and 26 tests |
| 4 | Traceable confidence-aware extraction | Met; 4 phase tests |
| 5 | Deterministic rule outcomes with evidence/unavailable semantics | Met; 5 phase tests |
| 6 | Verification states, labelled simulations, sound ZKP | Met for demo scope; real issuers unavailable |
| 7 | Explainable anomalies, measured performance, no forgery claims | Met for synthetic scope |
| 8 | Reviewer actions, attributable decisions, audit, human control | Met; phase tests |
| 9 | Unauthorized blocked, malformed files safe, no committed secrets, logging | Met; 7 security tests |
| 10 | Core flows, reproducible findings, measured metrics, limitations | Met; 61-test suite + synthetic evaluation |
| 11 | Reliable demo, simulations disclosed, claims supported | Documentation/demo completed; no browser automation/CI. Post-MVP hardening: M0 credibility containment, M1 evidence viewer, M2 structured declaration + three-way consistency, M3 QR/PDF-signature inspection, M4 report export + alert dispositions, M5 self-check, and M6 demo runbook + live walkthrough + advisory-control evaluation complete (86-test suite; no new migrations) |
