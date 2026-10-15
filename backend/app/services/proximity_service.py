import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import AlertSeverity, AlertType
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.location_record import LocationRecord
from app.models.zone import Zone
from app.schemas.location import MasterTelemetryIngest, TelemetryIngestResponse
from app.services import alert_service
from app.services.settings_service import get_or_create_alert_settings

logger = logging.getLogger(__name__)


@dataclass
class StudentLiveLocationDTO:
    """Strongly-typed live location snapshot for a student."""

    current_zone_name: str | None
    confidence: float
    device_code: str | None
    battery_percent: int | None


def _get_sta_mac_from_ap(ap_mac: str) -> str:
    """Convert an ESP32 SoftAP MAC (+1) back to its base Station MAC."""
    try:
        parts = ap_mac.upper().split(":")
        if len(parts) == 6:
            last_byte = int(parts[-1], 16)
            last_byte_sta = (last_byte - 1) % 256
            parts[-1] = f"{last_byte_sta:02X}"
            return ":".join(parts)
    except Exception:
        pass
    return ap_mac


async def process_telemetry_scan(
    db: AsyncSession, payload: MasterTelemetryIngest
) -> TelemetryIngestResponse:
    """Process a telemetry ping from a Master ESP scanning multiple Slave ESPs.

    Includes multi-scanner arbitration with hysteresis to prevent oscillation
    when adjacent scanners detect bleed-through signals from nearby rooms.
    """
    now_utc = datetime.now(UTC)

    # 1. Look up the Master Scanner
    stmt = select(Device).where(
        Device.mac_address == payload.scanner_mac, Device.type == DeviceType.SCANNER
    )
    result = await db.execute(stmt)
    scanner = result.scalar_one_or_none()

    if not scanner:
        logger.warning(
            "Ignored telemetry from unknown or inactive scanner MAC: %s",
            payload.scanner_mac,
        )
        return TelemetryIngestResponse(
            status="error",
            scanner_mac=payload.scanner_mac,
            processed_tags=0,
            server_time=now_utc,
        )

    # Update scanner last seen
    scanner.last_seen_at = now_utc
    scanner.status = DeviceStatus.ONLINE

    zone_id = scanner.assigned_zone_id
    if not zone_id:
        logger.warning(
            "Scanner %s has no assigned zone. Skipping tags.", scanner.device_code
        )
        await db.commit()
        return TelemetryIngestResponse(
            status="no_zone",
            scanner_mac=payload.scanner_mac,
            processed_tags=0,
            server_time=now_utc,
        )

    # 2. Process each Tag
    processed_count = 0
    updated_student_ids = set()

    for tag_obs in payload.tags:
        stmt_tag = select(Device).where(
            (Device.mac_address == tag_obs.mac)
            | (Device.mac_address == _get_sta_mac_from_ap(tag_obs.mac)),
            Device.type == DeviceType.WEARABLE,
        )
        res_tag = await db.execute(stmt_tag)
        tag_device = res_tag.scalars().first()

        if tag_device:
            tag_device.last_seen_at = now_utc
            tag_device.status = DeviceStatus.ONLINE
            if tag_obs.battery is not None:
                tag_device.battery_percent = tag_obs.battery

            # Create location record if assigned to a student
            if tag_device.student_id:
                # Calibrated RSSI-to-confidence calculation:
                # -30 dBm or above -> ~1.00 (immediate proximity to scanner)
                # -50 dBm -> ~0.75 (good in-room signal)
                # -65 dBm -> ~0.50 (edge of room)
                # -80 dBm -> ~0.25 (weak/penetrating signal)
                # -95 dBm -> ~0.05 (noise floor)
                confidence = max(0.05, min(1.0, (tag_obs.rssi + 95.0) / 65.0))

                # Multi-scanner arbitration:
                # Check the student's recent location record to prevent room-hopping flickering.
                stmt_latest = (
                    select(LocationRecord)
                    .where(LocationRecord.student_id == tag_device.student_id)
                    .order_by(LocationRecord.recorded_at.desc())
                    .limit(1)
                )
                res_latest = await db.execute(stmt_latest)
                latest_record = res_latest.scalar_one_or_none()

                should_record = True
                if latest_record:
                    rec_time = latest_record.recorded_at
                    if rec_time.tzinfo is None:
                        rec_time = rec_time.replace(tzinfo=UTC)
                    age_seconds = (now_utc - rec_time).total_seconds()

                    # If student was confirmed in another zone within the last 10 seconds:
                    # Only switch zones if incoming signal is not significantly weaker.
                    if (
                        latest_record.zone_id != zone_id
                        and age_seconds < 10.0
                        and confidence < (latest_record.confidence - 0.12)
                    ):
                        should_record = False
                        logger.debug(
                            "Arbitration: ignored bleed-through scan from %s for student %s "
                            "(conf=%.2f < active=%.2f, age=%.1fs)",
                            payload.scanner_mac,
                            tag_device.student_id,
                            confidence,
                            latest_record.confidence,
                            age_seconds,
                        )

                if should_record:
                    record = LocationRecord(
                        student_id=tag_device.student_id,
                        device_id=tag_device.id,
                        zone_id=zone_id,
                        confidence=confidence,
                        raw_scan={"scanner": payload.scanner_mac, "rssi": tag_obs.rssi},
                    )
                    db.add(record)
                    processed_count += 1
                    updated_student_ids.add(tag_device.student_id)

                # Handle SOS alerts immediately regardless of arbitration
                if tag_obs.sos:
                    await alert_service.create_alert_idempotent(
                        db,
                        alert_type=AlertType.SOS,
                        severity=AlertSeverity.CRITICAL,
                        message=f"SOS BUTTON PRESSED by {tag_device.device_code}",
                        student_id=tag_device.student_id,
                        device_id=tag_device.id,
                        zone_id=zone_id,
                    )

    await db.commit()

    # Auto-prune: Keep only the last 30 records per updated student
    if updated_student_ids:
        for sid in updated_student_ids:
            stmt_prune = (
                select(LocationRecord.id)
                .where(LocationRecord.student_id == sid)
                .order_by(LocationRecord.recorded_at.desc())
                .offset(30)
                .limit(100)
            )
            res_prune = await db.execute(stmt_prune)
            ids_to_delete = res_prune.scalars().all()
            if ids_to_delete:
                await db.execute(delete(LocationRecord).where(LocationRecord.id.in_(ids_to_delete)))
        await db.commit()

    logger.info(
        "Scanner %s in zone %s processed %d valid tags.",
        payload.scanner_mac,
        zone_id,
        processed_count,
    )
    return TelemetryIngestResponse(
        status="ack",
        scanner_mac=payload.scanner_mac,
        processed_tags=processed_count,
        server_time=now_utc,
    )


