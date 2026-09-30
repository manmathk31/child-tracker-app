"""Pydantic schemas for telemetry ingestion, live positioning estimates, and location history."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

BSSID_REGEX = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"


class TagObservation(BaseModel):
    """Single Wearable Tag observation from Master ESP."""

    mac: str = Field(..., description="Wearable hardware MAC address")
    rssi: int = Field(..., ge=-100, le=0, description="Signal strength in dBm (-100 to 0)")
    battery: int | None = Field(None, description="Battery percentage if available")
    sos: bool = Field(False, description="True if the tag is broadcasting an SOS emergency")

    @field_validator("mac")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        return v.replace("-", ":").upper()


class MasterTelemetryIngest(BaseModel):
    """Payload sent by Master ESP scanner."""

    scanner_mac: str = Field(..., description="Master ESP hardware MAC address")
    tags: list[TagObservation] = Field(..., description="Wearable tags detected in scan")

    @field_validator("scanner_mac")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        return v.replace("-", ":").upper()


class TelemetryIngestResponse(BaseModel):
    """Ingestion acknowledgement response per ESP32_PROTOCOL.md."""

    status: str = Field("ack", description="Ingestion status")
    scanner_mac: str = Field(..., description="Scanner identifier")
    processed_tags: int = Field(..., description="Number of tags successfully processed")
    server_time: datetime = Field(..., description="Server timestamp")


class LocationEstimate(BaseModel):
    """Indoor localization estimate computed by the localization service."""

    zone_id: uuid.UUID | None = None
    zone_name: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    is_low_confidence: bool = False
    distance_metrics: dict[str, float] = Field(default_factory=dict)


class LocationRecordResponse(BaseModel):
    """Historical position record response."""

    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str | None = None
    device_id: uuid.UUID
    device_code: str | None = None
    zone_id: uuid.UUID | None = None
    zone_name: str | None = None
    confidence: float
    raw_scan: dict[str, Any]
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentLiveLocationResponse(BaseModel):
    """Current live location and recent breadcrumbs for a student."""

    student_id: uuid.UUID
    student_name: str
    student_code: str
    device_id: uuid.UUID | None = None
    device_code: str | None = None
    device_status: str
    battery_percent: int | None = None
    last_seen_at: datetime | None = None
    current_zone_id: uuid.UUID | None = None
    current_zone_name: str | None = None
    confidence: float
    is_low_confidence: bool
    recent_breadcrumbs: list[LocationRecordResponse] = Field(default_factory=list)
