from __future__ import annotations

"""Human-readable application report export (M4).

The report is a review aid assembled from the same records the console shows.
It is **not** a decision document, a certificate, or evidence of authenticity:

* findings, anomalies, QR payloads, and signature structures are advisory;
* the structured declaration is applicant-supplied and never verified;
* issuer adapters are synthetic and explicitly labelled;
* the report footer repeats these limits on every format.

Rendering is local and dependency-free (JSON, Markdown, self-contained HTML) so
the export cannot silently change meaning between transports. No PDF renderer or
signature is applied; a report is never presented as a signed artefact.
"""

import html
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Application, AuditEvent, Extraction, User
from app.services.audit import record_audit, verify_audit_chain
from app.services.review import review_overview

REPORT_VERSION = "application-report-1.0"

ADVISORY_LIMITATIONS = (
    "This report is a prototype review aid. It is not an AICTE decision, certificate, or official record.",
    "Findings, anomaly scores, QR payloads, and PDF signature structures are advisory only. They are not proof of forgery, authenticity, or compliance.",
    "The structured declaration is applicant-supplied. A consistency PASS means two sources agree; it does not verify the declaration.",
    "Issuer and record responses are synthetic. No AICTE, DigiLocker, or issuer API is contacted.",
    "Final decisions remain with authorized human officials and are recorded separately as audited decisions.",
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _extraction_rows(db: Session, application: Application) -> dict[str, Extraction]:
    version_ids = [
        document.current_version_id
        for document in application.documents
        if document.current_version_id
    ]
    if not version_ids:
        return {}
    rows = db.scalars(select(Extraction).where(Extraction.document_version_id.in_(version_ids)))
    return {str(row.document_version_id): row for row in rows}


def _finding_payload(finding: Any) -> dict[str, Any]:
    return {
        "code": finding.code,
        "title": finding.title,
        "outcome": finding.outcome.value,
        "severity": finding.severity.value,
        "message": finding.message,
        "details": finding.details,
        "evidence": [
            {
                "evidence_type": evidence.evidence_type,
                "label": evidence.label,
                "entity_id": str(evidence.entity_id) if evidence.entity_id else None,
                "metadata": evidence.metadata_json,
            }
            for evidence in finding.evidence
        ],
    }


def build_application_report(
    db: Session, application: Application, *, actor: User
) -> dict[str, Any]:
    overview = review_overview(db, application)
    run = overview["latest_validation_run"]
    documents = overview["documents"]
    extractions = _extraction_rows(db, application)
    chain = verify_audit_chain(db)
    application_event_count = (
        db.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.application_id == application.id)
        )
        or 0
    )
    latest_event = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.application_id == application.id)
        .order_by(AuditEvent.sequence.desc())
        .limit(1)
    )

    checklist_items = []
    for item in application.checklist_items:
        checklist_items.append(
            {
                "code": item.code,
                "title": item.title,
                "required": item.required,
                "status": item.status.value,
                "has_document": item.document_id is not None,
                "has_justification": bool(item.justification),
                "accepted_document_types": item.accepted_document_types or [],
            }
        )

    document_rows = []
    for document in documents:
        version = document.current_version
        extraction = extractions.get(str(document.current_version_id)) if document.current_version_id else None
        document_rows.append(
            {
                "document_type": document.document_type.value,
                "status": document.status.value,
                "version": {
                    "version_no": version.version_no,
                    "original_filename": version.original_filename,
                    "mime_type": version.mime_type,
                    "size_bytes": version.size_bytes,
                    "sha256": version.sha256,
                    "page_count": version.page_count,
                    "uploaded_at": _iso(version.uploaded_at),
                }
                if version
                else None,
                "extraction": {
                    "status": extraction.status.value,
                    "error_code": extraction.error_code,
                    "page_count": extraction.page_count,
                    "extractor_version": extraction.extractor_version,
                }
                if extraction
                else None,
            }
        )

    declaration = overview["declaration"]
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "generated_by": {"user_id": str(actor.id), "role": actor.role.value},
        "disclaimer": ADVISORY_LIMITATIONS[0],
        "application": {
            "id": str(application.id),
            "reference_no": application.reference_no,
            "status": application.status.value,
            "cycle": application.cycle,
            "category_code": application.category.code,
            "submitted_at": _iso(application.submitted_at),
            "created_at": _iso(application.created_at),
            "version": application.version,
            "institution": {
                "id": str(application.institution_id),
                "legal_name": application.institution.legal_name if application.institution else None,
                "aicte_permanent_id": application.institution.aicte_permanent_id
                if application.institution
                else None,
                "synthetic": application.institution.synthetic if application.institution else None,
            },
        },
        "declaration": {
            "verified": False,
            "version": declaration.version,
            "updated_at": _iso(declaration.updated_at),
            "affiliation_number": declaration.affiliation_number,
            "affiliation_valid_until": _iso(declaration.affiliation_valid_until),
            "programmes": declaration.programmes,
            "faculty_count": declaration.faculty_count,
            "previous_approval_reference": declaration.previous_approval_reference,
            "note": "Applicant-supplied and never verified. Compared with documents and synthetic records only.",
        }
        if declaration
        else None,
        "checklist": {
            "counts": {
                "total": len(checklist_items),
                "required": sum(1 for item in checklist_items if item["required"]),
                "satisfied": sum(1 for item in checklist_items if item["status"] == "SATISFIED"),
                "pending": sum(1 for item in checklist_items if item["status"] == "PENDING"),
            },
            "items": checklist_items,
        },
        "documents": document_rows,
        "latest_validation_run": {
            "id": str(run.id),
            "status": run.status.value,
            "engine_version": run.engine_version,
            "started_at": _iso(run.started_at),
            "completed_at": _iso(run.completed_at),
            "summary": run.summary,
            "findings": [_finding_payload(finding) for finding in run.findings],
        }
        if run
        else None,
        "technical_inspections": [
            {
                "adapter_code": item.adapter_code,
                "document_version_id": str(item.document_version_id),
                "status": item.status.value,
                "state": (item.evidence or {}).get("state"),
                "message": item.message,
                "advisory_only": (item.evidence or {}).get("advisory_only", True),
                "cryptographically_verified": (item.evidence or {}).get(
                    "cryptographically_verified", False
                ),
                "created_at": _iso(item.created_at),
            }
            for item in overview["technical_verifications"]
        ],
        "issuer_verifications": [
            {
                "adapter_code": item.adapter_code,
                "status": item.status.value,
                "simulated_source": item.simulated_source,
                "message": item.message,
                "created_at": _iso(item.created_at),
            }
            for item in overview["issuer_verifications"]
        ],
        "anomaly_signals": [
            {
                "signal_code": signal.signal_code,
                "severity": signal.severity.value,
                "score": float(signal.score) if signal.score is not None else None,
                "message": signal.message,
                "advisory_only": True,
            }
            for signal in overview["anomaly_signals"]
        ],
        "infrastructure_assessment": overview["infrastructure_assessment"],
        "alerts": [
            {
                "alert_type": alert.alert_type.value,
                "status": alert.status.value,
                "disposition": alert.disposition,
                "title": alert.title,
                "message": alert.message,
                "created_at": _iso(alert.created_at),
                "resolved_at": _iso(alert.resolved_at),
                "resolution_note": (alert.payload or {}).get("resolution_note"),
            }
            for alert in overview["alerts"]
        ],
        "review_actions": [
            {
                "action_type": action.action_type.value,
                "note": action.note,
                "from_status": action.from_status.value if action.from_status else None,
                "to_status": action.to_status.value if action.to_status else None,
                "actor_id": str(action.actor_id) if action.actor_id else None,
                "created_at": _iso(action.created_at),
            }
            for action in overview["review_actions"]
        ],
        "decisions": [
            {
                "decision_type": decision.decision_type.value,
                "rationale": decision.rationale,
                "conditions": decision.conditions,
                "decided_by": str(decision.decided_by) if decision.decided_by else None,
                "decided_at": _iso(decision.decided_at),
            }
            for decision in overview["decisions"]
        ],
        "audit": {
            "chain_valid": chain["valid"],
            "chain_event_count": chain["event_count"],
            "broken_sequence": chain["broken_sequence"],
            "application_event_count_at_export": application_event_count,
            "latest_application_event_hash": latest_event.event_hash if latest_event else None,
            "latest_application_event_sequence": latest_event.sequence if latest_event else None,
        },
        "limitations": list(ADVISORY_LIMITATIONS),
    }


