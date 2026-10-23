"""Measured evaluation for the synthetic MVP dataset.

Run from backend/:
    ./venv/bin/python evaluation/run_evaluation.py

This script uses a dedicated PostgreSQL database (astra_evaluation) and never
touches the development or test databases. All documents and records are
synthetic. Metrics are computed from observed API responses; nothing is
hard-coded.
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
        submitted = submit(client, applicant, application["id"])
        run_id = submitted.json()["validation_run_id"]
        actual = finding_map(client, applicant, run_id)
        case_correct = 0
        for rule_code, actual_outcome in actual.items():
            expected = case["expected"].get(rule_code, "PASS")
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


def main() -> int:
    prepare_database()
    client = TestClient(app)
    applicant = login(client, "applicant@example.test")
    applicant2 = login(client, "applicant2@example.test")
    reviewer = login(client, "reviewer@example.test")
    admin = login(client, "admin@example.test")
    started = time.perf_counter()

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "synthetic, generated in-memory by this script",
        "disclaimer": (
            "Metrics describe only the synthetic evaluation corpus. They are not "
            "AICTE accuracy claims and must not be presented as evidence of real-world performance."
        ),
        "ocr_field_extraction": evaluate_ocr(client, applicant),
        "rule_validation": evaluate_rules(client, applicant, reviewer),
        "anomaly_heuristics": evaluate_anomalies(client, applicant, applicant2, admin),
        "issuer_verification": evaluate_issuer(client, applicant, admin),
    }
    results["total_runtime_seconds"] = round(time.perf_counter() - started, 2)

    output = BACKEND_DIR / "evaluation" / "results.json"
    output.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
