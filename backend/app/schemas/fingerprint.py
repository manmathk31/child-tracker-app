"""Pydantic schemas for Wi-Fi RSSI fingerprint collection, filtering, and calibration."""

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.fingerprint import FingerprintStatus

BSSID_REGEX = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"


class ScanSampleIn(BaseModel):
    """Single Wi-Fi Access Point observation from a hardware scan."""

    bssid: str = Field(..., description="Access point MAC address (e.g. AA:BB:CC:DD:EE:FF)")
    rssi: int = Field(..., ge=-100, le=0, description="Received signal strength in dBm (-100 to 0)")
    channel: Optional[int] = Field(None, ge=1, le=165, description="Wi-Fi channel")

    @field_validator("bssid")
    @classmethod
    def normalize_bssid(cls, v: str) -> str:
        """Normalize BSSID to uppercase colon-separated format."""
        return v.replace("-", ":").upper()


class CalibrationBatchIn(BaseModel):
    """Batch of Wi-Fi scan readings transmitted automatically by an ESP32 or test tool."""

    device_id: Optional[str] = Field(None, description="Optional calibration hardware identifier")
    scan: List[ScanSampleIn] = Field(..., min_length=1, description="List of observed AP signals")


class FingerprintCreate(BaseModel):
    """Payload to initiate a new calibration survey session for a zone."""

    zone_id: uuid.UUID = Field(..., description="Zone where survey is being conducted")
    min_rssi_cutoff: int = Field(-85, ge=-100, le=-30, description="Signals below this dBm are discarded as noise")
    target_ap_ids: Optional[List[uuid.UUID]] = Field(
        default=None,
        description="Optional list of specific Access Points to whitelist. If empty, all registered APs are included.",
    )
    notes: Optional[str] = Field(None, max_length=1000, description="Optional calibration notes")


class FingerprintUpdate(BaseModel):
    """Payload to update survey notes or cutoff thresholds."""

    notes: Optional[str] = Field(None, max_length=1000)
    min_rssi_cutoff: Optional[int] = Field(None, ge=-100, le=-30)


class FingerprintAPStatResponse(BaseModel):
    """Statistical distribution metrics for a single Access Point in a fingerprint."""

    id: uuid.UUID
    access_point_id: uuid.UUID
    access_point_name: Optional[str] = None
    access_point_bssid: Optional[str] = None
    median_rssi: float
    mean_rssi: float
    stddev_rssi: float
    sample_count: int

    model_config = ConfigDict(from_attributes=True)


class FingerprintResponse(BaseModel):
    """Public representation of a fingerprint survey header."""

    id: uuid.UUID
    zone_id: uuid.UUID
    zone_name: Optional[str] = None
    created_by: uuid.UUID
    creator_name: Optional[str] = None
    sample_count: int
    quality_score: Optional[float] = None
    min_rssi_cutoff: int
    status: FingerprintStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FingerprintDetailResponse(FingerprintResponse):
    """Detailed fingerprint report including AP statistical summaries."""

    ap_stats: List[FingerprintAPStatResponse] = []
