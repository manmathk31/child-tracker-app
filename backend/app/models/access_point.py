"""AccessPoint ORM model representing fixed Wi-Fi access points."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.zone import Zone


class AccessPoint(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Fixed Wi-Fi Access Point deployed in a specific zone."""

    __tablename__ = "access_points"

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    bssid: Mapped[str] = mapped_column(
        String(17),
        unique=True,
        index=True,
        nullable=False,
    )
    channel: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("zones.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Relationships
    zone: Mapped[Optional["Zone"]] = relationship(
        "Zone",
        back_populates="access_points",
    )

    def __repr__(self) -> str:
        return f"<AccessPoint {self.name} ({self.bssid})>"
