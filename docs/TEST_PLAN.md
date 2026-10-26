# Test Plan — AstraVerify (AICTE Adaptation)

**Status:** Phase 11 — implemented suites and executed results recorded; CI/browser automation not configured.
**Last updated:** 2026-10-25
**Companion documents:** [`SPEC.md`](../SPEC.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`DATA_MODEL.md`](DATA_MODEL.md) · [`API_CONTRACTS.md`](API_CONTRACTS.md) · [`REQUIREMENTS_TRACEABILITY.md`](REQUIREMENTS_TRACEABILITY.md)

---

## 1. Purpose and scope

This plan defines how the MVP will be verified against the official problem statement, the roadmap, and the approved ZKP/blockchain scope. It covers:

- Functional correctness of validation, verification, review, and audit workflows.
- Security properties (authorization, isolation, upload hardening, secret handling).
- Soundness and replay resistance of the ZKP flow.
- Access control and tamper-evidence of the anchoring contract.
- Explainability and evidence coverage.
- The evaluation metrics required by the problem statement.

Planned cases in §6 are the target design. The suites and checks actually executed are listed in §14; only those results are claimed. Items without a result remain planned, not passed.

---

## 2. Test levels

| Level | Scope | Tooling |
|---|---|---|
| Unit | Pure functions: normalizers, rule evaluators, hash/canonicalization, state machine, authz predicates | `pytest` |
| Integration | Modules against real PostgreSQL and MinIO; migrations; outbox/jobs | `pytest`, Docker Compose test profile |
| API contract | Routes, schemas, status codes, error envelope, OpenAPI drift | `pytest` + `httpx`, optional Schemathesis |
| End-to-end | Applicant → upload → validate → review → decide → audit | `pytest` + FastAPI TestClient (implemented); Playwright not set up |
| Security | Authz matrix, IDOR, upload fuzzing, token handling, secret scan, dependency audit | `pytest`, `bandit`, `pip-audit`, `npm audit`, `gitleaks`, `trivy` (optional) |
| Circuit | Constraint soundness, witness generation, proof verification | `circom`, `snarkjs`, Node test runner |
| Contract | Roles, anchoring, revocation, events, replay | Hardhat + ethers + Chai |
| Performance | Latency, throughput, queue lag | `k6` or `locust` |
| Accessibility/UI | Keyboard, labels, contrast, error messages | Playwright + axe-core (manual review for demo) |

---

## 3. Environments and fixtures

| Environment | Purpose | Data |
|---|---|---|
| `unit` | No external services | In-memory fixtures |
| `integration` | Ephemeral PostgreSQL 16 + MinIO | Migrations + seeded fixtures |
| `e2e` | Full Compose stack + Hardhat | Seeded synthetic dataset |
| `evaluation` | Full stack or batch harness | Labeled synthetic corpus |

**Rules:**

- Every test uses **synthetic or anonymized** data. No real Aadhaar, faculty PII, or institutional documents.
- Synthetic records carry `synthetic: true`; tests assert the flag propagates to API responses and UI badges.
- Tests must not depend on the developer's local `uploads/` or existing metadata.
- Large fixtures are generated deterministically by scripts and are not committed; small golden fixtures are committed.
- Each test run uses a unique schema/database and object-store prefix, torn down afterward.

---

## 4. Test data sets

| ID | Dataset | Contents | Size (MVP) |
|---|---|---|---|
| DS-1 | Document corpus | Affiliation certificate, land/lease, faculty degree, undertaking; clean, expired, low-quality scan, rotated, altered metadata, duplicate, name mismatch | 60 files (15 per type) |
| DS-2 | Applications | Clean, missing-document, expired-document, inconsistency, deficiency, TER-pending, approval-expired | 20 applications |
| DS-3 | Rule cases | Each active rule × `PASS`/`FAIL`/`NOT_AVAILABLE`/`NOT_APPLICABLE` as applicable | ≥ 60 cases |
| DS-4 | Anomaly corpus | Labeled duplicates, metadata edits, font inconsistencies, date anomalies, identifier mismatches, negatives | 40 files |
| DS-5 | Infrastructure evidence | Photos, floor plans, short videos, certificates; present/insufficient/inconclusive | 20 items |
| DS-6 | ZKP vectors | Valid, below-threshold, boundary, tampered signal, replay, expired request, wrong commitment/vkey | 12 vectors |
| DS-7 | Chain cases | Document, credential, proof-result anchors; duplicate, revoke, retry, outage | 10 cases |
| DS-8 | Audit scenarios | Sequential, concurrent, tampered chain, redacted actor | 100+ events |

**Golden labels:** each record includes the expected outcome, evidence reference, and rule version. A test fails if the output matches the outcome for the wrong reason (e.g., correct `FAIL` without evidence).

---

## 5. Traceability to requirements

| Official requirement | Primary suites |
|---|---|
| O1 category/checklist | `test_applications`, `test_admin_checklists` |
| O2 institutional records | `test_records`, `test_snapshots` |
| O3 OCR/classification/extraction | `test_processing`, `test_extraction_metrics` |
| O4 missing/expired/inconsistent | `test_rules_golden`, `test_phase5_validation`, `test_phase11_declarations` |
| O5 report/rectification | `test_phase13_report_and_alerts`, `test_phase11_declarations`, `test_phase8_review_audit` |
| O6 anomalies | `test_anomalies`, `test_anomaly_metrics` |
| O7 issuer verification | `test_issuer_adapters`, `test_verification_states` |
| O8 configurable checklists | `test_rule_config`, `test_rule_set_activation` |
| O9 infrastructure evidence | `test_infrastructure_evidence` |
| O10 dashboard | `test_review_queue`, e2e case view |
| O11 alerts | `test_phase13_report_and_alerts`, `test_phase8_review_audit` |
| O12 audit trail | `test_audit_chain`, `test_audit_coverage` |
| O13 RBAC/confidentiality/human review | `test_authz_matrix`, `test_decisions` |
| O14 no assumed access | `test_adapter_capabilities`, `test_synthetic_labels` |
| O15 retention/logging | `test_retention`, `test_log_redaction` |
| O16 explainability | `test_finding_evidence`, `test_wording` |
| O17 integration boundary | `test_openapi_contract`, `test_adapter_interfaces` |
| O18 evaluation metrics | `evaluation/` harness, §9 |

Implementation requirements R1–R56, Z1–Z8, B1–B5, and X1–X23 map to the suites in §6–§8. The traceability document remains the source of truth for status.

---

## 6. Functional test cases

### 6.1 Authentication and authorization

