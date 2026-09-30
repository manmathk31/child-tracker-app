"""Device ORM model representing ESP32 child wearables."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.student import Student


class DeviceStatus(str, enum.Enum):
    """Real-time operational status of an ESP32 wearable."""

    ONLINE = "online"
    OFFLINE = "offline"


class DeviceType(str, enum.Enum):
    """Type of the ESP32 device."""

    WEARABLE = "wearable"
    SCANNER = "scanner"


class Device(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """ESP32 wearable hardware tag assigned to a child."""

    __tablename__ = "devices"

    device_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    mac_address: Mapped[str] = mapped_column(
        String(17),
        unique=True,
        index=True,
        nullable=False,
    )
    battery_percent: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )
    firmware_version: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, name="device_status", native_enum=False),
        default=DeviceStatus.OFFLINE,
        nullable=False,
    )
    type: Mapped[DeviceType] = mapped_column(
        Enum(DeviceType, name="device_type", native_enum=False),
        default=DeviceType.WEARABLE,
        nullable=False,
    )
    student_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("students.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    assigned_zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("zones.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    student: Mapped[Optional["Student"]] = relationship(
        "Student",
        back_populates="device",
    )
    assigned_zone: Mapped[Optional["Zone"]] = relationship(
        "Zone",
        back_populates="scanner_devices",
    )

    def __repr__(self) -> str:
        return f"<Device {self.device_code} ({self.mac_address}) - {self.type.value} - {self.status.value}>"
