"""Pydantic schemas package."""

from app.schemas.access_point import (
    AccessPointCreate,
    AccessPointResponse,
    AccessPointUpdate,
)
from app.schemas.common import HealthResponse
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate
from app.schemas.fingerprint import (
    CalibrationBatchIn,
    FingerprintAPStatResponse,
    FingerprintCreate,
    FingerprintDetailResponse,
    FingerprintResponse,
    FingerprintUpdate,
    ScanSampleIn,
)
from app.schemas.location import (
    LocationEstimate,
    LocationRecordResponse,
    StudentLiveLocationResponse,
    TelemetryIngestIn,
    TelemetryIngestResponse,
    TelemetryScanItem,
)
from app.schemas.settings import (
    AlertSettingsResponse,
    AlertSettingsUpdate,
    SchoolSettingsResponse,
    SchoolSettingsUpdate,
)
from app.schemas.student import StudentCreate, StudentResponse, StudentUpdate
from app.schemas.user import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserRole,
    UserUpdate,
)
from app.schemas.zone import ZoneCreate, ZoneResponse, ZoneUpdate

__all__ = [
    "HealthResponse",
    "UserRole",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "LoginRequest",
    "TokenResponse",
    "ZoneCreate",
    "ZoneUpdate",
    "ZoneResponse",
    "AccessPointCreate",
    "AccessPointUpdate",
    "AccessPointResponse",
    "DeviceCreate",
    "DeviceUpdate",
    "DeviceResponse",
    "StudentCreate",
    "StudentUpdate",
    "StudentResponse",
    "SchoolSettingsUpdate",
    "SchoolSettingsResponse",
    "AlertSettingsUpdate",
    "AlertSettingsResponse",
    "ScanSampleIn",
    "CalibrationBatchIn",
    "FingerprintCreate",
    "FingerprintUpdate",
    "FingerprintResponse",
    "FingerprintDetailResponse",
    "FingerprintAPStatResponse",
    "TelemetryScanItem",
    "TelemetryIngestIn",
    "TelemetryIngestResponse",
    "LocationEstimate",
    "LocationRecordResponse",
    "StudentLiveLocationResponse",
]