| ID | Case | Expected |
|---|---|---|
| AUTH-01 | Valid login | `200`, access + refresh tokens, no password hash |
| AUTH-02 | Invalid password | `401` generic message; `security_event` written; rate limit applies |
| AUTH-03 | Expired access token | `401 TOKEN_EXPIRED`; refresh works |
| AUTH-04 | Refresh rotation | Old refresh rejected on reuse; token family revoked |
| AUTH-05 | Logout | Refresh token revoked; access token remains valid until expiry (documented) |
| AUTH-06 | Password change | All refresh tokens revoked |
| AUTH-07 | Deactivated user | Login denied; existing access token denied at next check |
| AUTHZ-01 | Applicant A reads Applicant B's application | `404` (no enumeration) |
| AUTHZ-02 | Applicant uploads to another institution | `403`/`404` |
| AUTHZ-03 | Reviewer reads unassigned application | Denied unless queue scope allows; documented |
| AUTHZ-04 | Reviewer attempts final decision | `403` |
| AUTHZ-05 | Admin attempts final decision | `403` |
| AUTHZ-06 | Auditor attempts write | `403` |
| AUTHZ-07 | Applicant reads another holder's credential | `404` |
| AUTHZ-08 | Applicant downloads another application's document | `404`; no presigned URL issued |
| AUTHZ-09 | Reviewer in scope reads records; applicant does not | `200` vs `403`/`404` |
| AUTHZ-10 | Every route in the matrix has a positive and negative test | Complete matrix coverage |

### 6.2 Applications and checklists

| ID | Case | Expected |
|---|---|---|
| APP-01 | Create EoA application | `201`, reference generated, checklist snapshot created |
| APP-02 | Duplicate active application for same institution/cycle | `409` (policy confirmed) |
| APP-03 | Edit draft | Version increments; audit event |
| APP-04 | Edit submitted application | `409 STATE_CONFLICT` |
| APP-05 | Submit with missing required document | `400 VALIDATION_FAILED` listing items |
| APP-06 | Submit with all required items | `202`, validation run queued |
| APP-07 | Withdraw from allowed states | `200`, terminal state, audit |
| APP-08 | Withdraw from decided state | `409` |
| APP-09 | Checklist waiver without rationale | `400` |
| APP-10 | Checklist waiver by reviewer | `200`, audit, finding no longer `FAIL` where rule permits |
| APP-11 | Resubmission after rectification | New versions, new validation run; old run unchanged |
| APP-12 | Category/template activation | Only one active template; old applications keep snapshot |
| APP-13 | Save structured declaration on a draft | `200`, `version` 1 then incremented per save; audit `application.declaration_saved` |
| APP-14 | Save declaration as staff / on a submitted application | `403` / `409 STATE_CONFLICT` |
| APP-15 | Read declaration from another institution | `404`; staff in scope may read it |
| APP-16 | Programmes with duplicate/odd-case codes | Codes upper-cased, trimmed, de-duplicated |

### 6.3 Uploads and storage

| ID | Case | Expected |
|---|---|---|
| UPL-01 | Valid PDF upload | `202`, SHA-256, stored privately, job queued |
| UPL-02 | Valid JPEG/PNG upload | `202` |
| UPL-03 | Executable renamed `.pdf` | `415` (magic bytes) |
| UPL-04 | PDF with JavaScript/embedded files | Rejected or quarantined per policy; no execution |
| UPL-05 | Oversized file | `413` |
| UPL-06 | Empty/truncated file | `415`/`422` |
| UPL-07 | Duplicate content | `409 DUPLICATE_DOCUMENT` |
| UPL-08 | New version of existing document | Version increments; old version immutable |
| UPL-09 | Path traversal filename | Safe randomized key; original name stored only as metadata |
| UPL-10 | Unauthorized upload | `403`/`404`, no object written |
| UPL-11 | DB failure after object write | Object compensated/deleted; no orphan |
| UPL-12 | Idempotent retry with same key | Same response, one document version |
| UPL-13 | Download URL expiry | URL invalid after TTL; access audited |
| UPL-14 | Malware scan (optional) | EICAR test file quarantined; no processing |

### 6.4 Processing and extraction

| ID | Case | Expected |
|---|---|---|
| OCR-01 | Clean PDF, 4 document types | Correct classification and required fields |
| OCR-02 | Rotated/skewed scan | Fields extracted or explicit `LOW_CONFIDENCE` |
| OCR-03 | Unreadable scan | `UNREADABLE`, no fabricated fields |
| OCR-04 | Multi-page PDF | Page refs correct; no cross-page name bleed |
| OCR-05 | Degree certificate | Holder, degree, institution, dates extracted |
| OCR-06 | Affiliation certificate | Institution, validity, authority extracted |
| OCR-07 | Land/lease document | Parties, area, dates extracted |
| OCR-08 | Undertaking | Signatory, date, institution extracted |
| OCR-09 | Conflicting dates across pages | Both retained with page refs; no silent overwrite |
| OCR-10 | Low-confidence field | Confidence below threshold; finding `INCONCLUSIVE` |
| OCR-11 | Reprocess after run | `409` if used by a completed run; new version required |
| OCR-12 | Extraction provenance | Every field has page/bbox/snippet or explicit absence |

### 6.5 Rules and findings (golden cases)

Each rule needs at least `PASS`, `FAIL`, and `NOT_AVAILABLE`/`NOT_APPLICABLE` cases where meaningful.

| Rule code | Scenario | Expected |
|---|---|---|
| `REQ_AFFILIATION` | Missing affiliation certificate | `FAIL`, evidence = checklist item, action = upload |
| `AFFILIATION_EXPIRY` | Certificate expired before submission | `FAIL`, evidence = `valid_until` field |
| `AFFILIATION_EXPIRY` | Valid certificate | `PASS` |
| `REQ_LAND` | Missing land/lease document | `FAIL` |
| `LAND_VALIDITY` | Lease expired | `FAIL` |
| `LAND_AREA` | Area below configured minimum | `FAIL`, evidence = area value + rule config |
| `REQ_FACULTY_DEGREE` | No degree certificate for listed faculty | `FAIL` |
| `FACULTY_QUALIFICATION` | Degree below requirement | `FAIL` |
| `FACULTY_EXPERIENCE` | Experience below minimum | `FAIL` |
| `NAME_CONSISTENCY` | Institution name differs across documents | `FAIL`, both values evidenced |
| `IDENTIFIER_MATCH` | AICTE ID differs from record | `FAIL` |
| `PROGRAMME_INTAKE_MATCH` | Intake differs from approved record | `FAIL` |
| `PREVIOUS_EOA_VALID` | Previous EoA expired | `FAIL` |
| `PREVIOUS_EOA_VALID` | No record | `NOT_AVAILABLE` (never `PASS`) |
| `DEFICIENCIES_UNRESOLVED` | Open deficiency | `FAIL` |
| `TER_STATUS` | TER pending/failed | `FAIL` |
| `TER_STATUS` | No TER record | `NOT_AVAILABLE` |
| `UNDERTAKING_SIGNED` | No signature/date | `FAIL`/`INCONCLUSIVE` |
| `DATE_ORDER` | Lease start after application date | `FAIL` |
| `INFRA_EVIDENCE_PRESENT` | Required photo missing | `FAIL`, action = upload/inspection |
| `DUPLICATE_IDENTIFIER` | Same identifier on different entities | `INCONCLUSIVE` (advisory) |
| `FACULTY_ZKP_ELIGIBILITY` | Valid threshold proof | `PASS` (advisory), evidence = proof ID |
| `QR_SIGNATURE` | Valid QR/signature | `PASS`; source/timestamp recorded |
| `CROSS_DOC_DATE` | Date mismatch across documents | `FAIL`/`INCONCLUSIVE` with both dates |
| `AFFILIATION_DECLARATION_MATCH` | Declared number/date match the extracted certificate | `PASS`, evidence = `DECLARATION` + `EXTRACTED_FIELD` |
| `AFFILIATION_DECLARATION_MATCH` | Declared number/date differ, or no declaration | `FAIL` (advisory) with both values / `NOT_AVAILABLE` |
| `PROGRAMME_DECLARATION_MATCH` | Declared programmes and intake agree with records | `PASS`, evidence includes `RECORD` |
| `PROGRAMME_DECLARATION_MATCH` | Declared programme missing from records, intake differs on a shared code, or declared total inconsistent | `FAIL` (advisory) with `missing_in_records`/`intake_mismatches`/`total_intake_mismatch` |
| `PROGRAMME_DECLARATION_MATCH` | Record has extra programmes not declared | `PASS` (informational only) |
| `FACULTY_COUNT_DECLARATION_MATCH` | Declared count within tolerance of synthetic faculty records | `PASS`; outside tolerance → `FAIL` (advisory) |

