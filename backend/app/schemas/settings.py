"""Pydantic schemas for school metadata and alert threshold configurations."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SchoolSettingsUpdate(BaseModel):
    """Schema for updating organization-level settings."""

    school_name: Optional[str] = Field(None, min_length=1, max_length=255)
    building_name: Optional[str] = Field(None, min_length=1, max_length=255)
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)


class SchoolSettingsResponse(BaseModel):
    """Public representation of school settings."""

    id: uuid.UUID
    school_name: str
    building_name: str
    timezone: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertSettingsUpdate(BaseModel):
    """Schema for modifying system safety thresholds."""

    offline_threshold_minutes: Optional[int] = Field(None, ge=1, le=120)
    critical_offline_threshold_minutes: Optional[int] = Field(None, ge=1, le=240)
    low_battery_percent: Optional[int] = Field(None, ge=5, le=50)
    min_localization_confidence: Optional[float] = Field(None, ge=0.1, le=1.0)
    restricted_zone_alerts_enabled: Optional[bool] = None
    fall_detection_enabled: Optional[bool] = None
    sos_alerts_enabled: Optional[bool] = None


class AlertSettingsResponse(BaseModel):
    """Public representation of safety thresholds."""

    id: uuid.UUID
    offline_threshold_minutes: int
    critical_offline_threshold_minutes: int
    low_battery_percent: int
    min_localization_confidence: float
    restricted_zone_alerts_enabled: bool
    fall_detection_enabled: bool
    sos_alerts_enabled: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
