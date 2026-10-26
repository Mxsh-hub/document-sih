"""Measured evaluation for the synthetic MVP dataset.

Run from backend/:
    ./venv/bin/python evaluation/run_evaluation.py

This script uses a dedicated PostgreSQL database (astra_evaluation) and never
touches the development or test databases. All documents and records are
synthetic. Metrics are computed from observed API responses; nothing is
hard-coded.

Sections: OCR field extraction, rule outcomes, anomaly precision/recall, issuer
states, declaration consistency labels, and an ``advisory_controls`` block of
binary assertions (self-check/submit parity, no-write preview, non-committal
inspection, report claim safety, export auditability, disposition gating,
stale-alert supersede). The advisory block is a pass/fail safety check, not an
accuracy statistic.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

EVAL_DATABASE_URL = "postgresql+psycopg://astra:astra@localhost:55432/astra_evaluation"
os.environ["DATABASE_URL"] = EVAL_DATABASE_URL
os.environ["JWT_SECRET"] = "evaluation-secret-at-least-32-characters-long"
os.environ["DOWNLOAD_SIGNING_KEY"] = "evaluation-download-key-at-least-32-characters"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["OBJECT_STORE_DIR"] = str(BACKEND_DIR / "evaluation" / "objects")
os.environ.setdefault("SEED_PASSWORD", "ChangeMe123!")
os.environ["PROCESS_DOCUMENTS_INLINE"] = "true"

import psycopg
import pymupdf
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.db.base import get_db
from app.main import app
from app.seed import seed


def make_pdf(lines: list[str], *, creator: str | None = None) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((50, 100 + index * 22), line)
    if creator:
        document.set_metadata({"creator": creator, "producer": creator})
    content = document.tobytes()
    document.close()
    return content


def prepare_database() -> None:
    with psycopg.connect(
        "postgresql://astra:astra@localhost:55432/postgres", autocommit=True
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'astra_evaluation'"
        ).fetchone()
        if not exists:
            connection.execute("CREATE DATABASE astra_evaluation")
    with psycopg.connect(
        "postgresql://astra:astra@localhost:55432/astra_evaluation", autocommit=True
    ) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    seed()


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": os.environ["SEED_PASSWORD"]},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_application(client, headers, cycle: str) -> dict:
    response = client.post(
        "/api/v1/applications",
        headers=headers,
        json={"category_code": "EOA", "cycle": cycle},
    )
    response.raise_for_status()
    return response.json()


def checklist(client, headers, application_id: str) -> list[dict]:
    response = client.get(f"/api/v1/applications/{application_id}/checklist", headers=headers)
    response.raise_for_status()
    return response.json()["items"]


def upload(
    client,
    headers,
    application_id: str,
    *,
    document_type: str,
    content: bytes,
    checklist_item_id: str | None = None,
    filename: str = "synthetic.pdf",
):
    data = {"document_type": document_type}
    if checklist_item_id:
        data["checklist_item_id"] = checklist_item_id
    started = time.perf_counter()
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        files={"file": (filename, content, "application/pdf")},
        data=data,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    return response.json(), elapsed_ms


def document_lines(
    *,
    institution: str,
    valid_until: str = "31/03/2031",
    affiliation_no: str = "AFF/EVAL/001",
) -> dict[str, list[str]]:
    return {
        "AFFILIATION_CERTIFICATE": [
            "AICTE Affiliation Certificate",
            f"Name of Institution: {institution}",
            f"Affiliation No: {affiliation_no}",
            "Issued by: State Technical University",
            "Date of Issue: 01/04/2026",
            f"Valid upto: {valid_until}",
        ],
        "LAND_LEASE_DOCUMENT": [
            "Registered Land Lease Deed",
            f"Name of Institution: {institution}",
            "Land Area: 2.5 acres",
        ],
        "FACULTY_DEGREE_CERTIFICATE": [
            "University Degree Certificate",
            "Name: Dr. A. Sharma",
            "Degree: Ph.D. (Computer Science)",
            "Issued by: State Technical University",
        ],
        "INSTITUTIONAL_UNDERTAKING": [
            "Institutional Undertaking",
            f"Name of Institution: {institution}",
            "Issued by: The Registrar",
            "Date of Issue: 20/06/2026",
        ],
    }


def upload_pack(
    client, headers, application_id: str, lines_by_type: dict[str, list[str]]
) -> tuple[dict[str, dict], list[float]]:
    uploaded: dict[str, dict] = {}
    durations: list[float] = []
    items = {item["code"]: item for item in checklist(client, headers, application_id)}
    for code, lines in lines_by_type.items():
        item = items[code]
        result, elapsed = upload(
            client,
            headers,
            application_id,
            document_type=item["accepted_document_types"][0],
            content=make_pdf(lines),
            checklist_item_id=item["id"],
            filename=f"{code}.pdf",
        )
        uploaded[code] = result
        durations.append(elapsed)
    return uploaded, durations


def submit(client, headers, application_id: str):
    response = client.post(f"/api/v1/applications/{application_id}/submit", headers=headers)
    return response


def finding_map(client, headers, run_id: str) -> dict[str, str]:
    response = client.get(f"/api/v1/validation-runs/{run_id}", headers=headers)
    response.raise_for_status()
    return {item["code"]: item["outcome"] for item in response.json()["findings"]}


DECLARATION_RULES = {
    "AFFILIATION_DECLARATION_MATCH",
    "PROGRAMME_DECLARATION_MATCH",
    "FACULTY_COUNT_DECLARATION_MATCH",
}


def declare(client, headers, application_id: str, declaration: dict) -> dict:
    response = client.put(
        f"/api/v1/applications/{application_id}/declaration",
        headers=headers,
        json=declaration,
    )
    response.raise_for_status()
    return response.json()



def evaluate_ocr(client, applicant) -> dict:
    application = create_application(client, applicant, "2031-01")
    expected_fields = 5
    correct = 0
    total = 0
    upload_ms: list[float] = []
    records = []
    for index in range(20):
        institution = f"Evaluation Institute {index:02d}"
        affiliation = f"AFF/EVAL/{index:03d}"
        valid_until = f"31/03/{2030 + (index % 3)}"
        lines = [
            "AICTE Affiliation Certificate",
            f"Name of Institution: {institution}",
            f"Affiliation No: {affiliation}",
            "Issued by: Evaluation Technical University",
            "Date of Issue: 01/04/2026",
            f"Valid upto: {valid_until}",
        ]
        result, elapsed = upload(
            client,
            applicant,
            application["id"],
            document_type="AFFILIATION_CERTIFICATE",
            content=make_pdf(lines),
            filename=f"ocr-{index}.pdf",
        )
        upload_ms.append(elapsed)
        extraction = client.get(
            f"/api/v1/document-versions/{result['document_version_id']}/extraction",
            headers=applicant,
        ).json()
        fields = {field["name"]: field["normalized_value"] for field in extraction["fields"]}
        expected = {
            "institution_name": institution.lower(),
            "affiliation_number": affiliation.lower(),
            "issuing_authority": "evaluation technical university",
            "issued_date": "2026-04-01",
            "valid_until": f"{2030 + (index % 3)}-03-31",
        }
        matches = 0
        for name, value in expected.items():
            total += 1
            if fields.get(name) == value:
                correct += 1
                matches += 1
        records.append({"document": index, "fields_expected": expected_fields, "fields_correct": matches})
    return {
        "documents": 20,
        "fields_total": total,
        "fields_correct": correct,
        "field_exact_match_accuracy": round(correct / total, 4),
        "processing_time_ms": {
            "samples": len(upload_ms),
            "median": round(statistics.median(upload_ms), 2),
            "p95": round(sorted(upload_ms)[int(len(upload_ms) * 0.95) - 1], 2),
            "max": round(max(upload_ms), 2),
        },
        "per_document": records,
    }


def evaluate_rules(client, applicant, reviewer) -> dict:
    cases = [
        {
            "name": "valid",
            "cycle": "2032-01",
            "institution": "Sunrise Institute of Technology",
            "valid_until": "31/03/2031",
            "declaration": {
                "affiliation_number": "AFF/2032-01",
                "affiliation_valid_until": "2031-03-31",
                "programmes": [
                    {"code": "CSE", "name": "B.Tech Computer Science and Engineering", "level": "UG", "intake": 120},
                    {"code": "ECE", "name": "B.Tech Electronics and Communication Engineering", "level": "UG", "intake": 60},
                ],
                "total_intake": 180,
                "faculty_count": 2,
            },
            "expected": {},
            "expected_status": "SUBMITTED",
        },
        {
            "name": "expired_affiliation",
            "cycle": "2032-02",
            "institution": "Sunrise Institute of Technology",
            "valid_until": "31/03/2020",
            "expected": {"AFFILIATION_VALIDITY": "FAIL"},
            "expected_status": "SUBMITTED",
        },
        {
            "name": "institution_name_mismatch",
            "cycle": "2032-03",
            "institution": "Unrelated Valley College",
            "valid_until": "31/03/2031",
            "expected": {"INSTITUTION_NAME_CONSISTENCY": "FAIL"},
            "expected_status": "SUBMITTED",
        },
        {
            "name": "declaration_mismatch",
            "cycle": "2032-04",
            "institution": "Sunrise Institute of Technology",
            "valid_until": "31/03/2031",
            "declaration": {
                "affiliation_number": "AFF/NEVER-ISSUED/999",
                "affiliation_valid_until": "2030-03-31",
                "programmes": [{"code": "MEC", "name": "B.Tech Mechanical Engineering", "level": "UG", "intake": 60}],
                "total_intake": 60,
                "faculty_count": 5,
            },
            "expected": {
                "AFFILIATION_DECLARATION_MATCH": "FAIL",
                "PROGRAMME_DECLARATION_MATCH": "FAIL",
                "FACULTY_COUNT_DECLARATION_MATCH": "FAIL",
            },
            "expected_status": "SUBMITTED",
        },
    ]
    correct = 0
    total = 0
    details = []
    for case in cases:
        application = create_application(client, applicant, case["cycle"])
        upload_pack(
            client,
            applicant,
            application["id"],
            document_lines(
                institution=case["institution"],
                valid_until=case["valid_until"],
                affiliation_no=f"AFF/{case['cycle']}",
            ),
        )
        if case.get("declaration"):
            declare(client, applicant, application["id"], case["declaration"])
        submitted = submit(client, applicant, application["id"])
        run_id = submitted.json()["validation_run_id"]
        actual = finding_map(client, applicant, run_id)
        case_correct = 0
        for rule_code, actual_outcome in actual.items():
            if rule_code in case["expected"]:
                expected = case["expected"][rule_code]
            elif rule_code in DECLARATION_RULES:
                # A supplied declaration is expected to agree; without one the
                # consistency rule has nothing to compare.
                expected = "PASS" if case.get("declaration") else "NOT_AVAILABLE"
            else:
                expected = "PASS"
            total += 1
            if actual_outcome == expected:
                correct += 1
                case_correct += 1
        details.append(
            {
                "case": case["name"],
                "application_id": application["id"],
                "outcomes": actual,
                "expected_overrides": case["expected"],
                "declaration_supplied": bool(case.get("declaration")),
                "rules_correct": case_correct,
                "rules_total": len(actual),
            }
        )
    return {
        "cases": len(cases),
        "labels_total": total,
        "labels_correct": correct,
        "rule_outcome_accuracy": round(correct / total, 4),
        "details": details,
    }


def evaluate_anomalies(client, applicant, applicant2, admin) -> dict:
    expected = {}
    # Clean case.
    clean = create_application(client, applicant, "2033-01")
    clean_upload, _ = upload_pack(
        client, applicant, clean["id"], document_lines(institution="Sunrise Institute of Technology", affiliation_no="ANOM-CLEAN")
    )
    expected[clean["id"]] = set()

    # Cross-application reuse plus shared identifier.
    shared_lines = document_lines(institution="Sunrise Institute of Technology", affiliation_no="ANOM-SHARED")
    shared_content = make_pdf(shared_lines["AFFILIATION_CERTIFICATE"])
    source = create_application(client, applicant2, "2033-02")
    upload(
        client,
        applicant2,
        source["id"],
        document_type="AFFILIATION_CERTIFICATE",
        content=shared_content,
        filename="shared-source.pdf",
    )
    reuse = create_application(client, applicant, "2033-03")
    upload(
        client,
        applicant,
        reuse["id"],
        document_type="AFFILIATION_CERTIFICATE",
        content=shared_content,
        filename="shared-copy.pdf",
    )
    expected[reuse["id"]] = {
        "CROSS_APPLICATION_FILE_REUSE",
        "SHARED_REFERENCE_IDENTIFIER",
    }

    # PDF editing metadata.
    metadata_app = create_application(client, applicant, "2033-04")
    upload(
        client,
        applicant,
        metadata_app["id"],
        document_type="AFFILIATION_CERTIFICATE",
        content=make_pdf(
            document_lines(institution="Sunrise Institute of Technology", affiliation_no="ANOM-META")[
                "AFFILIATION_CERTIFICATE"
            ],
            creator="Adobe Photoshop",
        ),
        filename="metadata.pdf",
    )
    expected[metadata_app["id"]] = {"PDF_EDITING_TOOL_METADATA"}

    tp = fp = fn = 0
    details = []
    for application_id, expected_codes in expected.items():
        response = client.post(
            f"/api/v1/applications/{application_id}/anomaly-scan", headers=admin
        )
        response.raise_for_status()
        actual_codes = {item["signal_code"] for item in response.json()}
        tp += len(expected_codes & actual_codes)
        fp += len(actual_codes - expected_codes)
        fn += len(expected_codes - actual_codes)
        details.append(
            {
                "application_id": application_id,
                "expected": sorted(expected_codes),
                "actual": sorted(actual_codes),
                "advisory_flags": all(item["advisory"] for item in response.json()),
            }
        )
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "applications": len(expected),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "details": details,
    }


def evaluate_issuer(client, applicant, admin) -> dict:
    application = create_application(client, applicant, "2034-01")
    first, _ = upload(
        client,
        applicant,
        application["id"],
        document_type="OTHER",
        content=make_pdf(["Synthetic issuer-bound document"]),
    )
    second, _ = upload(
        client,
        applicant,
        application["id"],
        document_type="OTHER",
        content=make_pdf(["Synthetic different document"]),
    )
    issued = client.post(
        "/api/v1/demo-issuer/credentials",
        headers=admin,
        json={
            "document_version_id": first["document_version_id"],
            "claims": {"kind": "synthetic-evaluation"},
        },
    )
    issued.raise_for_status()
    credential_id = issued.json()["credential_id"]
    verified = client.post(
        f"/api/v1/document-versions/{first['document_version_id']}/issuer-verifications",
        headers=admin,
        json={"issuer_code": "demo", "credential_id": credential_id},
    ).json()
    mismatch = client.post(
        f"/api/v1/document-versions/{second['document_version_id']}/issuer-verifications",
        headers=admin,
        json={"issuer_code": "demo", "credential_id": credential_id},
    ).json()
    unavailable = client.post(
        f"/api/v1/document-versions/{first['document_version_id']}/issuer-verifications",
        headers=admin,
        json={"issuer_code": "external"},
    ).json()
    outcomes = {
        "signed_demo_credential": verified["status"],
        "bound_to_other_document": mismatch["status"],
        "external_source": unavailable["status"],
    }
    expected = {
        "signed_demo_credential": "VERIFIED",
        "bound_to_other_document": "MISMATCH",
        "external_source": "SOURCE_UNAVAILABLE",
    }
    return {
        "scenarios": len(expected),
        "scenarios_correct": sum(outcomes[key] == value for key, value in expected.items()),
        "outcomes": outcomes,
        "expected": expected,
        "all_simulated_sources_labelled": verified["simulated_source"]
        and mismatch["simulated_source"]
        and unavailable["simulated_source"],
    }


AUTO_SUPERSEDED_ALERT_TYPES = {
    "VALIDATION_FAILURE",
    "EXPIRED_DOCUMENT",
    "PENDING_VERIFICATION",
    "UNRESOLVED_DISCREPANCY",
}

CONSISTENT_DECLARATION = {
    "affiliation_number": "AFF/2035-01",
    "affiliation_valid_until": "2031-03-31",
    "programmes": [
        {
            "code": "CSE",
            "name": "B.Tech Computer Science and Engineering",
            "level": "UG",
            "intake": 120,
        },
        {
            "code": "ECE",
            "name": "B.Tech Electronics and Communication Engineering",
            "level": "UG",
            "intake": 60,
        },
    ],
    "total_intake": 180,
    "faculty_count": 2,
}

# Phrases that would turn an advisory review aid into a claim the prototype
# cannot support. The limitations block uses negated wording ("not proof of
# forgery"), so these are deliberately claim-shaped rather than topic words.
FORBIDDEN_CLAIMS = (
    "is forged",
    "confirmed forgery",
    "is authentic",
    "authenticated document",
    "officially verified",
    "guaranteed compliant",
    "proves authenticity",
)


def _check(name: str, passed: bool, observed=None) -> dict:
    return {"check": name, "passed": bool(passed), "observed": observed}


def _score(checks: list[dict]) -> dict:
    passed = sum(1 for check in checks if check["passed"])
    return {
        "checks_total": len(checks),
        "checks_passed": passed,
        "pass_rate": round(passed / len(checks), 4) if checks else 1.0,
        "checks": checks,
    }


def audit_event_count(client, headers, application_id: str) -> int:
    response = client.get(
        f"/api/v1/applications/{application_id}/audit-events", headers=headers
    )
    response.raise_for_status()
    return len(response.json())


def declaration_consistency_metric(rule_results: dict) -> dict:
    """Score the three declaration-consistency labels case by case.

    A supplied declaration must agree with the extracted field and the synthetic
    record; without a declaration the rule must report ``NOT_AVAILABLE`` rather
    than inventing a verdict.
    """
    checks = []
    for case in rule_results["details"]:
        supplied = case.get("declaration_supplied", False)
        for code in sorted(DECLARATION_RULES):
            actual = case["outcomes"].get(code)
            override = case["expected_overrides"].get(code)
            expected = override if override else ("PASS" if supplied else "NOT_AVAILABLE")
            checks.append(
                _check(
                    f"{case['case']}:{code}",
                    actual == expected,
                    {"expected": expected, "actual": actual},
                )
            )
    return _score(checks)


def evaluate_advisory_controls(
    client, applicant, applicant2, reviewer, admin, rule_results
) -> dict:
    """Exercise the advisory-only paths added after the MVP.

    These controls check that the report, self-check, alert dispositions, and
    technical inspection stay advisory: they must never write a decision, never
    expose a conclusive authenticity claim, and never disagree with the real
    submission gate.
    """
    checks: list[dict] = []
    institution = "Sunrise Institute of Technology"

    # --- self-check parity with the submission gate -------------------------
    application = create_application(client, applicant, "2035-01")
    application_id = application["id"]
    self_check_url = f"/api/v1/applications/{application_id}/self-check"

    audit_before = audit_event_count(client, admin, application_id)
    preview = client.get(self_check_url, headers=applicant)
    preview_body = preview.json() if preview.status_code == 200 else {}
    checks.append(_check("self_check_available_for_draft", preview.status_code == 200, preview.status_code))
    checks.append(
        _check(
            "self_check_blocks_missing_evidence",
            preview_body.get("counts", {}).get("BLOCKING", 0) >= 1,
            preview_body.get("counts"),
        )
    )
    checks.append(
        _check(
            "self_check_reports_cannot_submit",
            preview_body.get("can_submit") is False,
            preview_body.get("can_submit"),
        )
    )
    client.get(self_check_url, headers=applicant)
    audit_after = audit_event_count(client, admin, application_id)
    checks.append(
        _check(
            "self_check_writes_no_audit_event",
            audit_before == audit_after,
            {"before": audit_before, "after": audit_after},
        )
    )
    blocked = submit(client, applicant, application_id)
    checks.append(_check("preview_matches_blocked_submit", blocked.status_code == 400, blocked.status_code))

    uploaded, _ = upload_pack(
        client,
        applicant,
        application_id,
        document_lines(institution=institution, affiliation_no="AFF/2035-01"),
    )
    declare(client, applicant, application_id, CONSISTENT_DECLARATION)
    ready = client.get(self_check_url, headers=applicant).json()
    checks.append(
        _check(
            "self_check_clears_after_evidence",
            ready.get("can_submit") is True and ready.get("counts", {}).get("BLOCKING") == 0,
            ready.get("counts"),
        )
    )
    accepted = submit(client, applicant, application_id)
    checks.append(_check("preview_matches_accepted_submit", accepted.status_code == 200, accepted.status_code))
    after_submit = client.get(self_check_url, headers=applicant)
    checks.append(
        _check(
            "self_check_closed_after_submission",
            after_submit.status_code == 409,
            after_submit.status_code,
        )
    )

    # --- advisory technical inspection --------------------------------------
    version_id = uploaded["AFFILIATION_CERTIFICATE"]["document_version_id"]
    inspection = client.post(
        f"/api/v1/document-versions/{version_id}/technical-verifications",
        headers=reviewer,
    )
    rows = inspection.json() if inspection.status_code == 201 else []
    by_adapter = {row["adapter_code"]: row for row in rows}
    checks.append(
        _check(
            "technical_inspection_returns_two_advisers",
            inspection.status_code == 201
            and set(by_adapter) == {"qr-payload", "pdf-signature"},
            sorted(by_adapter),
        )
    )
    checks.append(
        _check(
            "technical_inspection_never_claims_verified",
            bool(rows) and all(row["status"] != "VERIFIED" for row in rows),
            {code: row["status"] for code, row in by_adapter.items()},
        )
    )
    checks.append(
        _check(
            "unsigned_pdf_signature_not_found",
            by_adapter.get("pdf-signature", {}).get("status") == "NOT_FOUND",
            by_adapter.get("pdf-signature", {}).get("status"),
        )
    )
    checks.append(
        _check(
            "qr_state_is_non_committal",
            by_adapter.get("qr-payload", {}).get("status")
            in {"NOT_FOUND", "SOURCE_UNAVAILABLE", "ERROR"},
            by_adapter.get("qr-payload", {}).get("status"),
        )
    )
    checks.append(
        _check(
            "technical_inspection_performed_no_verification",
            all((row.get("evidence") or {}).get("advisory_only") is True for row in rows)
            and (by_adapter.get("qr-payload", {}).get("evidence") or {}).get(
                "external_lookup_performed"
            )
            is False
            and all(
                (by_adapter.get("pdf-signature", {}).get("evidence") or {}).get(flag) is False
                for flag in ("cryptographically_verified", "revocation_checked", "trust_chain_checked")
            ),
            {
                code: {
                    key: (row.get("evidence") or {}).get(key)
                    for key in (
                        "advisory_only",
                        "external_lookup_performed",
                        "cryptographically_verified",
                        "revocation_checked",
                        "trust_chain_checked",
                    )
                }
                for code, row in by_adapter.items()
            },
        )
    )

    # --- advisory report export ---------------------------------------------
    report_bodies: dict[str, str] = {}
    for report_format in ("json", "markdown", "html"):
        response = client.get(
            f"/api/v1/applications/{application_id}/report?format={report_format}",
            headers=reviewer,
        )
        report_bodies[report_format] = response.text
        checks.append(
            _check(f"report_{report_format}_exported", response.status_code == 200, response.status_code)
        )
        disposition = response.headers.get("content-disposition", "")
        checks.append(
            _check(f"report_{report_format}_is_attachment", disposition.lower().startswith("attachment"), disposition)
        )
        checks.append(
            _check(
                f"report_{report_format}_repeats_limitations",
                "advisory only" in response.text.lower(),
                None,
            )
        )
    payload = json.loads(report_bodies["json"])
    checks.append(
        _check(
            "report_is_versioned",
            payload.get("report_version") == "application-report-1.0",
            payload.get("report_version"),
        )
    )
    checks.append(
        _check(
            "report_lists_all_limitations",
            len(payload.get("limitations") or []) >= 5,
            len(payload.get("limitations") or []),
        )
    )
    checks.append(
        _check(
            "report_is_staff_only",
            client.get(
                f"/api/v1/applications/{application_id}/report", headers=applicant
            ).status_code
            == 403,
            None,
        )
    )
    checks.append(
        _check(
            "unsupported_report_format_rejected",
            client.get(
                f"/api/v1/applications/{application_id}/report?format=pdf",
                headers=reviewer,
            ).status_code
            == 400,
            None,
        )
    )
    events = client.get(
        f"/api/v1/applications/{application_id}/audit-events", headers=admin
    ).json()
    exports = [event for event in events if event["event_type"] == "application.report_exported"]
    checks.append(_check("each_export_is_audited", len(exports) == 3, len(exports)))
    hits = sorted(
        {
            phrase
            for phrase in FORBIDDEN_CLAIMS
            for body in report_bodies.values()
            if phrase in body.lower()
        }
    )
    checks.append(_check("report_has_no_conclusive_claim", not hits, hits))

    # --- alert dispositions and stale-alert supersede ------------------------
    alert_application = create_application(client, applicant, "2035-02")
    alert_application_id = alert_application["id"]
    alert_items = {
        item["code"]: item for item in checklist(client, applicant, alert_application_id)
    }
    upload_pack(
        client,
        applicant,
        alert_application_id,
        document_lines(
            institution="Unrelated Valley College",
            valid_until="31/03/2020",
            affiliation_no="AFF/2035-02",
        ),
    )
    failed_submit = submit(client, applicant, alert_application_id)
    run_id = failed_submit.json()["validation_run_id"]
    findings_before = finding_map(client, applicant, run_id)

    alerts_url = f"/api/v1/applications/{alert_application_id}/alerts"
    alerts = client.get(alerts_url, headers=reviewer).json()
    open_alerts = [alert for alert in alerts if alert["status"] == "OPEN"]
    checks.append(_check("failed_findings_raise_alerts", len(open_alerts) >= 1, len(open_alerts)))

    if open_alerts:
        alert_id = open_alerts[0]["id"]
        no_note = client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            headers=reviewer,
            json={"disposition": "FALSE_POSITIVE"},
        )
        checks.append(
            _check("dismissive_disposition_requires_note", no_note.status_code == 400, no_note.status_code)
        )
        unknown = client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            headers=reviewer,
            json={"disposition": "NOT_A_DISPOSITION"},
        )
        checks.append(
            _check("unknown_disposition_rejected", unknown.status_code == 400, unknown.status_code)
        )
        resolved = client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            headers=reviewer,
            json={
                "disposition": "FALSE_POSITIVE",
                "note": "Synthetic evaluation artefact, reviewed manually.",
            },
        )
        resolved_body = resolved.json() if resolved.status_code == 200 else {}
        checks.append(
            _check(
                "disposition_recorded_with_actor",
                resolved.status_code == 200
                and resolved_body.get("disposition") == "FALSE_POSITIVE"
                and resolved_body.get("resolved_by") is not None,
                {
                    "status": resolved.status_code,
                    "disposition": resolved_body.get("disposition"),
                    "resolved_by": resolved_body.get("resolved_by"),
                },
            )
        )
        checks.append(
            _check(
                "applicant_cannot_read_alert_detail",
                client.get(f"/api/v1/alerts/{alert_id}", headers=applicant).status_code == 403,
                None,
            )
        )
        findings_after = finding_map(client, applicant, run_id)
        checks.append(
            _check(
                "disposition_does_not_change_findings",
                findings_before == findings_after,
                {"changed": sorted(
                    code
                    for code in set(findings_before) | set(findings_after)
                    if findings_before.get(code) != findings_after.get(code)
                )},
            )
        )

    requested = client.post(
        f"/api/v1/applications/{alert_application_id}/review-actions",
        headers=reviewer,
        json={
            "action_type": "REQUEST_RECTIFICATION",
            "note": "Synthetic evaluation rectification request.",
        },
    )
    checks.append(
        _check("rectification_requested", requested.status_code in {200, 201}, requested.status_code)
    )
    affiliation_item = alert_items["AFFILIATION_CERTIFICATE"]
    upload(
        client,
        applicant,
        alert_application_id,
        document_type=affiliation_item["accepted_document_types"][0],
        content=make_pdf(
            document_lines(institution=institution, affiliation_no="AFF/2035-02")[
                "AFFILIATION_CERTIFICATE"
            ]
        ),
        checklist_item_id=affiliation_item["id"],
        filename="rectified-affiliation.pdf",
    )
    pending_before_resubmit = {
        alert["id"]
        for alert in client.get(alerts_url, headers=reviewer).json()
        if alert["status"] == "OPEN" and alert["alert_type"] in AUTO_SUPERSEDED_ALERT_TYPES
    }
    resubmitted = submit(client, applicant, alert_application_id)
    checks.append(
        _check("rectified_resubmission_accepted", resubmitted.status_code == 200, resubmitted.status_code)
    )
    alerts_after = client.get(alerts_url, headers=reviewer).json()
    superseded = [
        alert
        for alert in alerts_after
        if alert["id"] in pending_before_resubmit
        and alert["status"] == "RESOLVED"
        and alert.get("disposition") == "SUPERSEDED"
    ]
    checks.append(
        _check(
            "stale_alerts_superseded",
            bool(pending_before_resubmit) and len(superseded) == len(pending_before_resubmit),
            {
                "stale_before_resubmit": len(pending_before_resubmit),
                "superseded_after_resubmit": len(superseded),
            },
        )
    )
    checks.append(
        _check(
            "supersede_has_no_human_actor",
            all(alert.get("resolved_by") is None for alert in superseded),
            [alert.get("resolved_by") for alert in superseded],
        )
    )
    statuses_after = finding_map(client, applicant, resubmitted.json()["validation_run_id"])
    checks.append(
        _check(
            "rectified_run_reports_valid_affiliation",
            statuses_after.get("AFFILIATION_VALIDITY") == "PASS",
            statuses_after.get("AFFILIATION_VALIDITY"),
        )
    )

    return {
        "declaration_consistency": declaration_consistency_metric(rule_results),
        "advisory_controls": _score(checks),
    }


def main() -> int:
    prepare_database()
    client = TestClient(app)
    applicant = login(client, "applicant@example.test")
    applicant2 = login(client, "applicant2@example.test")
    reviewer = login(client, "reviewer@example.test")
    admin = login(client, "admin@example.test")
    started = time.perf_counter()

    rule_results = evaluate_rules(client, applicant, reviewer)
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "synthetic, generated in-memory by this script",
        "disclaimer": (
            "Metrics describe only the synthetic evaluation corpus. They are not "
            "AICTE accuracy claims and must not be presented as evidence of real-world performance."
        ),
        "ocr_field_extraction": evaluate_ocr(client, applicant),
        "rule_validation": rule_results,
        "anomaly_heuristics": evaluate_anomalies(client, applicant, applicant2, admin),
        "issuer_verification": evaluate_issuer(client, applicant, admin),
        "advisory_controls": evaluate_advisory_controls(
            client, applicant, applicant2, reviewer, admin, rule_results
        ),
    }
    results["total_runtime_seconds"] = round(time.perf_counter() - started, 2)

    output = BACKEND_DIR / "evaluation" / "results.json"
    output.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
