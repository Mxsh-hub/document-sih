# AstraVerify — AICTE SIH Adaptation Roadmap

## Project Objective

Adapt the existing `document-sih` repository into an AI-powered platform for application validation, document authentication, and regulatory compliance verification aligned with the SIH problem statement.

The platform must help validate institutional applications, extract and cross-check document information, identify potential anomalies, facilitate verification through authorized issuing authorities, assist with regulatory compliance checks, and provide evidence-linked findings for authorized human review.

**Core principle:** This is a regulatory decision-support system. AI-generated findings are advisory; statutory scrutiny, inspections, and final decisions remain with competent AICTE authorities.

## Mandatory Development Rules

1. Audit the existing repository before proposing code changes.
2. Reuse working components wherever practical. Do not rebuild the project from scratch.
3. Distinguish implemented features from placeholders, mock implementations, and planned functionality.
4. Do not remove existing functionality without documenting the reason and obtaining approval.
5. Do not assume access to AICTE databases, restricted institutional records, or external issuer APIs.
6. Use synthetic or authorized anonymized data for the prototype. Clearly label simulated integrations.
7. Keep regulatory rules configurable and versioned rather than hardcoding unconfirmed requirements.
8. Every validation finding should explain the reason, evidence, applicable rule, and recommended next action.
9. Never treat an anomaly score as conclusive proof of forgery.
10. Preserve role-based access, confidentiality, auditability, and human review.
11. Work incrementally. Explain the plan, implement a milestone, run tests, review the diff, and document results before proceeding.
12. Do not begin the next phase until the current phase's acceptance criteria have been met.

---

## Phase 1 — Repository Audit and Requirements Analysis

### Objective
Understand the current implementation and map it to the SIH problem statement.

### Tasks
- Inspect the repository structure, frontend, backend, database, APIs, authentication, and tests.
- Trace the existing document-upload and verification workflows.
- Inspect OCR, AI, issuer verification, cryptographic proofs, blockchain, and other existing modules.
- Identify working functionality, incomplete functionality, placeholders, and technical debt.
- Map every SIH requirement to an existing feature or a required implementation.
- Identify reusable components and unnecessary complexity.

### Deliverables
- `docs/REPOSITORY_AUDIT.md`
- `docs/REQUIREMENTS_TRACEABILITY.md`
- Updated `README.md`
- Initial `SPEC.md` outlining the target system and MVP scope.

### Acceptance Criteria
- Existing architecture is documented accurately.
- Every major SIH requirement has an implementation status and planned approach.
- Existing functionality is classified as KEEP, MODIFY, BUILD, or DEFER.
- No application code has been modified without approval.

---

## Phase 2 — System Specification and Architecture

### Objective
Define the target architecture and implementation contracts before major coding begins.

### Tasks
- Define application workflows, user roles, and application states.
- Select one representative application category for the initial MVP.
- Design the data model and API contracts.
- Define module boundaries for application management, document processing, rules evaluation, issuer verification, anomaly detection, compliance assistance, and audit logging.
- Define file storage, data protection, error handling, and security requirements.
- Establish testing strategy and measurable acceptance criteria.

### Deliverables
- Completed `SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/API_CONTRACTS.md`
- `docs/TEST_PLAN.md`

### Acceptance Criteria
- Architecture aligns with the supplied SIH problem statement.
- Existing technology choices are retained or changed with justification.
- Frontend and backend interfaces are defined.
- The MVP scope is realistic and testable.

---

## Phase 3 — Application Management and Institutional Records

### Objective
Make the institution's application the central unit of the system.

### Tasks
- Implement application creation, editing, submission, and status tracking.
- Support application categories and category-specific checklists.
- Implement institution profiles and synthetic institutional records.
- Associate uploaded documents with specific applications and checklist requirements.
- Support document versions and permitted rectification workflows.
- Establish role-based access to applications and records.

### Deliverables
- Functional application management APIs.
- Application and institution database models.
- Application submission and document-upload interface.
- Configurable checklist data structures.

### Acceptance Criteria
- A user can create an application and upload its supporting documents.
- Application data persists across sessions.
- Each document is associated with the correct application and requirement.
- Access restrictions are enforced server-side.

