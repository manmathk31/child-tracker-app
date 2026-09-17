"""Pydantic schemas for Wi-Fi Access Point registration and management."""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

BSSID_REGEX = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"


class AccessPointBase(BaseModel):
    """Common attributes for access points."""

    name: str = Field(..., min_length=1, max_length=128, description="Human-readable AP label")
    bssid: str = Field(
        ...,
        pattern=BSSID_REGEX,
        description="Access point MAC address (e.g. AA:BB:CC:DD:EE:FF)",
    )
    channel: Optional[int] = Field(None, ge=1, le=165, description="Wi-Fi channel (1-165)")
    zone_id: Optional[uuid.UUID] = Field(None, description="Physical zone containing this access point")

    @field_validator("bssid")
    @classmethod
    def normalize_bssid(cls, v: str) -> str:
        """Normalize BSSID to uppercase colon-separated format."""
        clean = v.replace("-", ":").upper()
        return clean


class AccessPointCreate(AccessPointBase):
    """Schema for registering a new access point."""

    pass


class AccessPointUpdate(BaseModel):
    """Schema for updating an existing access point."""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    bssid: Optional[str] = Field(None, pattern=BSSID_REGEX)
    channel: Optional[int] = Field(None, ge=1, le=165)
    zone_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None

    @field_validator("bssid")
    @classmethod
    def normalize_bssid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.replace("-", ":").upper()
        return v


class AccessPointResponse(AccessPointBase):
    """Public representation of an access point."""

    id: uuid.UUID
    zone_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
