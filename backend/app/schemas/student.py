"""Pydantic schemas for student enrollment and profile management."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.zone import ZoneResponse


class StudentBase(BaseModel):
    """Common attributes for students."""

    student_code: str = Field(..., min_length=1, max_length=64, description="School-assigned identifier (e.g. STU-1001)")
    full_name: str = Field(..., min_length=1, max_length=255, description="Student full name")
    class_name: str = Field(..., min_length=1, max_length=64, description="Class or section (e.g. Grade 3A)")
    age: int = Field(..., ge=2, le=25, description="Student age in years")
    photo_url: Optional[str] = Field(None, max_length=512, description="Optional portrait photo URL")


class StudentCreate(StudentBase):
    """Schema for creating a new student profile."""

    device_id: Optional[uuid.UUID] = Field(None, description="Optional wearable hardware tag to assign")
    allowed_zone_ids: List[uuid.UUID] = Field(default_factory=list, description="List of authorized zone IDs")


class StudentUpdate(BaseModel):
    """Schema for modifying a student profile."""

    student_code: Optional[str] = Field(None, min_length=1, max_length=64)
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    class_name: Optional[str] = Field(None, min_length=1, max_length=64)
    age: Optional[int] = Field(None, ge=2, le=25)
    photo_url: Optional[str] = Field(None, max_length=512)
    device_id: Optional[uuid.UUID] = None
    allowed_zone_ids: Optional[List[uuid.UUID]] = None
    is_active: Optional[bool] = None


class StudentResponse(StudentBase):
    """Public representation of an enrolled student."""

    id: uuid.UUID
    is_active: bool
    device_id: Optional[uuid.UUID] = None
    device_code: Optional[str] = None
    device_battery: Optional[int] = None
    allowed_zones: List[ZoneResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
