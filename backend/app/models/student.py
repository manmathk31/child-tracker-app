"""Student ORM model and allowed_zones association table."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.zone import Zone

# Association table defining many-to-many permitted zones for a student
allowed_zones = Table(
    "allowed_zones",
    Base.metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("student_id", Uuid(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("zone_id", Uuid(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("student_id", "zone_id", name="uq_allowed_zones_student_zone"),
)


class Student(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Enrolled student profile monitored by ChildTrack."""

    __tablename__ = "students"

    student_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    class_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    age: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    photo_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    # Relationships
    device: Mapped[Optional["Device"]] = relationship(
        "Device",
        back_populates="student",
        uselist=False,
    )
    allowed_zones: Mapped[List["Zone"]] = relationship(
        "Zone",
        secondary=allowed_zones,
        back_populates="students",
    )

    @property
    def device_id(self) -> Optional[uuid.UUID]:
        if "device" in self.__dict__ and self.device:
            return self.device.id
        return None

    @property
    def device_code(self) -> Optional[str]:
        if "device" in self.__dict__ and self.device:
            return self.device.device_code
        return None

    @property
    def device_battery(self) -> Optional[int]:
        if "device" in self.__dict__ and self.device:
            return self.device.battery_percent
        return None

    def __repr__(self) -> str:
        return f"<Student {self.student_code} - {self.full_name} ({self.class_name})>"

