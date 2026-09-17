"""Zone ORM model representing monitored areas within the school."""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.access_point import AccessPoint
    from app.models.student import Student


class Zone(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Monitored physical zone in a building or campus."""

    __tablename__ = "zones"

    name: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    building: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    floor: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    # Relationships
    access_points: Mapped[List["AccessPoint"]] = relationship(
        "AccessPoint",
        back_populates="zone",
        cascade="all, delete-orphan",
    )
    students: Mapped[List["Student"]] = relationship(
        "Student",
        secondary="allowed_zones",
        back_populates="allowed_zones",
    )

    def __repr__(self) -> str:
        return f"<Zone {self.name} ({self.building or 'Default'}, {self.floor or 'Ground'})>"