**Rule invariants:**

- `FAIL`/`INCONCLUSIVE` always include explanation, evidence, and recommended action.
- `NOT_AVAILABLE` is never rendered as success.
- Rule outcomes are deterministic for identical snapshots and rule versions.
- No rule reads the network during evaluation.
- Thresholds come from rule config, never code.
- Declaration-consistency rules never auto-reject: they return `NOT_AVAILABLE` (never `PASS`) when either side of the comparison is missing, and a mismatch is an advisory `FAIL` for human review.

### 6.6 Institutional records and snapshots

| ID | Case | Expected |
|---|---|---|
| REC-01 | Fetch bundle | Records returned with `source`, `synthetic`, `retrieved_at` |
| REC-02 | Snapshot immutability | Re-running validation creates a new snapshot; old unchanged |
| REC-03 | Snapshot checksum | Recomputation matches |
| REC-04 | Source unavailable | `NOT_AVAILABLE` findings; alert; no pass |
| REC-05 | TER record absent | `TER_STATUS = NOT_AVAILABLE` |
| REC-06 | Programme mismatch | `FAIL` with both records |
| REC-07 | Deficiency open | `FAIL` with deficiency code/status |
| REC-08 | Applicant reads raw records | Denied |

### 6.7 Issuer verification

| ID | Case | Expected |
|---|---|---|
| ISS-01 | Simulated `VERIFIED` | `VERIFIED`, `simulated: true`, source/time recorded |
| ISS-02 | Simulated `MISMATCH` | `MISMATCH`, field-level comparison |
| ISS-03 | Simulated `EXPIRED` | `EXPIRED` |
| ISS-04 | Adapter unavailable | `SOURCE_UNAVAILABLE`; no exception to client |
| ISS-05 | Inconclusive | `MANUAL_REVIEW` |
| ISS-06 | Pending retry | `PENDING`; worker retries with backoff |
| ISS-07 | Unknown adapter | `400`/`404` |
| ISS-08 | Response schema violation | Adapter result rejected; `MANUAL_REVIEW` |
| ISS-09 | QR/signature valid | `VERIFIED`, cryptographic result recorded |
| ISS-10 | QR/signature invalid | `MISMATCH`/`MANUAL_REVIEW`; no authenticity claim |
| ISS-11 | Simulated label propagation | API + UI show simulated badge |
| ISS-12 | Live DigiLocker absent | Capability `available: false`, reason recorded |

M3 adds an **advisory** technical inspection. It does not satisfy ISS-09/ISS-10 (which require cryptographic source verification); the implemented expectations are:

| ID | Case | Expected |
|---|---|---|
| ISS-13 | Unsigned PDF | `qr-payload` → `NOT_FOUND`/`NO_QR_DETECTED`; `pdf-signature` → `NOT_FOUND`/`NO_PDF_SIGNATURE`; advisory flags set |
| ISS-14 | PDF with signature structure and valid byte-range coverage | `pdf-signature` → `SOURCE_UNAVAILABLE`/`PDF_SIGNATURE_PRESENT_UNVERIFIED`; `cryptographically_verified: false`, `trust_chain_checked: false` |
| ISS-15 | Signature byte range out of bounds/discontiguous | `MISMATCH`/`PDF_SIGNATURE_COVERAGE_INCOMPLETE`; advisory wording, not an alteration claim |
| ISS-16 | QR payload detected | `SOURCE_UNAVAILABLE`/`QR_PAYLOAD_DETECTED_UNVERIFIED`; payload preview/digest/host recorded, `not_fetched: true`, no external request |
| ISS-17 | QR decoder unavailable | `SOURCE_UNAVAILABLE`/`QR_DECODER_UNAVAILABLE`; message states deployment limitation |
| ISS-18 | Applicant or unsupported media type | Applicant `403`; non-PDF/image version `400 UNSUPPORTED_MEDIA_TYPE`; overview shows newest inspection per adapter |

### 6.8 Anomalies

| ID | Case | Expected |
|---|---|---|
| ANOM-01 | Exact duplicate | `DUPLICATE_EXACT`, evidence = both versions |
| ANOM-02 | Perceptual duplicate (resized) | `DUPLICATE_PERCEPTUAL` with score |
| ANOM-03 | Metadata editor | `METADATA_EDITOR`, producer evidence |
| ANOM-04 | Font inconsistency | Signal with page/font evidence |
| ANOM-05 | Identifier mismatch | Signal + link to records |
| ANOM-06 | Future/irregular date | `DATE_ANOMALY` with both dates |
| ANOM-07 | Clean document | No high-severity signal |
| ANOM-08 | Wording | Never “forged”, “fake”, or “authentic”; always “preliminary indicator” |
| ANOM-09 | Score not proof | UI/API disclaimer present |
| ANOM-10 | Method version | Each signal records `method_version` |

### 6.9 Infrastructure evidence

| ID | Case | Expected |
|---|---|---|
| INF-01 | Required photo present | `PRESENT`; no compliance conclusion |
| INF-02 | Missing photo | `FAIL`/`INSUFFICIENT`; recommend upload/inspection |
| INF-03 | Video/floor plan | Stored and mapped; metadata only |
| INF-04 | Capture date old | Advisory finding; no automatic rejection |
| INF-05 | Reviewer marks insufficient | Rationale required; audit |
| INF-06 | CV not implemented | No fabricated visual finding; limitation shown |

### 6.10 ZKP (critical)

| ID | Case | Expected |
|---|---|---|
| ZKP-01 | Honest proof, value ≥ threshold | `VERIFIED` |
| ZKP-02 | Value < threshold | Witness generation fails; no proof accepted |
| ZKP-03 | Boundary equality | `VERIFIED` (GTE semantics) |
| ZKP-04 | Tampered public signal | `REJECTED` |
| ZKP-05 | Threshold mismatch | `REJECTED THRESHOLD_MISMATCH` |
| ZKP-06 | Request hash mismatch | `REJECTED REQUEST_HASH_MISMATCH` |
| ZKP-07 | Commitment mismatch | `REJECTED COMMITMENT_MISMATCH` |
| ZKP-08 | Replayed nullifier | `REJECTED NULLIFIER_REUSED` |
| ZKP-09 | Expired request | `REJECTED REQUEST_EXPIRED` |
| ZKP-10 | Wrong circuit/vkey | `REJECTED VKEY_UNKNOWN`/`PROOF_INVALID` |
| ZKP-11 | Malformed proof JSON | `400`, no verifier crash |
| ZKP-12 | Proof for another credential | `REJECTED COMMITMENT_MISMATCH` |
| ZKP-13 | Private value in API/logs/chain | Absent (grep + response inspection) |
| ZKP-14 | Nullifier determinism | Same credential/value/request context yields expected deterministic nullifier per design |
| ZKP-15 | Concurrent duplicate submissions | Exactly one `VERIFIED`; other `409`/`REJECTED` |
| ZKP-16 | Verifier unavailable | `503 VERIFIER_UNAVAILABLE`; request remains `PENDING` |
| ZKP-17 | Vkey pinning | Verifier loads only configured vkey ID; path traversal rejected |
| ZKP-18 | Circuit soundness regression | `circom` constraints reject under-threshold witness (CI gate) |