---

## Phase 4 — OCR and Intelligent Document Processing

### Objective
Extract structured information from uploaded documents and make it available for validation.

### Tasks
- Reuse and improve existing OCR and document parsing.
- Support appropriate PDF and image formats.
- Classify document types.
- Extract relevant fields, identifiers, dates, and institution details.
- Normalize extracted values for comparison.
- Retain page references, extraction confidence, and source evidence.
- Handle unreadable documents, missing fields, and low-confidence extraction.
- Store document hashes and securely retain original files.

### Deliverables
- Document processing pipeline.
- Structured extraction schema.
- OCR and classification APIs.
- Document processing status and error handling.

### Acceptance Criteria
- Supported documents can be processed end to end.
- Extracted values can be traced to their source documents.
- Uncertain values are not silently treated as verified facts.
- Extraction performance can be measured using labeled test data.

---

## Phase 5 — Regulatory Rules Engine and Application Validation

### Objective
Validate applications against configurable requirements and available institutional records.

### Tasks
- Implement versioned, configurable validation rules.
- Support category-specific required-document checklists.
- Detect missing, incomplete, expired, or inconsistent information.
- Cross-check institution names, identifiers, dates, and other relevant fields.
- Compare application data with available authorized institutional records.
- Validate applicable payment or approval-status information when supported by available data.
- Generate structured findings linked to the relevant documents, fields, records, and rules.
- Support rectification and revalidation.

### Deliverables
- Regulatory rules engine.
- Versioned rule configuration.
- Application validation API.
- Evidence-linked validation reports.

### Acceptance Criteria
- Known test cases produce deterministic rule outcomes.
- Each finding identifies its reason, source evidence, rule version, and recommended action.
- Unavailable information is distinguished from a failed check.
- Regulatory thresholds and requirements are grounded in approved source material.

---

## Phase 6 — Document Authentication and Issuer Verification

### Objective
Verify document integrity and facilitate confirmation from original issuing authorities where supported.

### Tasks
- Separate file integrity, document authenticity, and information consistency checks.
- Reuse existing cryptographic verification and issuer workflows where appropriate.
- Implement supported QR-code and digital-signature verification.
- Design an adapter interface for authorized issuer APIs and official verification services.
- Record verification source, timestamp, response, and result.
- Support verified, mismatch detected, expired, pending, source unavailable, and manual-review states as applicable.
- Implement clearly labeled simulated issuer services for unavailable external integrations.

### Deliverables
- Verification adapter interface.
- Document verification service.
- Verification status model.
- Issuer-verification history.

### Acceptance Criteria
- Verification workflows handle success, mismatch, unavailable sources, and inconclusive results.
- Simulated verification is never represented as a real authority response.
- Hash matching alone is not presented as proof of authenticity.
- Restricted sources are accessed only through authorized mechanisms.

---

## Phase 7 — Anomaly Detection and Infrastructure Compliance Assistance

### Objective
Identify suspicious indicators and potential compliance gaps requiring further review.

### Tasks
- Detect duplicate documents and identifiers.
- Identify inconsistent metadata and suspicious document differences where technically supported.
- Compare relevant document fields and records.
- Evaluate suitable computer-vision techniques for submitted infrastructure evidence.
- Associate photographs, videos, floor plans, and certificates with configurable requirements.
- Flag insufficient, missing, or inconclusive evidence.
- Recommend additional evidence or physical inspection when warranted.
- Record the reason and supporting evidence for each finding.

### Deliverables
- Anomaly detection module.
- Evidence comparison workflows.
- Infrastructure compliance assistance interface.
- Advisory finding schema.

### Acceptance Criteria
- Anomaly findings are evidence-linked and explainable.
- Performance is evaluated on suitable labeled test cases.
- No model is claimed to prove forgery without adequate evidence.
- Inconclusive infrastructure evidence does not automatically establish non-compliance.

---

## Phase 8 — Official Review Dashboard, Alerts, and Audit Trail

### Objective
Give authorized reviewers a centralized view of application validation and outstanding actions.

