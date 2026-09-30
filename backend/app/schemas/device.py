"""Pydantic schemas for ESP32 wearable devices."""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.device import DeviceStatus, DeviceType

MAC_REGEX = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"


class DeviceBase(BaseModel):
    """Common attributes for wearable devices."""

    device_code: str = Field(..., min_length=1, max_length=64, description="Unique tag identifier (e.g. WB-001)")
    mac_address: str = Field(
        ...,
        pattern=MAC_REGEX,
        description="Wearable Wi-Fi MAC address (e.g. AA:BB:CC:DD:EE:FF)",
    )
    firmware_version: Optional[str] = Field(None, max_length=32, description="Installed firmware version")

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        return v.replace("-", ":").upper()


class DeviceCreate(DeviceBase):
    """Schema for registering a new wearable."""

    battery_percent: int = Field(default=100, ge=0, le=100, description="Initial battery percentage (0-100)")
    type: DeviceType = Field(default=DeviceType.WEARABLE, description="Type of ESP device")
    assigned_zone_id: Optional[uuid.UUID] = Field(None, description="Zone ID if type is SCANNER")


class DeviceUpdate(BaseModel):
    """Schema for updating wearable metadata or assigning to a student."""

    device_code: Optional[str] = Field(None, min_length=1, max_length=64)
    mac_address: Optional[str] = Field(None, pattern=MAC_REGEX)
    battery_percent: Optional[int] = Field(None, ge=0, le=100)
    firmware_version: Optional[str] = Field(None, max_length=32)
    student_id: Optional[uuid.UUID] = None
    type: Optional[DeviceType] = None
    assigned_zone_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.replace("-", ":").upper()
        return v


class DeviceResponse(DeviceBase):
    """Public representation of a wearable device."""

    id: uuid.UUID
    battery_percent: int
    last_seen_at: Optional[datetime] = None
    status: DeviceStatus
    student_id: Optional[uuid.UUID] = None
    student_name: Optional[str] = None
    type: DeviceType
    assigned_zone_id: Optional[uuid.UUID] = None
    assigned_zone_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