### 6.11 Blockchain anchoring

| ID | Case | Expected |
|---|---|---|
| CHN-01 | Anchor document hash | `CONFIRMED`, tx/block recorded |
| CHN-02 | Anchor credential/proof | `CONFIRMED`, correct event |
| CHN-03 | Unauthorized signer | Reverted by `AccessControl` |
| CHN-04 | Revoke as authorized role | Revoked event; status `REVOKED` |
| CHN-05 | Revoke as unauthorized role | Revert |
| CHN-06 | Duplicate anchor | Idempotent local row; no duplicate tx |
| CHN-07 | Chain unavailable | Business flow completes; anchor `FAILED`/`PENDING`; alert |
| CHN-08 | Retry failed anchor | New tx; row updated |
| CHN-09 | Hash-only payload | No PII/commitment secret on chain |
| CHN-10 | Confirmation tracking | Confirmations counted; stale pending retried |
| CHN-11 | Verify hash match | `on_chain_match: true` + mandatory disclaimer |
| CHN-12 | Tampered local hash | Mismatch detected |

### 6.12 Review, alerts, decisions, audit

| ID | Case | Expected |
|---|---|---|
| REV-01 | Queue filters and scoping | Correct subset; no cross-institution leakage |
| REV-02 | Assign reviewer | Audited; notification/alert |
| REV-03 | Request rectification | Status transition + alert; rationale required |
| REV-04 | Applicant response | `RESUBMITTED`; new validation run |
| REV-05 | Approver decision | Final, unique, audited |
| REV-06 | Duplicate decision | `409` |
| REV-07 | Non-approver decision | `403` |
| ALR-01 | Finding raises alert | One alert per `(application_id, alert_type, source_ref)` |
| ALR-02 | Revalidation | No duplicate alert |
| ALR-03 | Acknowledge/resolve | Actor/time recorded; audit |
| ALR-04 | Alert timeliness | Measured (§9) |
| ALR-05 | Resolve with disposition | Disposition + note stored in `payload`, exposed as `AlertOut.disposition`, written to `alert.resolved`; `FALSE_POSITIVE`/`ACCEPTED_RISK` without a note → `400 VALIDATION_FAILED`; unknown value → `400` |
| ALR-06 | Alert detail scope | `GET /alerts/{id}` staff-only; `404` for an alert whose application is outside the caller's scope; `404` for an unknown ID; `403` for applicants |
| ALR-07 | Stale alert supersede | A finding/anomaly alert whose `source_ref` is absent from the newest run becomes `RESOLVED`/`SUPERSEDED` with `resolved_by = null` and an `alert.superseded` audit event; rectification/escalation alerts are untouched |
| ALR-08 | Disposition does not decide | Recording any disposition leaves finding outcomes, application status, and decisions unchanged |
| AUD-01 | State change writes audit | 100% coverage |
| AUD-02 | Hash chain valid | `valid: true` |
| AUD-03 | Tampered event | Verification fails at correct seq |
| AUD-04 | Concurrent writes | Chain order preserved; no forks |
| AUD-05 | Applicant audit scope | Own events only |
| AUD-06 | Audit export | JSONL hashes verify |
| AUD-07 | Redaction | No tokens/passwords/document text in audit |

### 6.13 Reports and explainability

The implemented export is `GET /applications/{id}/report?format=json|markdown|html` (see §14.13). There is no PDF renderer, no queued export job, and no signed artefact.

| ID | Case | Expected |
|---|---|---|
| RPT-01 | JSON report | Matches the latest run/findings; carries `report_version`, limitations, audit chain state |
| RPT-02 | Markdown/HTML report | Same data as JSON; HTML self-contained and escaped; no `<script>` passthrough |
| RPT-03 | Evidence coverage | Every `FAIL`/`INCONCLUSIVE` finding carries its evidence rows |
| RPT-04 | Wording audit | No conclusive forgery/authenticity language; limitations present in every format |
| RPT-05 | Synthetic labels | Report states issuer/record data is synthetic; declaration labelled applicant-supplied and unverified |
| RPT-06 | Export access | Staff-only (`403` for applicants); every export writes `application.report_exported`; response is an attachment |
| RPT-07 | Unsupported format | `format=pdf` → `400 VALIDATION_FAILED` (not silently downgraded) |
| RPT-08 | Not executed | PDF generation, signatures, presigned download URLs (§14.16) |

### 6.14 Pre-submission self-check

`GET /applications/{id}/self-check` is read-only (no validation run, no alerts, no audit event) and only available for `DRAFT`/`RECTIFICATION_REQUESTED`.

| ID | Case | Expected |
|---|---|---|
| SC-01 | Blocking parity with submit | Blocking codes are exactly the checklist items `submit` would reject; after satisfying them `can_submit` flips to `true` and that same submit returns `200` |
| SC-02 | No side effects | Repeated calls write zero audit events and create no alerts/validation runs |
| SC-03 | Declaration tracking | `DECLARATION_MISSING` → `DECLARATION_INCOMPLETE` (with the missing fields listed) → `DECLARATION_PRESENT`; the present message says the declaration is not verified |
| SC-04 | State gate | `409 STATE_CONFLICT` once the application is submitted |
| SC-05 | Scope | Another institution's applicant gets `404` |
| SC-06 | Advisory findings | Latest-run findings appear as `WARNING` with rule codes, do not set `can_submit = false`, and the check does not re-run the rule engine |

---

## 7. Security test cases

| ID | Case | Expected |
|---|---|---|
| SEC-01 | JWT `alg: none` / algorithm confusion | Rejected |
| SEC-02 | Expired/revoked token | Rejected |
| SEC-03 | Refresh token reuse | Family revoked; `security_event` |
| SEC-04 | IDOR across institutions/applications/documents/records | `404`/`403`; no data in body |
| SEC-05 | Mass assignment (`role`, `status`, `synthetic`) | Ignored/rejected |
| SEC-06 | Upload polyglot/zip bomb/PDF bomb | Rejected safely; bounded CPU/memory |
| SEC-07 | SSRF via adapter config | No user-supplied URLs; allowlist |
| SEC-08 | Prompt injection in document text | No tool execution; no policy override; finding unaffected |
| SEC-09 | Log injection/redaction | Structured logs; secrets absent |
| SEC-10 | CORS | Explicit origin allowlist (not `*`) |
| SEC-11 | Rate limits | Enforced with `Retry-After` |
| SEC-12 | Secret scan | No committed secrets; `.env.example` only |
| SEC-13 | Dependency audit | No known critical/high vulnerabilities in runtime deps (report actuals) |
| SEC-14 | Container scan | No critical/high image findings (report actuals) |
| SEC-15 | Synthetic label spoofing | Client cannot set `synthetic`/`simulated` |
| SEC-16 | Chain signer key exposure | Key only via env/secret store; not logged |
| SEC-17 | Audit tampering via DB role | App role lacks `UPDATE`/`DELETE` on audit |
| SEC-18 | Presigned URL leakage | Short TTL; scoped; audited |

---

## 8. Performance and reliability targets

Targets are provisional for the demo environment (single host, Compose):

| Metric | Target |
|---|---|
| Read API p95 | < 300 ms |
| Write API p95 (excluding async work) | < 800 ms |
| 10-page PDF processing p95 | < 30 s |
| Validation run (≤ 25 rules) p95 | < 5 s |
| Submit → validation complete median | < 60 s |
| Submit → validation complete p95 | < 180 s |
| Alert creation p95 after finding | < 60 s |
| Server ZKP verification p95 | < 1.5 s |
| Browser proof generation (reference laptop) | < 10 s |
| Job queue lag p95 | < 10 s |
| Concurrent users (smoke) | 50 with < 1% errors |
| Recovery after adapter/chain outage | No data loss; visible status; retry succeeds |

Load tests must use synthetic data and must not target real issuer/AICTE endpoints.

---

## 9. Evaluation metrics (official requirements)

These are the metrics the prototype must report. **No metric may be claimed without a reproducible run and an artifact.**

### 9.1 Definitions and procedure

| Metric | Definition | Procedure |
|---|---|---|
| Extraction accuracy | Per-field precision/recall/F1 after normalization (exact match) | Run extractors on DS-1; compare to golden labels; report micro + macro and per field |
| Classification accuracy | Correct document type / total | DS-1 confusion matrix |
| Validation accuracy | Finding outcome equals golden outcome for each rule-case | DS-2 + DS-3; exact match; report false-pass rate separately |
| Anomaly performance | Precision/recall/F1 by anomaly type | DS-4; threshold fixed before evaluation; report confusion matrix |
| Source-verification success rate | `VERIFIED` / eligible documents with a configured source | Simulated adapters; report by adapter; status correctness separately |
| Discrepancy-identification reliability | Correctly identified discrepancies / golden discrepancies | DS-2; precision and recall; include evidence correctness |
| Average verification time | Submit → completed validation; also upload → processed | Timestamps from DB; median and p95 |
| Alert timeliness | Finding/transition created → alert created | DB timestamps; p95 |
| Manual-effort reduction | Steps/time on scripted tasks with vs without the platform | 10 synthetic cases; same operator; report as a local proxy, not a production claim |
| Evidence coverage | Findings with required evidence / findings requiring evidence | Must be 100% |
| Audit coverage | State-changing actions with audit event / total | Must be 100% |

### 9.2 MVP targets

| Metric | Target | Notes |
|---|---|---|
| Extraction macro F1 (key fields) | ≥ 0.85 | Critical fields (dates, IDs, names): recall ≥ 0.90 |
| Classification accuracy | ≥ 0.95 | 4 types |
| Rule outcome accuracy | 100% on deterministic golden cases | False-pass rate 0 on critical rules |
| Anomaly precision | ≥ 0.80 | Synthetic set; report actual |
| Anomaly recall | ≥ 0.70 | Synthetic set; report actual |
| Discrepancy precision/recall | ≥ 0.80 each | Includes evidence match |
| Source-verification status correctness | 100% | Simulated adapters |
| Evidence coverage | 100% | Enforced by schema + tests |
| Audit coverage | 100% | Enforced by tests |
| Median verification time | ≤ 60 s | 10-page docs, ≤ 25 rules |
| p95 verification time | ≤ 180 s | Demo hardware |
| Alert p95 | ≤ 60 s | From finding creation |
| Manual-effort proxy | ≥ 30% fewer steps/time | Report measured value; do not generalize |

Targets may be revised **before** measurement if the corpus or environment changes; revisions must be documented with rationale. Results are reported with dataset size, environment, commit SHA, and date.

### 9.3 Reporting template

```
Run: <date> <commit>
Dataset: DS-1 vX (N=60), DS-2 vX (N=20), ...
Environment: <CPU/RAM/OS, Docker versions>
Extraction: micro P/R/F1 = ...; macro = ...; per-field table attached
Classification: accuracy = ...; confusion matrix attached
Rules: cases = ...; accuracy = ...; false-pass = ...
Anomalies: precision = ...; recall = ...; F1 = ...
Verification: eligible = ...; verified = ...; status correctness = ...
Timing: median = ...; p95 = ...
Alerts: p95 = ...
Manual effort: steps/time baseline vs platform = ...
Limitations: ...
```

### 9.4 Advisory safety metrics

These are measured by `evaluation/run_evaluation.py` (section `advisory_controls`) and are pass/fail, not accuracy statistics. They exist to keep advisory features from drifting into claims.

| Control | Definition | Expected |
|---|---|---|
| Submission-gate parity | `self-check.can_submit` equals whether `POST /submit` is accepted, before and after evidence | 100% |
| Preview side-effect freedom | Audit event count around repeated self-check calls | Unchanged |
| Declaration consistency labels | Supplied → `PASS`, absent → `NOT_AVAILABLE`, mismatched → `FAIL` | 100% |
| Inspection non-commitment | No technical-inspection row reports `VERIFIED`; QR/signature checks record `external_lookup_performed=false` and `cryptographically_verified=false` | 100% |
| Report format parity | JSON/Markdown/HTML exported as attachments and each repeats the limitations | 100% |
| Report claim safety | No claim-shaped phrase (`is forged`, `is authentic`, `officially verified`, …) in any exported format | 100% |
| Export auditability | One `application.report_exported` event per successful export | 100% |
| Disposition gating | Dismissive dispositions require a note; unknown dispositions rejected; recorded disposition does not change findings | 100% |
| Stale alert supersede | Alerts whose source is absent from the newest run resolve as `SUPERSEDED` with no human actor | 100% |

---

## 10. CI pipeline

**No CI pipeline is configured in the repository.** The table is a target design, not an executed pipeline. Commands actually run are in §14.

| Stage | Commands (target) | Gate |
|---|---|---|
| Lint | `ruff check`, `ruff format --check`, `npm run lint` (config added) | Required |
| Type check | `mypy app` (strict on new modules), `tsc --noEmit` | Required |
| Unit/integration | `pytest -q` with PostgreSQL service | Required |
| API contract | `pytest tests/contract`, OpenAPI diff | Required |
| Frontend | `npm run build`, component tests | Required |
| E2E | `docker compose up -d` + `npx playwright test` | Required |
| Contracts | `npx hardhat test` | Required |
| Circuits | `circom` build + `snarkjs` verify + negative witness tests | Required when circuits change |
| Security | `bandit`, `pip-audit`, `npm audit --omit=dev`, `gitleaks`, `trivy` | Required (report actuals) |
| Evaluation | `python -m evaluation.run --dataset ...` | Nightly/manual; required before claims |

CI must not use real AICTE/issuer credentials. Chain tests use Hardhat only.

