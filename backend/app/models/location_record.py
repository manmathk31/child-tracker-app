"""Location Record ORM Model for indoor positioning audit trails."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.student import Student
    from app.models.zone import Zone


class LocationRecord(Base, UUIDPrimaryKeyMixin):
    """Historical record of an indoor localization estimate for a monitored student."""

    __tablename__ = "location_records"

    student_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("zones.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    raw_scan: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    student: Mapped["Student"] = relationship(
        "Student",
    )
    device: Mapped["Device"] = relationship(
        "Device",
    )
    zone: Mapped[Optional["Zone"]] = relationship(
        "Zone",
    )

    @property
    def student_name(self) -> str | None:
        if "student" in self.__dict__ and self.student:
            return self.student.full_name
        return None

    @property
    def device_code(self) -> str | None:
        if "device" in self.__dict__ and self.device:
            return self.device.device_code
        return None

    @property
    def zone_name(self) -> str | None:
        if "zone" in self.__dict__ and self.zone:
            return self.zone.name
        return "Unknown Area"

    def __repr__(self) -> str:
        return (
            f"<LocationRecord student_id={self.student_id} "
            f"zone_id={self.zone_id} conf={self.confidence}>"
        )