async def get_student_location_history(
    db: AsyncSession, student_id: uuid.UUID, limit: int = 50
) -> list[LocationRecord]:
    """Get location history breadcrumbs for a student."""
    stmt = (
        select(LocationRecord)
        .options(selectinload(LocationRecord.zone))
        .where(LocationRecord.student_id == student_id)
        .order_by(LocationRecord.recorded_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_student_live_location(
    db: AsyncSession, student_id: uuid.UUID
) -> StudentLiveLocationDTO:
    """Get real-time resolved location and device status for a student."""
    stmt = (
        select(LocationRecord, Zone.name)
        .outerjoin(Zone, LocationRecord.zone_id == Zone.id)
        .where(LocationRecord.student_id == student_id)
        .order_by(LocationRecord.recorded_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    loc = row[0] if row else None
    zone_name = row[1] if row else None

    stmt_device = select(Device).where(
        Device.student_id == student_id, Device.type == DeviceType.WEARABLE
    )
    res_device = await db.execute(stmt_device)
    device = res_device.scalars().first()

    if not loc:
        return StudentLiveLocationDTO(
            current_zone_name=None,
            confidence=0.0,
            device_code=device.device_code if device else None,
            battery_percent=device.battery_percent if device else None,
        )

    alert_settings = await get_or_create_alert_settings(db)
    is_low_confidence = loc.confidence < alert_settings.min_localization_confidence

    return StudentLiveLocationDTO(
        current_zone_name=None if is_low_confidence else zone_name,
        confidence=loc.confidence,
        device_code=device.device_code if device else None,
        battery_percent=device.battery_percent if device else None,
    )