def _md_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    application = report["application"]
    lines: list[str] = []
    lines.append(f"# Application report — {application['reference_no']}")
    lines.append("")
    lines.append(f"- Report version: `{report['report_version']}`")
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Generated by role: `{report['generated_by']['role']}`")
    lines.append(f"- Status: `{application['status']}` · cycle `{application['cycle']}`")
    lines.append(f"- Institution: {_md_text(application['institution']['legal_name'])}")
    lines.append("")
    lines.append(f"> {report['disclaimer']}")
    lines.append("")

    lines.append("## Structured declaration")
    declaration = report["declaration"]
    if not declaration:
        lines.append("_No declaration saved._")
    else:
        lines.append("Applicant-supplied; never verified by the system.")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        for key in (
            "affiliation_number",
            "affiliation_valid_until",
            "faculty_count",
            "previous_approval_reference",
        ):
            lines.append(f"| {key} | {_md_text(declaration.get(key))} |")
        programmes = declaration.get("programmes") or []
        lines.append(f"| programmes | {_md_text(len(programmes))} declared |")
    lines.append("")

    lines.append("## Checklist")
    counts = report["checklist"]["counts"]
    lines.append(
        f"{counts['satisfied']}/{counts['total']} satisfied · {counts['pending']} pending · "
        f"{counts['required']} required"
    )
    lines.append("")
    lines.append("| Code | Required | Status | Evidence |")
    lines.append("|---|---|---|---|")
    for item in report["checklist"]["items"]:
        evidence = "document" if item["has_document"] else ("justification" if item["has_justification"] else "none")
        lines.append(
            f"| {_md_text(item['code'])} | {'yes' if item['required'] else 'no'} | "
            f"{item['status']} | {evidence} |"
        )
    lines.append("")

    lines.append("## Documents")
    if not report["documents"]:
        lines.append("_No documents attached._")
    else:
        lines.append("| Type | Status | Version | SHA-256 | Extraction |")
        lines.append("|---|---|---|---|---|")
        for document in report["documents"]:
            version = document["version"] or {}
            extraction = document["extraction"] or {}
            lines.append(
                f"| {document['document_type']} | {document['status']} | "
                f"v{_md_text(version.get('version_no'))} | `{_md_text((version.get('sha256') or '')[:16])}…` | "
                f"{_md_text(extraction.get('status', 'none'))} |"
            )
    lines.append("")

    lines.append("## Latest validation run")
    run = report["latest_validation_run"]
    if not run:
        lines.append("_No validation run exists._")
    else:
        lines.append(
            f"Engine `{run['engine_version']}` · completed `{run['completed_at']}` · "
            f"status `{run['status']}`"
        )
        summary_counts = (run.get("summary") or {}).get("counts", {})
        if summary_counts:
            lines.append("")
            lines.append(
                "Counts: "
                + " · ".join(f"{key} {value}" for key, value in sorted(summary_counts.items()))
            )
        lines.append("")
        lines.append("| Rule | Outcome | Severity | Message |")
        lines.append("|---|---|---|---|")
        for finding in run["findings"]:
            lines.append(
                f"| {_md_text(finding['code'])} | {finding['outcome']} | "
                f"{finding['severity']} | {_md_text(finding['message'])} |"
            )
    lines.append("")

    lines.append("## Technical inspection (advisory)")
    if not report["technical_inspections"]:
        lines.append("_No technical inspection recorded._")
    else:
        lines.append("| Adapter | State | Cryptographically verified | Message |")
        lines.append("|---|---|---|---|")
        for item in report["technical_inspections"]:
            lines.append(
                f"| {item['adapter_code']} | {_md_text(item['state'])} | "
                f"{'yes' if item['cryptographically_verified'] else 'no'} | {_md_text(item['message'])} |"
            )
    lines.append("")

    lines.append("## Alerts")
    if not report["alerts"]:
        lines.append("_No alerts._")
    else:
        lines.append("| Type | Status | Disposition | Message |")
        lines.append("|---|---|---|---|")
        for alert in report["alerts"]:
            lines.append(
                f"| {alert['alert_type']} | {alert['status']} | "
                f"{_md_text(alert.get('disposition') or '—')} | {_md_text(alert['message'])} |"
            )
    lines.append("")

    lines.append("## Human review")
    if not report["review_actions"] and not report["decisions"]:
        lines.append("_No review actions or decisions recorded._")
    else:
        for action in report["review_actions"]:
            lines.append(f"- {action['created_at']} · `{action['action_type']}` · {_md_text(action['note'])}")
        for decision in report["decisions"]:
            lines.append(
                f"- **{decision['decision_type']}** at {decision['decided_at']} · "
                f"{_md_text(decision['rationale'])}"
            )
    lines.append("")

    lines.append("## Audit")
    audit = report["audit"]
    lines.append(
        f"- Hash chain valid: `{audit['chain_valid']}` ({audit['chain_event_count']} events)"
    )
    lines.append(f"- Latest application event sequence: `{audit['latest_application_event_sequence']}`")
    lines.append(f"- Latest application event hash: `{audit['latest_application_event_hash']}`")
    lines.append("")

    lines.append("## Limitations")
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{_e(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    if not rows:
        body = f'<tr><td colspan="{len(headers)}" class="empty">None recorded.</td></tr>'
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def render_html(report: dict[str, Any]) -> str:
    application = report["application"]
    declaration = report["declaration"]
    run = report["latest_validation_run"]
    counts = report["checklist"]["counts"]
    audit = report["audit"]

    sections: list[str] = []
    sections.append(
        "<h2>Structured declaration</h2>"
        + (
            '<p class="muted">Applicant-supplied; never verified by the system.</p>'
            + _table(
                ["Field", "Value"],
                [
                    ["affiliation_number", declaration.get("affiliation_number")],
                    ["affiliation_valid_until", declaration.get("affiliation_valid_until")],
                    ["faculty_count", declaration.get("faculty_count")],
                    ["previous_approval_reference", declaration.get("previous_approval_reference")],
                    ["programmes", f"{len(declaration.get('programmes') or [])} declared"],
                ],
            )
            if declaration
            else "<p>No declaration saved.</p>"
        )
    )

    sections.append(
        "<h2>Checklist</h2>"
        f"<p>{counts['satisfied']}/{counts['total']} satisfied · {counts['pending']} pending · "
        f"{counts['required']} required</p>"
        + _table(
            ["Code", "Required", "Status", "Evidence"],
            [
                [
                    item["code"],
                    "yes" if item["required"] else "no",
                    item["status"],
                    "document" if item["has_document"] else ("justification" if item["has_justification"] else "none"),
                ]
                for item in report["checklist"]["items"]
            ],
        )
    )

    sections.append(
        "<h2>Documents</h2>"
        + _table(
            ["Type", "Status", "Version", "SHA-256", "Extraction"],
            [
                [
                    document["document_type"],
                    document["status"],
                    f"v{(document['version'] or {}).get('version_no')}",
                    (document["version"] or {}).get("sha256"),
                    (document["extraction"] or {}).get("status", "none"),
                ]
                for document in report["documents"]
            ],
        )
    )

    if run:
        summary_counts = (run.get("summary") or {}).get("counts", {})
        findings = _table(
            ["Rule", "Outcome", "Severity", "Message"],
            [
                [finding["code"], finding["outcome"], finding["severity"], finding["message"]]
                for finding in run["findings"]
            ],
        )
        sections.append(
            "<h2>Latest validation run</h2>"
            f"<p>Engine <code>{_e(run['engine_version'])}</code> · completed "
            f"<code>{_e(run['completed_at'])}</code> · status <code>{_e(run['status'])}</code></p>"
            + (
                "<p>"
                + _e(" · ".join(f"{key} {value}" for key, value in sorted(summary_counts.items())))
                + "</p>"
                if summary_counts
                else ""
            )
            + findings
        )
    else:
        sections.append("<h2>Latest validation run</h2><p>No validation run exists.</p>")

    sections.append(
        "<h2>Technical inspection (advisory)</h2>"
        + _table(
            ["Adapter", "State", "Cryptographically verified", "Message"],
            [
                [
                    item["adapter_code"],
                    item["state"],
                    "yes" if item["cryptographically_verified"] else "no",
                    item["message"],
                ]
                for item in report["technical_inspections"]
            ],
        )
    )

    sections.append(
        "<h2>Alerts</h2>"
        + _table(
            ["Type", "Status", "Disposition", "Message"],
            [
                [
                    alert["alert_type"],
                    alert["status"],
                    alert.get("disposition") or "—",
                    alert["message"],
                ]
                for alert in report["alerts"]
            ],
        )
    )

    review_rows = [
        [action["created_at"], action["action_type"], action["note"]]
        for action in report["review_actions"]
    ] + [
        [decision["decided_at"], decision["decision_type"], decision["rationale"]]
        for decision in report["decisions"]
    ]
    sections.append("<h2>Human review</h2>" + _table(["When", "Action", "Rationale/note"], review_rows))

    sections.append(
        "<h2>Audit</h2>"
        f"<p>Hash chain valid: <code>{_e(audit['chain_valid'])}</code> "
        f"({_e(audit['chain_event_count'])} events). Latest application event: "
        f"<code>{_e(audit['latest_application_event_sequence'])}</code> · "
        f"<code>{_e(audit['latest_application_event_hash'])}</code></p>"
    )

    limitations = "".join(f"<li>{_e(item)}</li>" for item in report["limitations"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Application report {_e(application['reference_no'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 980px; color: #111; line-height: 1.45; }}
  h1 {{ margin-bottom: 0.25rem; }}
  h2 {{ margin-top: 2rem; border-bottom: 1px solid #ccc; padding-bottom: 0.25rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0.5rem 0 1rem; font-size: 0.86rem; }}
  th, td {{ border: 1px solid #bbb; padding: 0.35rem 0.45rem; text-align: left; vertical-align: top; }}
  th {{ background: #eee; }}
  .muted {{ color: #555; }}
  .empty {{ color: #666; font-style: italic; }}
  .banner {{ border: 2px solid #a05a00; background: #fff4e0; padding: 0.75rem 1rem; margin: 1rem 0; }}
  code {{ word-break: break-all; }}
  @media print {{ body {{ margin: 0.5cm; max-width: none; }} }}
</style>
</head>
<body>
<h1>Application report — {_e(application['reference_no'])}</h1>
<p class="muted">
  Report version <code>{_e(report['report_version'])}</code> · generated
  <code>{_e(report['generated_at'])}</code> · by role <code>{_e(report['generated_by']['role'])}</code>
</p>
<p>
  Status <code>{_e(application['status'])}</code> · cycle <code>{_e(application['cycle'])}</code> ·
  institution {_e(application['institution']['legal_name'])}
  {_e('(synthetic)' if application['institution']['synthetic'] else '')}
</p>
<div class="banner"><strong>Prototype review aid.</strong> {_e(report['disclaimer'])}</div>
{''.join(sections)}
<h2>Limitations</h2>
<ul>{limitations}</ul>
<p class="muted">Generated by the AICTE compliance prototype. Not an official AICTE document.</p>
</body>
</html>
"""


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, default=str)


REPORT_FORMATS: dict[str, tuple[str, str]] = {
    "json": ("application/json", "json"),
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "html": ("text/html; charset=utf-8", "html"),
}
_RENDERERS = {
    "json": render_json,
    "markdown": render_markdown,
    "html": render_html,
}


def export_application_report(
    db: Session,
    application: Application,
    *,
    actor: User,
    report_format: str = "json",
) -> tuple[str, str, str]:
    """Build, render, and audit one report export.

    Returns ``(body, media_type, filename)``. The audit event is committed with
    the export so that generating a report is attributable and visible in the
    hash chain.
    """
    if report_format not in _RENDERERS:
        raise ValueError(f"Unsupported report format: {report_format}")
    report = build_application_report(db, application, actor=actor)
    body = _RENDERERS[report_format](report)
    media_type, extension = REPORT_FORMATS[report_format]
    run = report["latest_validation_run"] or {}
    record_audit(
        db,
        event_type="application.report_exported",
        actor=actor,
        application_id=application.id,
        entity_type="application",
        entity_id=application.id,
        payload={
            "format": report_format,
            "report_version": REPORT_VERSION,
            "finding_count": len(run.get("findings") or []),
        },
    )
    db.commit()
    return body, media_type, f"{application.reference_no}-report.{extension}"