### Tasks
- Implement application search, filters, and status summaries.
- Build an application-level review interface.
- Show extracted fields, documents, rule results, issuer responses, and anomaly findings.
- Implement alerts for deficiencies, expired documents, pending verification, and unresolved discrepancies.
- Support reviewer notes, rectification requests, escalation, and recorded decisions.
- Maintain a traceable history of validation runs, rule changes, source responses, and reviewer actions.

### Deliverables
- Official review dashboard.
- Alert and action workflows.
- Audit event model and history interface.
- Reviewer action APIs.

### Acceptance Criteria
- Reviewers can investigate and act on application findings.
- Every important action is attributable to an authorized user or system process.
- Earlier validation results remain explainable against the rule versions used.
- Final regulatory decisions remain under authorized human control.

---

## Phase 9 — Security and Reliability Hardening

### Objective
Make the prototype safe, robust, and suitable for controlled demonstration.

### Tasks
- Enforce role-based authorization on protected endpoints.
- Secure document upload, storage, preview, and download.
- Validate file types, file sizes, and untrusted document content.
- Protect secrets and configuration.
- Apply appropriate encryption, retention, and access logging.
- Test isolation between institutions and reviewer permissions.
- Protect AI workflows against prompt injection through uploaded content.
- Add error handling, observability, and audit-integrity checks.

### Deliverables
- Security checklist.
- Authorization and upload-validation tests.
- Documented data-handling policy.
- Reliability and error-handling improvements.

### Acceptance Criteria
- Unauthorized users cannot access protected applications or documents.
- Malformed or unsupported files are handled safely.
- Secrets are not committed to the repository.
- Security-relevant actions are logged appropriately.

---

## Phase 10 — Integration and End-to-End Testing

### Objective
Verify that the complete platform works as one coherent system.

### Tasks
- Integrate all modules and verify their API contracts.
- Create synthetic application datasets covering valid, incomplete, expired, inconsistent, and suspicious cases.
- Test issuer verification success, mismatch, and unavailable-source scenarios.
- Test infrastructure evidence requiring additional review.
- Test rectification and revalidation.
- Test audit history and authorization.
- Measure OCR accuracy, rule-validation accuracy, anomaly precision and recall, verification success rate, and processing time.

### Deliverables
- Automated test suite.
- Synthetic demonstration dataset.
- Test and evaluation report.
- Documented known limitations.

### Acceptance Criteria
- Core workflows pass integration and end-to-end tests.
- Findings are reproducible on the test dataset.
- Evaluation metrics are measured rather than invented.
- Known limitations are explicitly documented.

---

## Phase 11 — SIH Demo and Final Documentation

### Objective
Deliver a polished, reproducible prototype demonstrating the value of the solution.

### Tasks
- Prepare synthetic institution applications and supporting documents.
- Demonstrate application creation, document extraction, validation, and anomaly detection.
- Show an issuer-verification result and an unavailable-source fallback.
- Demonstrate an evidence-linked discrepancy and human reviewer action.
- Show the audit history and explain how results are generated.
- Finalize setup instructions, architecture documentation, test results, and limitations.
- Prepare a concise technical demonstration and SIH presentation.

### Deliverables
- Working end-to-end prototype.
- Updated README and complete specifications.
- Demo dataset and reproducible test instructions.
- Evaluation report and demonstration script.

### Acceptance Criteria
- The entire core workflow can be demonstrated reliably.
- Synthetic and simulated components are clearly disclosed.
- Every major claim is supported by working functionality or measured results.
- The project clearly demonstrates alignment with the SIH problem statement.

---

## Execution Protocol

For every phase:

1. Read the relevant specification and inspect existing code.
2. Propose a small implementation plan with affected files.
3. Explain architectural decisions and trade-offs.
4. Wait for approval before significant changes.
5. Implement one milestone at a time.
6. Run relevant tests and inspect the diff.
7. Update documentation and report completed work, failed tests, limitations, and remaining tasks.
8. Do not claim completion without evidence.

**Immediate instruction:** Execute Phase 1 only. Audit the repository and produce the repository audit, requirements traceability matrix, updated README, and initial SPEC. Do not start implementation phases until the audit and scope have been reviewed.