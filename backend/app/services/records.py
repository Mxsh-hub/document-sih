from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AccreditationRecord,
    ApprovalHistory,
    ComplianceDeficiency,
    FacultyRecord,
    NocPermission,
    Programme,
    TerPayment,
)
from app.services.authorization import require_staff_access
from app.db.models import User

SYNTHETIC_SOURCE = "synthetic-aicte-records-v1"

RECORD_MODELS = {
    "approvals": ApprovalHistory,
    "programmes": Programme,
    "faculty": FacultyRecord,
    "deficiencies": ComplianceDeficiency,
    "ter": TerPayment,
    "accreditations": AccreditationRecord,
    "nocs": NocPermission,
}


def _value_to_json(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _serialize(row: Any) -> dict[str, Any]:
    return {column.name: _value_to_json(getattr(row, column.name)) for column in row.__table__.columns}


def get_record_group(db: Session, institution_id: uuid.UUID, record_type: str) -> dict[str, Any]:
    model = RECORD_MODELS.get(record_type)
    if model is None:
        raise ApiError(404, "NOT_FOUND", "Unknown institutional record type.")
    rows = list(
        db.scalars(
            select(model)
            .where(model.institution_id == institution_id)
            .order_by(model.retrieved_at.desc())
        )
    )
    retrieved_at = max((row.retrieved_at for row in rows), default=None)
    return {
        "source": SYNTHETIC_SOURCE,
        "synthetic": True,
        "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
        "items": [_serialize(row) for row in rows],
    }


def get_record_bundle(db: Session, institution_id: uuid.UUID) -> dict[str, Any]:
    records = {name: get_record_group(db, institution_id, name) for name in RECORD_MODELS}
    retrieved_values = [
        datetime.fromisoformat(group["retrieved_at"])
        for group in records.values()
        if group["retrieved_at"]
    ]
    retrieved_at = max(retrieved_values, default=None)
    return {
        "institution_id": str(institution_id),
        "source": SYNTHETIC_SOURCE,
        "synthetic": True,
        "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
        "records": records,
    }


def get_records_for_staff(
    db: Session, actor: User, institution_id: uuid.UUID, record_type: str | None = None
) -> dict[str, Any]:
    require_staff_access(actor)
    if record_type:
        return get_record_group(db, institution_id, record_type)
    return get_record_bundle(db, institution_id)
