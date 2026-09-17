"""Business logic for safety alerts, automated periodic monitoring, and incident triage workflow."""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.alert import Alert, AlertSeverity, AlertStatus, AlertType
from app.models.device import Device, DeviceStatus
from app.models.location_record import LocationRecord
from app.models.student import Student
from app.services import settings_service

logger = logging.getLogger("childtrack.alert_service")


async def get_active_alerts_count(db: AsyncSession) -> int:
    """Return the total count of currently active unacknowledged alerts."""
    stmt = select(func.count(Alert.id)).where(Alert.status == AlertStatus.ACTIVE)
    count = await db.scalar(stmt)
    return count or 0


async def list_active_alerts(db: AsyncSession, limit: int = 20) -> Sequence[Alert]:
    """Retrieve recent active safety alerts for feeds and dashboards."""
    return await list_alerts(db, status=AlertStatus.ACTIVE, limit=limit)


async def list_alerts(
    db: AsyncSession,
    status: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    alert_type: AlertType | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[Alert]:
    """Retrieve safety alerts with optional filtering and pagination."""
    stmt = select(Alert)

    filters = []
    if status is not None:
        filters.append(Alert.status == status)
    if severity is not None:
        filters.append(Alert.severity == severity)
    if alert_type is not None:
        filters.append(Alert.type == alert_type)

    if filters:
        stmt = stmt.where(and_(*filters))

    stmt = (
        stmt.order_by(Alert.created_at.desc())
        .offset(offset)
        .limit(limit)
        .options(
            selectinload(Alert.student),
            selectinload(Alert.device),
            selectinload(Alert.zone),
            selectinload(Alert.acknowledger),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_alert_by_id(db: AsyncSession, alert_id: uuid.UUID) -> Alert:
    """Retrieve a single alert record by UUID."""
    stmt = (
        select(Alert)
        .where(Alert.id == alert_id)
        .options(
            selectinload(Alert.student),
            selectinload(Alert.device),
            selectinload(Alert.zone),
            selectinload(Alert.acknowledger),
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError("Alert", alert_id)
    return alert


async def create_alert_idempotent(
    db: AsyncSession,
    *,
    alert_type: AlertType,
    severity: AlertSeverity,
    message: str,
    student_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
) -> tuple[Alert, bool]:
    """Create an alert only if an identical active alert is not already open.

    Enforces strict idempotency (AGENTS.md absolute rule): avoids generating
    duplicate active alerts on repeated sweeps for the same condition.
    Returns (alert, was_created).
    """
    conditions = [
        Alert.type == alert_type,
        Alert.status == AlertStatus.ACTIVE,
    ]
    if student_id is not None:
        conditions.append(Alert.student_id == student_id)
    if device_id is not None:
        conditions.append(Alert.device_id == device_id)
    if zone_id is not None:
        conditions.append(Alert.zone_id == zone_id)

    stmt = select(Alert).where(and_(*conditions)).limit(1)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        return existing, False

    alert = Alert(
        type=alert_type,
        severity=severity,
        status=AlertStatus.ACTIVE,
        message=message,
        student_id=student_id,
        device_id=device_id,
        zone_id=zone_id,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    logger.warning(
        "Generated safety alert [%s/%s]: %s (student=%s, device=%s)",
        alert_type.value,
        severity.value,
        message,
        student_id,
        device_id,
    )
    return alert, True


async def acknowledge_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Alert:
    """Acknowledge an active alert and record the resolving user timestamp."""
    alert = await get_alert_by_id(db, alert_id)
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = user_id
    alert.acknowledged_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(alert)
    logger.info("Alert %s acknowledged by user %s", alert_id, user_id)
    return alert


async def resolve_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> Alert:
    """Mark an alert as resolved and clear it from active triage."""
    alert = await get_alert_by_id(db, alert_id)
    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = datetime.now(UTC)
    if user_id and not alert.acknowledged_by:
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(alert)
    logger.info("Alert %s marked as resolved", alert_id)
    return alert


# ==============================================================================
# Automated Safety Sweep & Rule Checkers
# ==============================================================================


async def check_offline_devices(
    db: AsyncSession,
    offline_threshold_seconds: int | None = None,
) -> list[Alert]:
    """Scan active devices and flag wearables that have stopped reporting telemetry."""
    settings = await settings_service.get_or_create_alert_settings(db)
    if offline_threshold_seconds is None:
        offline_threshold_seconds = settings.offline_threshold_minutes * 60

    critical_threshold_seconds = settings.critical_offline_threshold_minutes * 60

    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=offline_threshold_seconds)

    # Find active devices assigned to students that have gone stale
    stmt = (
        select(Device)
        .where(
            Device.is_active == True,  # noqa: E712
            Device.student_id.is_not(None),
        )
        .options(selectinload(Device.student))
    )
    res = await db.execute(stmt)
    devices = res.scalars().all()

    new_alerts: list[Alert] = []
    for d in devices:
        last_seen = d.last_seen_at
        if last_seen:
            last_seen_aware = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=UTC)
            is_stale = last_seen_aware < cutoff
        else:
            created_aware = (
                d.created_at if d.created_at.tzinfo else d.created_at.replace(tzinfo=UTC)
            )
            is_stale = created_aware < cutoff

        if is_stale:
            # Update operational status to OFFLINE if still marked ONLINE
            if d.status == DeviceStatus.ONLINE:
                d.status = DeviceStatus.OFFLINE
                await db.commit()

            student_name = d.student.full_name if d.student else "Unassigned"
            # Calculate duration since last seen
            if last_seen:
                diff_sec = int((now - last_seen_aware).total_seconds())
                severity = (
                    AlertSeverity.CRITICAL
                    if diff_sec >= critical_threshold_seconds
                    else AlertSeverity.WARNING
                )
                msg = (
                    f"Wearable tag '{d.device_code}' assigned to {student_name} is offline. "
                    f"No telemetry received for {diff_sec // 60} minutes."
                )
            else:
                severity = AlertSeverity.WARNING
                msg = (
                    f"Wearable tag '{d.device_code}' assigned to {student_name} has never "
                    f"reported telemetry."
                )

            alert, created = await create_alert_idempotent(
                db,
                alert_type=AlertType.OFFLINE,
                severity=severity,
                message=msg,
                student_id=d.student_id,
                device_id=d.id,
            )
            if created:
                new_alerts.append(alert)

    return new_alerts


async def check_low_battery_devices(
    db: AsyncSession,
    low_battery_threshold: int | None = None,
) -> list[Alert]:
    """Scan active devices and generate warnings for critically depleted batteries."""
    if low_battery_threshold is None:
        settings = await settings_service.get_or_create_alert_settings(db)
        low_battery_threshold = settings.low_battery_percent

    stmt = (
        select(Device)
        .where(
            Device.is_active == True,  # noqa: E712
            Device.student_id.is_not(None),
            Device.battery_percent <= low_battery_threshold,
        )
        .options(selectinload(Device.student))
    )
    res = await db.execute(stmt)
    devices = res.scalars().all()

    new_alerts: list[Alert] = []
    for d in devices:
        student_name = d.student.full_name if d.student else "Unassigned"
        severity = AlertSeverity.CRITICAL if d.battery_percent <= 5 else AlertSeverity.WARNING
        msg = (
            f"Low battery warning: Wearable '{d.device_code}' ({student_name}) "
            f"battery is at {d.battery_percent}%."
        )

        alert, created = await create_alert_idempotent(
            db,
            alert_type=AlertType.LOW_BATTERY,
            severity=severity,
            message=msg,
            student_id=d.student_id,
            device_id=d.id,
        )
        if created:
            new_alerts.append(alert)

    return new_alerts


async def check_restricted_zone_breaches(db: AsyncSession) -> list[Alert]:
    """Inspect latest location estimates and trigger critical alerts for zone violations."""
    settings = await settings_service.get_or_create_alert_settings(db)
    if not settings.restricted_zone_alerts_enabled:
        return []

    # 1. Fetch active students with configured allowed_zones
    student_stmt = (
        select(Student)
        .where(
            Student.is_active == True,  # noqa: E712
        )
        .options(
            selectinload(Student.allowed_zones),
            selectinload(Student.device),
        )
    )
    s_res = await db.execute(student_stmt)
    students = s_res.scalars().all()

    if not students:
        return []

    # 2. Get latest location records for all students via subquery
    subq = (
        select(
            LocationRecord.student_id,
            func.max(LocationRecord.recorded_at).label("max_recorded_at"),
        )
        .group_by(LocationRecord.student_id)
        .subquery()
    )

    latest_stmt = (
        select(LocationRecord)
        .join(
            subq,
            and_(
                LocationRecord.student_id == subq.c.student_id,
                LocationRecord.recorded_at == subq.c.max_recorded_at,
            ),
        )
        .options(selectinload(LocationRecord.zone))
    )
    latest_res = await db.execute(latest_stmt)
    latest_by_student = {rec.student_id: rec for rec in latest_res.scalars().all()}

    new_alerts: list[Alert] = []
    for s in students:
        # Check only students with an assigned wearable
        if not s.device:
            continue

        allowed_ids = {z.id for z in s.allowed_zones}
        # Whitelist check applies only if allowed zones are defined
        if not allowed_ids:
            continue

        latest_rec = latest_by_student.get(s.id)
        if not latest_rec or latest_rec.zone_id is None:
            continue

        if latest_rec.zone_id not in allowed_ids:
            # Breach detected
            zone_name = latest_rec.zone.name if latest_rec.zone else "Unauthorized Area"
            msg = (
                f"RESTRICTED ZONE VIOLATION: Student {s.full_name} ({s.class_name}) "
                f"detected in unauthorized safe zone '{zone_name}'!"
            )
            alert, created = await create_alert_idempotent(
                db,
                alert_type=AlertType.RESTRICTED_ZONE,
                severity=AlertSeverity.CRITICAL,
                message=msg,
                student_id=s.id,
                device_id=s.device.id,
                zone_id=latest_rec.zone_id,
            )
            if created:
                new_alerts.append(alert)

    return new_alerts


async def auto_resolve_cleared_alerts(db: AsyncSession) -> int:
    """Automatically resolve active alerts whose fault condition has returned to normal."""
    now = datetime.now(UTC)
    resolved_count = 0

    # 1. Auto-resolve OFFLINE alerts for devices that came back online
    offline_alerts_stmt = (
        select(Alert)
        .where(
            Alert.status == AlertStatus.ACTIVE,
            Alert.type == AlertType.OFFLINE,
            Alert.device_id.is_not(None),
        )
        .options(selectinload(Alert.device))
    )
    off_res = await db.execute(offline_alerts_stmt)
    active_offline_alerts = off_res.scalars().all()

    settings = await settings_service.get_or_create_alert_settings(db)
    threshold = timedelta(minutes=settings.offline_threshold_minutes)

    for a in active_offline_alerts:
        device = a.device
        if device and device.status == DeviceStatus.ONLINE and device.last_seen_at:
            last_seen_aware = (
                device.last_seen_at
                if device.last_seen_at.tzinfo
                else device.last_seen_at.replace(tzinfo=UTC)
            )
            if now - last_seen_aware <= threshold:
                a.status = AlertStatus.RESOLVED
                a.resolved_at = now
                resolved_count += 1
                logger.info(
                    "Auto-resolved OFFLINE alert %s for device %s", a.id, device.device_code
                )

    if resolved_count > 0:
        await db.commit()

    return resolved_count


async def run_safety_checks_sweep(db: AsyncSession) -> dict[str, Any]:
    """Execute a comprehensive safety sweep across offline, low battery, and restricted zones."""
    start_time = datetime.now(UTC)

    offline_alerts = await check_offline_devices(db)
    battery_alerts = await check_low_battery_devices(db)
    restricted_alerts = await check_restricted_zone_breaches(db)
    auto_resolved = await auto_resolve_cleared_alerts(db)

    duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

    summary = {
        "timestamp": start_time.isoformat(),
        "duration_ms": duration_ms,
        "offline_alerts_created": len(offline_alerts),
        "low_battery_alerts_created": len(battery_alerts),
        "restricted_zone_alerts_created": len(restricted_alerts),
        "auto_resolved_count": auto_resolved,
        "total_new_alerts": len(offline_alerts) + len(battery_alerts) + len(restricted_alerts),
    }

    if summary["total_new_alerts"] > 0 or auto_resolved > 0:
        logger.info("Safety check sweep completed: %s", summary)

    return summary
