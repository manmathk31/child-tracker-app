"""Pydantic schemas for safety alerts and notification payloads."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.alert import AlertSeverity, AlertStatus, AlertType


class AlertResponse(BaseModel):
    """Public representation of an active or historical safety alert."""

    id: uuid.UUID
    student_id: uuid.UUID | None = None
    student_name: str | None = None
    device_id: uuid.UUID | None = None
    device_code: str | None = None
    zone_id: uuid.UUID | None = None
    zone_name: str | None = None
    type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    message: str
    created_at: datetime
    acknowledged_by: uuid.UUID | None = None
    acknowledged_by_name: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AlertCountResponse(BaseModel):
    """Count response for top-navigation bell badge."""

    count: int = Field(..., ge=0, description="Total active, unacknowledged safety alerts")


class AlertAcknowledgeIn(BaseModel):
    """Payload to acknowledge an active safety alert."""

    notes: str | None = Field(
        None, max_length=500, description="Optional resolution or triage notes"
    )
