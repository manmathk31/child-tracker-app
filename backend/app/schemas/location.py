"""Pydantic schemas for telemetry ingestion, live positioning estimates, and location history."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

BSSID_REGEX = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"


class TelemetryScanItem(BaseModel):
    """Single Wi-Fi Access Point observation from ESP32 wearable."""

    bssid: str = Field(..., description="Access point BSSID / MAC address")
    rssi: int = Field(..., ge=-100, le=0, description="Signal strength in dBm (-100 to 0)")
    channel: int | None = Field(None, ge=1, le=165, description="Wi-Fi channel (1-165)")

    @field_validator("bssid")
    @classmethod
    def normalize_bssid(cls, v: str) -> str:
        return v.replace("-", ":").upper()


class TelemetryIngestIn(BaseModel):
    """Payload sent by wearable device per ESP32_PROTOCOL.md."""

    device_id: str = Field(..., description="Hardware identifier etched on casing or device_code")
    mac_address: str = Field(..., description="Wearable hardware MAC address")
    battery_percent: int = Field(..., ge=0, le=100, description="0 to 100 percentage")
    firmware_version: str | None = Field(None, description="Installed firmware version")
    scan: list[TelemetryScanItem] = Field(..., description="Wi-Fi APs detected in scan")
    events: dict[str, Any] | None = Field(default_factory=dict, description="Hardware event flags")

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        return v.replace("-", ":").upper()


class TelemetryIngestResponse(BaseModel):
    """Ingestion acknowledgement response per ESP32_PROTOCOL.md."""

    status: str = Field("ack", description="Ingestion status")
    device_id: str = Field(..., description="Device identifier")
    assigned_zone: str | None = Field(
        None,
        description="Estimated zone name or null if unassigned/low confidence",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Localization confidence score (0.0 - 1.0)",
    )
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
