"""Live end-to-end smoke walkthrough for the M6 demo.

This script talks to a *running* backend over HTTP. It does not import the app
and does not touch the database directly, so it validates exactly what a demo
audience sees:

    health -> login -> application -> self-check (blocked) -> uploads ->
    declaration -> self-check (ready) -> submit -> review overview ->
    technical inspection -> report export (json/markdown/html) ->
    alert acknowledgement and disposition

Everything it uploads is synthetic and generated in memory. The application it
creates stays in the target database (use the dev database, never production).

Usage (backend must already be running):

    cd backend
    ./venv/bin/python scripts/demo_smoke.py
    ./venv/bin/python scripts/demo_smoke.py --base-url http://localhost:8000

Exit code 0 means every step passed; 1 means at least one step failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

import httpx
import pymupdf

DEFAULT_PASSWORD = "ChangeMe123!"
CANDIDATE_CYCLES = [f"2099-{month:02d}" for month in range(1, 13)]
INSTITUTION = "Sunrise Institute of Technology"

CONSISTENT_DECLARATION = {
    "affiliation_number": "AFF/SMOKE/001",
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


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Walkthrough:
    base_url: str
    password: str
    client: httpx.Client = field(init=False)
    steps: list[Step] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.client = httpx.Client(base_url=self.base_url, timeout=120.0)

    # -- helpers ---------------------------------------------------------
    def record(self, name: str, ok: bool, detail: str = "") -> bool:
        self.steps.append(Step(name, ok, detail))
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {name}" + (f" — {detail}" if detail else ""))
        return ok

    def expect(self, name: str, response: httpx.Response, status: int) -> httpx.Response:
        body = response.text
        if response.status_code != status:
            detail = body[:300].replace("\n", " ")
            self.record(name, False, f"expected {status}, got {response.status_code}: {detail}")
            raise SystemExit(1)
        self.record(name, True, f"{response.status_code}")
        return response

    def login(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": self.password}
        )
        if response.status_code != 200:
            self.record(
                f"login {email}", False, f"{response.status_code}: {response.text[:200]}"
            )
            raise SystemExit(1)
        self.record(f"login {email}", True, "access token issued")
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def free_application(self, headers: dict[str, str]) -> dict:
        for cycle in CANDIDATE_CYCLES:
            response = self.client.post(
                "/api/v1/applications",
                headers=headers,
                json={"category_code": "EOA", "cycle": cycle},
            )
            if response.status_code == 201:
                application = response.json()
                self.record(
                    "create application", True, f"{application['reference_no']} (cycle {cycle})"
                )
                return application
            if response.status_code != 409:
                self.record(
                    "create application", False, f"{response.status_code}: {response.text[:200]}"
                )
                raise SystemExit(1)
        self.record(
            "create application",
            False,
            "cycles 2099-01..12 all taken; drop the demo applications or pass a clean database",
        )
        raise SystemExit(1)


def make_pdf(lines: list[str]) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((50, 100 + index * 22), line)
    content = document.tobytes()
    document.close()
    return content


def document_lines(*, institution: str, valid_until: str, affiliation_no: str) -> dict[str, list[str]]:
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


def findings_of(walk: Walkthrough, headers: dict[str, str], application_id: str) -> dict[str, str]:
    """Read the latest validation findings from the staff review overview."""
    response = walk.client.get(
        f"/api/v1/applications/{application_id}/review-overview", headers=headers
    )
    response.raise_for_status()
    body = response.json()
    return {
        item["code"]: item["outcome"]
        for item in (body.get("latest_validation_run") or {}).get("findings", [])
    }


def checklist_items(walk: Walkthrough, headers: dict[str, str], application_id: str) -> dict:
    response = walk.client.get(
        f"/api/v1/applications/{application_id}/checklist", headers=headers
    )
    walk.expect("read checklist", response, 200)
    return {item["code"]: item for item in response.json()["items"]}


def upload_pack(
    walk: Walkthrough,
    headers: dict[str, str],
    application_id: str,
    lines_by_code: dict[str, list[str]],
) -> dict:
    items = checklist_items(walk, headers, application_id)
    uploaded: dict[str, dict] = {}
    for code, lines in lines_by_code.items():
        item = items[code]
        response = walk.client.post(
            f"/api/v1/applications/{application_id}/documents",
            headers=headers,
            files={"file": (f"{code.lower()}.pdf", make_pdf(lines), "application/pdf")},
            data={
                "document_type": item["accepted_document_types"][0],
                "checklist_item_id": item["id"],
            },
        )
        walk.expect(f"upload {code}", response, 202)
        uploaded[code] = response.json()
    return uploaded


def run(args: argparse.Namespace) -> int:
    walk = Walkthrough(args.base_url.rstrip("/"), args.password)
    print(f"Smoke walkthrough against {walk.base_url}\n")

    health = walk.client.get("/health")
    walk.expect("health", health, 200)

    applicant = walk.login("applicant@example.test")
    reviewer = walk.login("reviewer@example.test")

    application = walk.free_application(applicant)
    application_id = application["id"]

    preview = walk.client.get(
        f"/api/v1/applications/{application_id}/self-check", headers=applicant
    )
    body = walk.expect("self-check before evidence", preview, 200).json()
    walk.record(
        "self-check blocks an empty application",
        body["can_submit"] is False and body["counts"]["BLOCKING"] >= 1,
        f"blocking={body['counts']['BLOCKING']}, can_submit={body['can_submit']}",
    )

    blocked = walk.client.post(
        f"/api/v1/applications/{application_id}/submit", headers=applicant
    )
    walk.record(
        "submit is refused while evidence is missing",
        blocked.status_code == 400,
        f"{blocked.status_code} {blocked.json().get('error', {}).get('code', '')}",
    )

    uploaded = upload_pack(
        walk,
        applicant,
        application_id,
        document_lines(
            institution=INSTITUTION,
            valid_until="31/03/2031",
            # Unique per application so a clean demo run does not trip the
            # cross-application identifier-reuse anomaly on a re-run.
            affiliation_no=f"AFF/{application['reference_no']}",
        ),
    )

    declaration = walk.client.put(
        f"/api/v1/applications/{application_id}/declaration",
        headers=applicant,
        json={
            **CONSISTENT_DECLARATION,
            "affiliation_number": f"AFF/{application['reference_no']}",
        },
    )
    walk.expect("save structured declaration", declaration, 200)

    preview = walk.client.get(
        f"/api/v1/applications/{application_id}/self-check", headers=applicant
    )
    body = walk.expect("self-check after evidence", preview, 200).json()
    walk.record(
        "self-check now allows submission",
        body["can_submit"] is True,
        f"blocking={body['counts']['BLOCKING']}, warnings={body['counts']['WARNING']}",
    )

    submitted = walk.client.post(
        f"/api/v1/applications/{application_id}/submit", headers=applicant
    )
    walk.expect("submit", submitted, 200)
    run_id = submitted.json()["validation_run_id"]
    walk.record("validation run started", run_id is not None, str(run_id))

    overview = walk.client.get(
        f"/api/v1/applications/{application_id}/review-overview", headers=reviewer
    )
    overview_body = walk.expect("review overview", overview, 200).json()
    findings = {
        item["code"]: item["outcome"]
        for item in (overview_body.get("latest_validation_run") or {}).get("findings", [])
    }
    walk.record(
        "findings returned",
        bool(findings),
        ", ".join(f"{code}={outcome}" for code, outcome in sorted(findings.items())[:4]),
    )
    walk.record(
        "declaration consistency evaluated",
        findings.get("AFFILIATION_DECLARATION_MATCH") == "PASS",
        str(findings.get("AFFILIATION_DECLARATION_MATCH")),
    )

    version_id = uploaded["AFFILIATION_CERTIFICATE"]["document_version_id"]
    inspection = walk.client.post(
        f"/api/v1/document-versions/{version_id}/technical-verifications", headers=reviewer
    )
    rows = walk.expect("technical inspection", inspection, 201).json()
    walk.record(
        "inspection stays advisory",
        bool(rows) and all(row["status"] != "VERIFIED" for row in rows),
        ", ".join(f"{row['adapter_code']}={row['status']}" for row in rows),
    )

    for report_format in ("json", "markdown", "html"):
        response = walk.client.get(
            f"/api/v1/applications/{application_id}/report",
            headers=reviewer,
            params={"format": report_format},
        )
        walk.expect(f"report export {report_format}", response, 200)
        walk.record(
            f"report {report_format} is an attachment and repeats limitations",
            response.headers.get("content-disposition", "").lower().startswith("attachment")
            and "advisory only" in response.text.lower(),
        )

    clean_alerts = walk.client.get(
        f"/api/v1/applications/{application_id}/alerts", headers=reviewer
    ).json()
    rule_failure_alerts = [
        alert
        for alert in clean_alerts
        if (alert.get("payload") or {}).get("advisory_only") is not True
    ]
    walk.record(
        "clean application produces no rule-failure alert",
        not rule_failure_alerts,
        f"{len(clean_alerts)} advisory alert(s)" if clean_alerts else "0 alerts",
    )

    # A deliberate mismatch, so the alert path is exercised even when the happy
    # path produces no findings. This application is left in the database as an
    # example of a failed validation.
    mismatch = walk.free_application(applicant)
    upload_pack(
        walk,
        applicant,
        mismatch["id"],
        document_lines(
            institution="Unrelated Valley College",
            valid_until="31/03/2020",
            affiliation_no="AFF/SMOKE/EXPIRED",
        ),
    )
    mismatch_submit = walk.client.post(
        f"/api/v1/applications/{mismatch['id']}/submit", headers=applicant
    )
    walk.expect("submit deliberately inconsistent application", mismatch_submit, 200)
    mismatch_findings = findings_of(walk, reviewer, mismatch["id"])
    walk.record(
        "deliberately inconsistent application fails a rule",
        mismatch_findings.get("AFFILIATION_VALIDITY") == "FAIL",
        str(mismatch_findings.get("AFFILIATION_VALIDITY")),
    )
    mismatch_alerts = walk.client.get(
        f"/api/v1/applications/{mismatch['id']}/alerts", headers=reviewer
    ).json()
    walk.record(
        "failed findings raise alerts",
        any(alert["status"] == "OPEN" for alert in mismatch_alerts),
        f"{len(mismatch_alerts)} alerts",
    )

    if args.resolve_alert:
        open_alerts = [alert for alert in mismatch_alerts if alert["status"] == "OPEN"]
        if not walk.record(
            "an alert is available to demonstrate disposition",
            bool(open_alerts),
            f"{len(open_alerts)} open",
        ):
            return 1
        alert_id = open_alerts[0]["id"]
        acknowledged = walk.client.post(
            f"/api/v1/alerts/{alert_id}/acknowledge", headers=reviewer
        )
        walk.expect("acknowledge alert", acknowledged, 200)
        rejected = walk.client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            headers=reviewer,
            json={"disposition": "FALSE_POSITIVE"},
        )
        walk.record(
            "dismissive disposition without a note is refused",
            rejected.status_code == 400,
            str(rejected.status_code),
        )
        resolved = walk.client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            headers=reviewer,
            json={
                "disposition": "ADDRESSED",
                "note": "Synthetic demo walkthrough; reviewed manually.",
            },
        )
        resolved_body = walk.expect("resolve alert with disposition", resolved, 200).json()
        walk.record(
            "disposition recorded",
            resolved_body.get("disposition") == "ADDRESSED",
            str(resolved_body.get("disposition")),
        )
        walk.record(
            "disposition does not change findings",
            findings_of(walk, reviewer, mismatch["id"]) == mismatch_findings,
            "finding outcomes unchanged",
        )

    failed = [step for step in walk.steps if not step.ok]
    total = len(walk.steps)
    print(f"\n{total - len(failed)}/{total} steps passed")
    if failed:
        for step in failed:
            print(f"  failed: {step.name} — {step.detail}")
        return 1
    print(
        "\nReminder: every result above is advisory. Nothing here is an AICTE decision, "
        "and no issuer or AICTE system was contacted."
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Running backend base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="Seed account password (default: ChangeMe123!)",
    )
    parser.add_argument(
        "--no-resolve-alert",
        dest="resolve_alert",
        action="store_false",
        help="Skip alert acknowledgement/disposition demonstration",
    )
    parser.set_defaults(resolve_alert=True)
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(run(parse_args()))
