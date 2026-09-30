"""Pydantic schemas for the live safety monitoring dashboard and auto-refresh feeds."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.alert import AlertResponse


class DashboardMetrics(BaseModel):
    """High-level safety and attendance counts."""

    total_students: int = Field(0, ge=0, description="Total active enrolled students")
    trackable_students: int = Field(0, ge=0, description="Students with wearables online")
    attention_students: int = Field(
        0, ge=0, description="Students needing attention (low battery/offline/restricted)"
    )
    active_alerts_count: int = Field(0, ge=0, description="Count of unacknowledged safety alerts")


class OccupantSummary(BaseModel):
    """Compact summary of a student present in a physical room."""

    student_id: uuid.UUID
    full_name: str
    student_code: str
    class_name: str
    photo_url: str | None = None
    device_code: str | None = None
    battery_percent: int | None = None
    confidence: float = 0.0
    is_restricted: bool = False

    model_config = ConfigDict(from_attributes=True)


class ZoneOccupancy(BaseModel):
    """Real-time occupancy representation for a school room or designated area."""

    zone_id: uuid.UUID | None = None
    zone_name: str
    building: str | None = None
    floor: str | None = None
    occupant_count: int = Field(0, ge=0)
    has_restricted_student: bool = False
    occupants: list[OccupantSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class StudentLiveStatus(BaseModel):
    """Comprehensive real-time monitoring card representation for an enrolled student."""

    student_id: uuid.UUID
    full_name: str
    student_code: str
    class_name: str
    age: int
    photo_url: str | None = None
    device_id: uuid.UUID | None = None
    device_code: str | None = None
    battery_percent: int | None = None
    device_status: str
    current_zone_id: uuid.UUID | None = None
    current_zone_name: str | None = None
    confidence: float = 0.0
    last_seen_at: datetime | None = None
    is_restricted: bool = False
    status_level: str = "offline"

    model_config = ConfigDict(from_attributes=True)


class DashboardLiveResponse(BaseModel):
    """Consolidated payload delivered to frontend poller for real-time DOM updates."""

    timestamp: datetime
    metrics: DashboardMetrics
    zones: list[ZoneOccupancy] = Field(default_factory=list)
    roaming_zone: ZoneOccupancy
    students: list[StudentLiveStatus] = Field(default_factory=list)
    active_alerts: list[AlertResponse] = Field(default_factory=list)
