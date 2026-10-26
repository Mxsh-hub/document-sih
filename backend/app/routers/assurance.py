from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.db.base import get_db
from app.db.enums import Role
from app.db.models import User
from app.schemas.phase3 import (
    AnomalySignalOut,
    InfrastructureAssessmentOut,
    InfrastructureEvidenceCreate,
    InfrastructureEvidenceOut,
)
from app.services.audit import record_audit
from app.services.assurance import (
    infrastructure_assessment,
    list_anomalies,
    list_infrastructure_evidence,
    register_infrastructure_evidence,
    scan_anomalies,
)
from app.services.authorization import get_application_or_404

router = APIRouter(tags=["Application Assurance"])


@router.post(
    "/applications/{application_id}/anomaly-scan",
    response_model=list[AnomalySignalOut],
)
def run_anomaly_scan(
    application_id: uuid.UUID,
    user: Annotated[User, Depends(require_roles(Role.REVIEWER, Role.APPROVER, Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    signals = scan_anomalies(db, application)
    record_audit(
        db,
        event_type="anomaly.scan_completed",
        actor=user,
        application_id=application.id,
        entity_type="application",
        entity_id=application.id,
        payload={"signal_count": len(signals), "advisory_only": True},
    )
    db.commit()
    return [AnomalySignalOut.model_validate(item) for item in signals]


@router.get(
    "/applications/{application_id}/anomaly-signals",
    response_model=list[AnomalySignalOut],
)
def get_anomaly_signals(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    get_application_or_404(db, application_id, user)
    return [AnomalySignalOut.model_validate(item) for item in list_anomalies(db, application_id)]


@router.post(
    "/applications/{application_id}/infrastructure-evidence",
    response_model=InfrastructureEvidenceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_infrastructure_evidence(
    application_id: uuid.UUID,
    payload: InfrastructureEvidenceCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    evidence = register_infrastructure_evidence(
        db,
        application=application,
        actor=user,
        evidence_type=payload.evidence_type,
        document_version_id=payload.document_version_id,
        label=payload.label,
        description=payload.description,
        captured_at=payload.captured_at,
        metadata=payload.metadata,
    )
    return InfrastructureEvidenceOut.model_validate(evidence)


@router.get(
    "/applications/{application_id}/infrastructure-evidence",
    response_model=list[InfrastructureEvidenceOut],
)
def get_infrastructure_evidence(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    get_application_or_404(db, application_id, user)
    return [
        InfrastructureEvidenceOut.model_validate(item)
        for item in list_infrastructure_evidence(db, application_id)
    ]


@router.get(
    "/applications/{application_id}/infrastructure-assessment",
    response_model=InfrastructureAssessmentOut,
)
def get_infrastructure_assessment(
    application_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    application = get_application_or_404(db, application_id, user)
    return InfrastructureAssessmentOut.model_validate(infrastructure_assessment(db, application))
