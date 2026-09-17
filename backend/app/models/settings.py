"""Settings ORM models for organization metadata and alert thresholds."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin


class SchoolSettings(Base, UUIDPrimaryKeyMixin):
    """Organization-level settings and metadata (singleton)."""

    __tablename__ = "school_settings"

    school_name: Mapped[str] = mapped_column(
        String(255),
        default="ChildTrack Academy",
        nullable=False,
    )
    building_name: Mapped[str] = mapped_column(
        String(255),
        default="Main Campus",
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        default="UTC",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SchoolSettings {self.school_name} - {self.building_name}>"


class AlertSettings(Base, UUIDPrimaryKeyMixin):
    """Configurable system alert triggers and localization thresholds (singleton)."""

    __tablename__ = "alert_settings"

    offline_threshold_minutes: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    critical_offline_threshold_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    low_battery_percent: Mapped[int] = mapped_column(
        Integer,
        default=20,
        nullable=False,
    )
    min_localization_confidence: Mapped[float] = mapped_column(
        Float,
        default=0.45,
        nullable=False,
    )
    restricted_zone_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    fall_detection_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    sos_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AlertSettings offline={self.offline_threshold_minutes}m low_battery={self.low_battery_percent}%>"
