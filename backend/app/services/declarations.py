from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationDeclaration, User
from app.schemas.phase3 import DeclarationUpsert
from app.services.audit import record_audit


def get_declaration(db: Session, application_id: uuid.UUID) -> ApplicationDeclaration | None:
    return db.scalar(
        select(ApplicationDeclaration).where(
            ApplicationDeclaration.application_id == application_id
        )
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_programmes(payload: DeclarationUpsert) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for programme in payload.programmes:
        code = programme.code.strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        items.append(
            {
                "code": code,
                "name": _clean(programme.name),
                "level": _clean(programme.level),
                "intake": programme.intake,
            }
        )
    return items


def upsert_declaration(
    db: Session,
    application: Application,
    user: User,
    payload: DeclarationUpsert,
) -> ApplicationDeclaration:
    """Create or replace the applicant's declared facts.

    The router has already checked ownership and draft state. Every write is
    audited; the declaration is applicant-supplied and never treated as
    verified data.
    """

    declaration = get_declaration(db, application.id)
    programmes = _normalize_programmes(payload)
    changed: list[str] = []
    before_version = declaration.version if declaration else None

    if declaration is None:
        declaration = ApplicationDeclaration(
            application_id=application.id,
            declared_by=user.id,
            version=1,
        )
        db.add(declaration)
        changed = [
            "affiliation_number",
            "affiliation_valid_until",
            "programmes",
            "total_intake",
            "faculty_count",
            "previous_approval_reference",
        ]
    else:
        declaration.version += 1
        declaration.declared_by = user.id

    values = {
        "affiliation_number": _clean(payload.affiliation_number),
        "affiliation_valid_until": payload.affiliation_valid_until,
        "programmes": programmes,
        "total_intake": payload.total_intake,
        "faculty_count": payload.faculty_count,
        "previous_approval_reference": _clean(payload.previous_approval_reference),
    }
    for field, value in values.items():
        if getattr(declaration, field) != value:
            setattr(declaration, field, value)
            if field not in changed:
                changed.append(field)

    db.flush()
    record_audit(
        db,
        event_type="application.declaration_saved",
        actor=user,
        application_id=application.id,
        entity_type="application_declaration",
        entity_id=declaration.id,
        payload={
            "version": declaration.version,
            "previous_version": before_version,
            "declared_by": str(user.id),
            "changed_fields": changed,
            "programme_codes": [item["code"] for item in programmes],
            "advisory": True,
        },
    )
    db.commit()
    db.refresh(declaration)
    return declaration
