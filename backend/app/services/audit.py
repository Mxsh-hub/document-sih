from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AuditActorType
from app.db.models import AuditEvent, User


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def record_audit(
    db: Session,
    *,
    event_type: str,
    actor: User | None,
    entity_type: str,
    entity_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
    application_id: uuid.UUID | None = None,
    actor_type: AuditActorType | None = None,
) -> AuditEvent:
    previous = db.scalar(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1))
    sequence = (previous.sequence + 1) if previous else 1
    previous_hash = previous.event_hash if previous else None
    created_at = datetime.now(timezone.utc)
    body = {
        "sequence": sequence,
        "event_type": event_type,
        "actor_type": (actor_type or (AuditActorType.USER if actor else AuditActorType.SYSTEM)).value,
        "actor_id": str(actor.id) if actor else None,
        "application_id": str(application_id) if application_id else None,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "payload": payload or {},
        "created_at": created_at.isoformat(),
    }
    event_hash = hashlib.sha256((previous_hash or "").encode() + _canonical(body)).hexdigest()
    event = AuditEvent(
        sequence=sequence,
        event_type=event_type,
        actor_type=AuditActorType(body["actor_type"]),
        actor_id=actor.id if actor else None,
        application_id=application_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        previous_hash=previous_hash,
        event_hash=event_hash,
        created_at=created_at,
    )
    db.add(event)
    db.flush()
    return event


def verify_audit_chain(db: Session) -> dict[str, Any]:
    events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.sequence.asc())))
    previous_hash: str | None = None
    for event in events:
        body = {
            "sequence": event.sequence,
            "event_type": event.event_type,
            "actor_type": event.actor_type.value,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "application_id": str(event.application_id) if event.application_id else None,
            "entity_type": event.entity_type,
            "entity_id": str(event.entity_id) if event.entity_id else None,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }
        expected = hashlib.sha256((previous_hash or "").encode() + _canonical(body)).hexdigest()
        if event.previous_hash != previous_hash or event.event_hash != expected:
            return {
                "valid": False,
                "event_count": len(events),
                "broken_sequence": event.sequence,
            }
        previous_hash = event.event_hash
    return {"valid": True, "event_count": len(events), "broken_sequence": None}
