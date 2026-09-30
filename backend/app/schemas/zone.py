"""Pydantic schemas for school zone management."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ZoneBase(BaseModel):
    """Common attributes for zones."""

    name: str = Field(..., min_length=1, max_length=128, description="Unique zone name (e.g. Classroom 3A)")
    description: Optional[str] = Field(None, description="Optional description of zone usage")
    building: Optional[str] = Field(None, max_length=64, description="Building identifier or name")
    floor: Optional[str] = Field(None, max_length=32, description="Floor identifier (e.g. 1st Floor)")


class ZoneCreate(ZoneBase):
    """Schema for creating a new zone."""

    pass


class ZoneUpdate(BaseModel):
    """Schema for updating an existing zone."""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    building: Optional[str] = Field(None, max_length=64)
    floor: Optional[str] = Field(None, max_length=32)
    is_active: Optional[bool] = None


class ZoneResponse(ZoneBase):
    """Public representation of a school zone."""

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    scanner_devices_count: int = 0

    model_config = ConfigDict(from_attributes=True)
