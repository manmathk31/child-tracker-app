"""Common shared Pydantic schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Schema for application health check endpoint response."""

    status: Literal["healthy", "degraded"] = Field(
        ..., description="Overall system health status"
    )
    database: Literal["connected", "disconnected"] = Field(
        ..., description="Database connectivity state"
    )
    version: str = Field(..., description="Application version")
    app_name: str = Field(..., description="Application name")
    environment: str = Field(..., description="Running environment")
    timestamp: datetime = Field(..., description="Current UTC timestamp")

    model_config = ConfigDict(from_attributes=True)