---

## 11. Phase exit criteria

| Phase | Test evidence required |
|---|---|
| 3 | Auth matrix, application lifecycle, upload/storage, migrations, object-level authorization |
| 4 | Processing success/failure states, provenance, extraction baseline on DS-1 |
| 5 | Golden rule cases (100% deterministic), snapshots, `NOT_AVAILABLE`, rectification/revalidation |
| 6 | Issuer statuses + simulated labels, ZKP positive/negative/soundness, chain ACL/revoke/retry/outage |
| 7 | Anomaly metrics on DS-4, evidence coverage, infrastructure evidence workflow, wording tests |
| 8 | Review/alerts/decisions E2E, audit chain integrity/concurrency, historical explainability |
| 9 | Security suite, upload hardening, secret scan, log redaction, retention |
| 10 | Full E2E on synthetic dataset, evaluation report with actual metrics, limitations |
| 11 | Reproducible demo script, seeded data, simulated disclosures, claim audit |

A phase is not complete if a required test is skipped, flaky, or only manually observed without an artifact.

---

## 12. Defect severity and release blocking

| Severity | Examples | Release impact |
|---|---|---|
| Critical | Auth bypass, cross-tenant data leak, proof forgery accepted, audit chain broken, PII on chain | Blocks release |
| High | False `PASS` on a critical rule, missing evidence for `FAIL`, unsigned/mislabeled issuer result, upload RCE | Blocks release |
| Medium | Incorrect non-critical extraction, alert duplication, UI state mismatch | Fix before demo if feasible |
| Low | Copy/layout issues, non-blocking warnings | Backlog |

Findings/false positives from AI components are **not** defects by themselves unless they violate evidence/labeling rules.

---

## 13. Risks and limitations of this plan

1. **Synthetic corpus bias.** Metrics on generated documents may not generalize to real AICTE scans. Report as synthetic-only.
2. **No real issuer/AICTE access.** Verification success is measured against simulated adapters; it does not demonstrate live integration.
3. **OCR variability.** Tesseract accuracy depends on scan quality; results must include per-field confidence and failure rates.
4. **ZKP ceremony.** Demo keys are not production-trusted; the test verifies soundness/replay resistance, not ceremony integrity.
5. **Manual-effort metric.** A small scripted study is a proxy, not a controlled productivity trial.
6. **Performance on demo hardware.** Targets are environment-specific and must be reported with hardware details.
7. **Anomaly ground truth.** Labels are synthetic and may encode the same heuristics used by the detector; use held-out and adversarial cases.

---

## 14. Executed results (2026-10-24, partially re-run 2026-10-25)

The 2026-10-24 results below were produced on Linux. Sections 14.1, 14.3, 14.6 and 14.7 were re-run on 2026-10-25 on Windows/Python 3.10 after adding evidence page geometry, the legacy API gate, the evidence workspace, and the structured declaration; see 14.9–14.11 for what changed and 14.10 for the HTTP smoke check.

### 14.1 Backend automated suite

Command (from `backend/`): `./venv/bin/pytest` (Windows: `.\venv\Scripts\python.exe -m pytest -q`)

**Result: 67 passed, 2 warnings, exit code 0** (2026-10-25, after M2; supersedes the 61/63-pass runs). Requires PostgreSQL `astra_test`, local storage, and `circuits/node_modules` for the ZKP suite.

| Suite | Tests | Coverage |
|---|---:|---|
| `test_phase3_applications.py` | 9 | lifecycle, checklist, submit gate, isolation |
| `test_phase3_auth.py` | 7 | login, refresh rotation, revocation, password change |
| `test_phase3_documents.py` | 7 | upload, validation, versions, signed download |
| `test_phase3_records_admin.py` | 3 | synthetic records, admin provisioning |
| `test_phase4_extraction.py` | 4 | extraction states, provenance, reprocess |
| `test_phase5_validation.py` | 5 | rule versions, findings, snapshots, rectification |
| `test_phase6_issuer.py` | 5 | Ed25519 verify, revocation, external unavailable |
| `test_phase7_assurance.py` | 4 | duplicates, anomalies, infrastructure presence |
| `test_phase8_review_audit.py` | 4 | assignment, rectification, decisions, audit chain |
| `test_phase9_security.py` | 7 | authz isolation, upload hardening, secrets, headers, injection sentinel |
| `test_phase10_zkp.py` | 5 | proof success, expiry, tamper, replay, authorization |
| `test_phase10_e2e.py` | 1 | full submit → validation → ZKP → review → decision → audit |
| `test_phase11_declarations.py` | 4 | declaration CRUD/versioning/audit, all-PASS consistency, advisory mismatches, `NOT_AVAILABLE` |
| `test_legacy_attestation.py` | 2 | demo Ed25519 attestation verifies; tampering rejected (added 2026-10-25) |

### 14.2 Legacy smoke scripts

| Command (from `backend/`) | Result |
|---|---|
| `./venv/bin/python test_backend.py` | Passed (import smoke test) |
| `./venv/bin/python test_api_endpoints.py` | Passed (legacy demo flow) |

**Caveat:** the legacy `validate-zk` path still does not verify proofs. The new `/api/v1/zkp` flow is tested separately and fails closed; do not treat the legacy script as a security test.

### 14.3 Database migrations

Commands used `DATABASE_URL=.../astra_migrate` and the test secrets.

| Check | Result |
|---|---|
| `alembic upgrade head` | Passed |
| `alembic downgrade -1` ×2 (`zk_challenges`, `zk_proofs`) | Passed |
| `alembic upgrade head` | Passed |
| `alembic current` | `c3d5e7f9a1b2 (head)` — structured declarations added 2026-10-25 |
| `alembic upgrade head` on `astra` | Applied `b7f1c9a2d4e0 -> c3d5e7f9a1b2` |
| `alembic downgrade -1` / `upgrade head` on `astra_test` | Passed (round-trip of `c3d5e7f9a1b2`) |
| `extracted_fields.page_width/page_height` present | `numeric(10,3)`, nullable |
| `application_declarations` present | Unique `application_id`; non-negative intake/faculty checks; cascade delete |

### 14.4 Contracts

Command (from `blockchain/`): `npx hardhat test`

**Result: 5 passed.** Covers access control, payload anchoring, nullifier reuse, and failed proof verification. `npx hardhat compile` succeeded.

### 14.5 Circuit and live anchoring

| Check | Result |
|---|---|
| `./build_faculty_threshold.sh` | Circuit, witness generator, zkey, vkey generated with circom 2.2.3/snarkjs |
| Manual Groth16 prove/verify | Valid proof accepted; tampered signal rejected |
| Live backend `verifyAndAnchor` against local Hardhat | `chain_status=ANCHORED`, real tx hash persisted |
| Deployment addresses (local) | `FacultyThresholdVerifier=0x5FbDB2315678afecb367f032d93F642f64180aa3`, `AstraVerifyAnchorV2=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512` |

The live test used a synthetic application in `astra_evaluation`; it is a manual integration check, not part of pytest.

### 14.6 Frontend

| Check | Result |
|---|---|
| `npm --prefix frontend run build` | Succeeded (2026-10-24); re-run 2026-10-25 after the evidence workspace, see 14.9 |
| `/compliance` browser interaction | **Not tested** in a browser automation run |
| `npm run lint` | Not runnable; no ESLint config |

### 14.7 Synthetic evaluation

Command: `./venv/bin/python evaluation/run_evaluation.py` (dedicated `astra_evaluation` DB).

| Metric | Result |
|---|---|
| OCR field exact match | 100/100 across 20 synthetic documents |
| OCR processing time | 2026-10-24: median 43.94 ms, p95 47.66 ms, max 73.15 ms; 2026-10-25 re-run: median 81.75 ms, p95 96.69 ms, max 207.9 ms |
| Rule outcomes | 48/48 across 4 rule cases × 12 rules (2026-10-25; was 27/27 across 3 × 9) |
| Declaration cases | matching declaration → all 12 `PASS`; declaration mismatch → all three consistency rules `FAIL` |
| Anomaly precision / recall | 1.0 / 1.0 over 3 synthetic applications |
| Issuer scenarios | 3/3 |
| Disclaimer | Synthetic corpus only; not AICTE accuracy evidence |

### 14.9 Re-run 2026-10-25 (Windows, Python 3.10)

Re-run after the evidence-geometry migration, the legacy API gate, the OCR-unavailable state, and the `/compliance` evidence workspace.

| Check | Result |
|---|---|
| `backend/venv/Scripts/python.exe -m pytest -q` | **63 passed, 2 warnings, exit code 0** |
| ZKP suite with `circuits/node_modules` installed | 5 passed (test harness now resolves `snarkjs.cmd`) |
| Anchoring tests with `BLOCKCHAIN_ENABLED=true` in a developer `.env` | Passed — `tests/conftest.py` forces both blockchain flags to `false` |
| Blank/scanned page without Tesseract | `status=FAILED`, `error_code=OCR_ENGINE_UNAVAILABLE` (accepted by the test alongside `UNREADABLE`/`NO_TEXT`) |
| `alembic upgrade head` on `astra` | Passed; head `b7f1c9a2d4e0` |
| `alembic downgrade -1` then `upgrade head` on `astra_test` | Passed |
| `npm --prefix frontend run build` | Succeeded; `pdf-*.js` (365 kB) and the PDF worker are separate lazy chunks, not in the initial bundle |
| `git diff` review of test-facing changes | Reviewed; test assertions for page geometry, evidence metadata, and document MIME/filename added |

Environment caveats found during the re-run (recorded, not fixed):
- `requirements.txt` pins `SQLAlchemy==2.1.6` (requires Python >= 3.11) while the committed venv is Python 3.10 with SQLAlchemy 2.0.55. `pip install -r requirements*.txt` fails; pytest 8.4.2 was installed separately.
- Tesseract is not installed on this machine, so OCR fallback behaviour was exercised only through the unavailable-engine path.
- `frontend/src/components/compliance/DocumentViewer.jsx` used `TriangleAlert`, which `lucide-react@0.344` does not export; corrected to `AlertTriangle` before the build passed.

### 14.10 HTTP smoke check of the evidence path (2026-10-25)

Manual script (not part of the suite) driving a running local server against the dev database: login as applicant and reviewer, create an application, upload a synthetic PDF for every required checklist item, submit, fetch `review-overview`, then follow a signed download.

| Observed | Result |
|---|---|
| `POST /applications` | Created in a free cycle (a second application in the same cycle is rejected `409`) |
| Uploads | 4 documents, `original_filename` and `mime_type` present in `review-overview` |
| Validation | 9 findings produced |
| Evidence with boxes | 4, each with `page=1`, `bbox`, `page_width=595`, `page_height=842` |
| `POST /document-versions/{id}/download-url` + follow | `200`, 1846 bytes, body starts with `%PDF` |

**Not implied:** this is one synthetic path over HTTP. It does not verify browser rendering of the overlays, PDF page-fit accuracy, or any authenticity claim; the overlays are a review aid only.

### 14.11 M2 re-run (2026-10-25, Windows/Python 3.10)

Re-run after adding the structured declaration, the three declaration-consistency rules, the rule-set versioning, and `/compliance` declaration form.

| Check | Result |
|---|---|
| `backend/venv/Scripts/python.exe -m pytest -q` | **67 passed, 2 warnings, exit code 0** |
| `test_phase11_declarations.py` | 4 passed (CRUD/versioning/draft lock/audit; all-12 PASS; advisory mismatches + review-overview; `NOT_AVAILABLE`) |
| `test_phase5_validation.py` | Updated expectations: 12 rules, 9 `PASS` + 3 `NOT_AVAILABLE` without a declaration |
| `test_phase10_e2e.py` | Outcome-set assertion now uses the real enum values (includes `NOT_AVAILABLE`) |
| `alembic upgrade head` on `astra` | Applied `c3d5e7f9a1b2`; `alembic current` reports `c3d5e7f9a1b2 (head)` |
| `astra_test` downgrade/upgrade of `c3d5e7f9a1b2` | Passed |
| Seeder run twice on `astra` | v1 `ARCHIVED` (9 rules) + v2 `ACTIVE` (12 rules); second run idempotent |
| `evaluation/run_evaluation.py` | 4 cases, 48/48 labels, `rule_outcome_accuracy 1.0`, OCR 100/100, median 81.75 ms, total 7.44 s |
| `npm --prefix frontend run build` | Succeeded; `index-CzXz8Ihd.js` 820.45 kB, PDF renderer/worker still lazy chunks |
| `git diff` review | Reviewed; no unrelated files modified by this change |

### 14.12 M3 re-run (2026-10-25, Windows/Python 3.10)

Re-run after adding advisory QR decoding and PDF signature-structure inspection (`POST /document-versions/{id}/technical-verifications`, `review-overview.technical_verifications`, `/compliance` technical inspection panel). No schema change; migration head remains `c3d5e7f9a1b2`.

| Check | Result |
|---|---|
| `backend/venv/Scripts/python.exe -m pytest -q --junit-xml=test-all-m3.xml` | **73 tests, 0 failures, 0 errors, 0 skipped, 105.07 s, exit code 0** |
| `test_phase12_technical_verification.py` | 6 passed (unsigned PDF states; embedded-signature present-unverified; invalid byte-range mismatch; QR payload recorded but not fetched; decoder-unavailable state; permissions, unsupported media type, latest-per-adapter overview, audit events) |
| QR decoder | Real OpenCV path exercised by the unsigned-PDF case (no payload); payload and unavailable paths are deterministic via monkeypatch |
| `npm --prefix frontend run build` | Succeeded; `index-3OHe_siU.js` 826.88 kB, PDF renderer/worker still lazy chunks |
| `alembic current` | Unchanged at `c3d5e7f9a1b2 (head)`; no migration added |

**Not implied:** a detected signature structure is not a verified signature; a detected QR payload is not a resolved issuer response. Neither result supports an authenticity claim, and browser rendering of the new panel has not been automated.

### 14.13 M4/M5 re-run (2026-10-25, Windows/Python 3.10)

First run of the advisory report export, alert dispositions, and pre-submission self-check (`test_phase13_report_and_alerts.py`, `test_phase14_self_check.py`). No schema change; migration head remains `c3d5e7f9a1b2`.

