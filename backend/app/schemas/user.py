"""Pydantic schemas for user accounts and authentication."""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole

EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


class UserBase(BaseModel):
    """Base schema attributes shared across user models."""

    email: str = Field(..., pattern=EMAIL_REGEX, description="User email address")
    full_name: str = Field(..., min_length=2, max_length=255, description="Full legal or professional name")
    role: UserRole = Field(default=UserRole.TEACHER, description="Assigned role: admin or teacher")


class UserCreate(UserBase):
    """Schema for administrator creating a new user account."""

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plaintext password (minimum 8 characters)",
    )


class UserUpdate(BaseModel):
    """Schema for updating user details."""

    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class UserResponse(UserBase):
    """Public representation of a user account."""

    id: uuid.UUID
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """JSON login request payload."""

    email: str = Field(..., pattern=EMAIL_REGEX)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Authentication success payload containing JWT token."""

    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserResponse
