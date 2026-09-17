"""Fingerprint, AP Statistical Aggregation, and Raw Sample ORM Models."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.access_point import AccessPoint
    from app.models.user import User
    from app.models.zone import Zone


class FingerprintStatus(str, enum.Enum):
    """Lifecycle status of a zone radio fingerprint survey."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Fingerprint(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Survey set containing baseline RSSI measurements for indoor localization."""

    __tablename__ = "fingerprints"

    zone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("zones.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sample_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    quality_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    min_rssi_cutoff: Mapped[int] = mapped_column(
        Integer,
        default=-85,
        nullable=False,
    )
    status: Mapped[FingerprintStatus] = mapped_column(
        SQLEnum(FingerprintStatus, native_enum=False),
        default=FingerprintStatus.DRAFT,
        nullable=False,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    zone: Mapped["Zone"] = relationship(
        "Zone",
        back_populates="fingerprints",
    )
    creator: Mapped["User"] = relationship(
        "User",
    )
    ap_stats: Mapped[List["FingerprintAPStat"]] = relationship(
        "FingerprintAPStat",
        back_populates="fingerprint",
        cascade="all, delete-orphan",
        order_by="FingerprintAPStat.median_rssi.desc()",
    )
    samples: Mapped[List["FingerprintSample"]] = relationship(
        "FingerprintSample",
        back_populates="fingerprint",
        cascade="all, delete-orphan",
    )

    @property
    def zone_name(self) -> Optional[str]:
        if "zone" in self.__dict__ and self.zone:
            return self.zone.name
        return None

    @property
    def creator_name(self) -> Optional[str]:
        if "creator" in self.__dict__ and self.creator:
            return self.creator.full_name
        return None

    def __repr__(self) -> str:
        return f"<Fingerprint id={self.id} zone_id={self.zone_id} status={self.status.value} samples={self.sample_count}>"



class FingerprintAPStat(Base, UUIDPrimaryKeyMixin):
    """Pre-computed statistical distribution per Access Point used by the k-NN engine."""

    __tablename__ = "fingerprint_ap_stats"

    fingerprint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fingerprints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_point_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_points.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    median_rssi: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    mean_rssi: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    stddev_rssi: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    sample_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Relationships
    fingerprint: Mapped["Fingerprint"] = relationship(
        "Fingerprint",
        back_populates="ap_stats",
    )
    access_point: Mapped["AccessPoint"] = relationship(
        "AccessPoint",
    )

    @property
    def access_point_name(self) -> Optional[str]:
        if "access_point" in self.__dict__ and self.access_point:
            return self.access_point.name
        return None

    @property
    def access_point_bssid(self) -> Optional[str]:
        if "access_point" in self.__dict__ and self.access_point:
            return self.access_point.bssid
        return None

    def __repr__(self) -> str:
        return f"<FingerprintAPStat ap_id={self.access_point_id} median={self.median_rssi} stddev={self.stddev_rssi}>"



class FingerprintSample(Base, UUIDPrimaryKeyMixin):
    """Raw RSSI survey vectors collected during calibration scans."""

    __tablename__ = "fingerprint_samples"

    fingerprint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fingerprints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_point_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_points.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rssi: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    fingerprint: Mapped["Fingerprint"] = relationship(
        "Fingerprint",
        back_populates="samples",
    )
    access_point: Mapped["AccessPoint"] = relationship(
        "AccessPoint",
    )

    def __repr__(self) -> str:
        return f"<FingerprintSample ap_id={self.access_point_id} rssi={self.rssi}>"