| Check | Result |
|---|---|
| `backend/venv/Scripts/python.exe -m pytest -q --junit-xml=test-m4-m5.xml` | **86 tests, 0 failures, 0 errors, 0 skipped, 82.16 s, exit code 0** |
| `test_phase13_report_and_alerts.py` | 6 passed (JSON/Markdown/HTML exports, advisory limitations, attachment headers, export audit events, applicant `403`, unsupported format `400`, HTML escaping; disposition note rules and `alert.resolved` payload; alert detail scope `404`/`403`; stale-alert supersede with system-actor audit) |
| `test_phase14_self_check.py` | 7 passed (blocking parity with submit then clearing; no audit writes on repeated calls; declaration missing/incomplete/present; `409` after submit; other-institution `404`; latest findings as advisory warnings; a failed document outside the checklist gate is a warning and `can_submit` still matches `submit`) |
| `npm --prefix frontend run build` | Succeeded; `index-DOTEMLQV.js` 838.84 kB, `pdf-BnPRJEQ6.js` 365.12 kB lazy chunk; only the pre-existing >500 kB warning |
| `alembic current` | Unchanged at `c3d5e7f9a1b2 (head)`; no migration added |

**Not implied:** the report is an advisory review aid and is not signed, official, or a decision. A recorded disposition is human judgement only and never changes a finding outcome. The self-check previews the submission gate; it does not predict approval, does not verify the declaration, and does not run the rule engine. `/compliance` rendering of the new alert and self-check panels was build-verified, not browser-automated.

### 14.14 M6 demo hardening (2026-10-25, Windows/Python 3.10)

Added the scripted live walkthrough (`backend/scripts/demo_smoke.py`), the demo runbook (`docs/DEMO_RUNBOOK.md`), an advisory-controls section in the evaluation harness, and a dependency-pin reconciliation. No application-behaviour change, no schema change; migration head remains `c3d5e7f9a1b2`.

| Check | Result |
|---|---|
| `backend/venv/Scripts/python.exe -m pytest -q --junit-xml=test-m6.xml` | **86 tests, 0 failures, 0 errors, 0 skipped, 171.64 s** (same suite as §14.13; no test was added or changed in M6) |
| `backend/venv/Scripts/python.exe evaluation/run_evaluation.py` | OCR 100/100 fields (median 104.21 ms, p95 128.18 ms); rules 48/48; declaration consistency 12/12; anomalies precision 1.0 recall 1.0; issuer 3/3; **advisory controls 39/39**; runtime 14.0 s |
| `backend/venv/Scripts/python.exe scripts/demo_smoke.py` against a live uvicorn on `http://localhost:8000` | **44/44 steps passed** (recorded in §14.15) |
| `pip install --dry-run --no-deps "SQLAlchemy>=2.0.55,<2.1"` | Already satisfied by the committed venv (2.0.55); the previous pin (`2.1.6`) needed Python ≥ 3.11 and blocked `pip install -r requirements.txt` on 3.10 |
| `npm --prefix frontend run build` | Succeeded before and after M6 (no frontend source changed in M6) |

**Not implied:** the walkthrough proves the local prototype flow responds correctly to synthetic input. It is not a browser test, not a penetration test, and not evidence of AICTE readiness. The evaluation metrics describe a synthetic corpus only.

### 14.15 Live smoke walkthrough (2026-10-25)

Recorded output of `backend/scripts/demo_smoke.py` against a local uvicorn server (dev database `astra`, application cycles `2099-07`/`2099-08`, exit code 0):

```text
Smoke walkthrough against http://localhost:8000

[PASS] health - 200
[PASS] login applicant@example.test - access token issued
[PASS] login reviewer@example.test - access token issued
[PASS] create application - APP-2099-000007 (cycle 2099-07)
[PASS] self-check before evidence - 200
[PASS] self-check blocks an empty application - blocking=4, can_submit=False
[PASS] submit is refused while evidence is missing - 400 VALIDATION_FAILED
[PASS] read checklist - 200
[PASS] upload AFFILIATION_CERTIFICATE - 202
[PASS] upload LAND_LEASE_DOCUMENT - 202
[PASS] upload FACULTY_DEGREE_CERTIFICATE - 202
[PASS] upload INSTITUTIONAL_UNDERTAKING - 202
[PASS] save structured declaration - 200
[PASS] self-check after evidence - 200
[PASS] self-check now allows submission - blocking=0, warnings=0
[PASS] submit - 200
[PASS] validation run started - 83f9ef8a-17a4-4a29-bbcb-49ea8567bc1e
[PASS] review overview - 200
[PASS] findings returned - ACCREDITATION_VALIDITY=PASS, AFFILIATION_DECLARATION_MATCH=PASS, AFFILIATION_VALIDITY=PASS, CHECKLIST_REQUIRED=PASS
[PASS] declaration consistency evaluated - PASS
[PASS] technical inspection - 201
[PASS] inspection stays advisory - qr-payload=NOT_FOUND, pdf-signature=NOT_FOUND
[PASS] report export json - 200
[PASS] report json is an attachment and repeats limitations
[PASS] report export markdown - 200
[PASS] report markdown is an attachment and repeats limitations
[PASS] report export html - 200
[PASS] report html is an attachment and repeats limitations
[PASS] clean application produces no rule-failure alert - 0 alerts
[PASS] create application - APP-2099-000008 (cycle 2099-08)
[PASS] read checklist - 200
[PASS] upload AFFILIATION_CERTIFICATE - 202
[PASS] upload LAND_LEASE_DOCUMENT - 202
[PASS] upload FACULTY_DEGREE_CERTIFICATE - 202
[PASS] upload INSTITUTIONAL_UNDERTAKING - 202
[PASS] submit deliberately inconsistent application - 200
[PASS] deliberately inconsistent application fails a rule - FAIL
[PASS] failed findings raise alerts - 3 alerts
[PASS] an alert is available to demonstrate disposition - 3 open
[PASS] acknowledge alert - 200
[PASS] dismissive disposition without a note is refused - 400
[PASS] resolve alert with disposition - 200
[PASS] disposition recorded - ADDRESSED
[PASS] disposition does not change findings - finding outcomes unchanged

44/44 steps passed

Reminder: every result above is advisory. Nothing here is an AICTE decision, and no issuer or AICTE system was contacted.
```

**Not implied:** this proves the local HTTP surface behaves as scripted on synthetic input. It is not browser automation, not a load test, and not evidence of AICTE readiness. The two applications it creates are left in the dev database as demo material; re-runs use the next free `2099-xx` cycle, so a public demo should start from a reset database (§7 of the runbook).

### 14.16 Not executed

No claim is made for: Playwright/browser E2E, CI, lint/type checks, load/performance tests, security scanners (`bandit`, `pip-audit`, `gitleaks`, `trivy`), Amoy deployment, production MPC ceremony, real AICTE/issuer integration, or retention/encryption-at-rest verification.

---

## 15. Open questions

1. Confirm the exact AICTE rule set and citations before measuring validation accuracy against “official” labels.
2. Confirm evaluation dataset composition and whether judges will supply test records.
3. Confirm acceptable verification-time targets for the demo environment.
4. Confirm whether video evidence is in scope for the demo (affects upload limits and processing).
5. Confirm the manual-effort study protocol (operator, tasks, timing).
