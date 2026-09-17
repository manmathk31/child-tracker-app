"""High-efficiency real-time safety monitoring and room occupancy aggregation service."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.device import DeviceStatus
from app.models.location_record import LocationRecord
from app.models.student import Student
from app.models.zone import Zone
from app.schemas.alert import AlertResponse
from app.schemas.dashboard import (
    DashboardLiveResponse,
    DashboardMetrics,
    OccupantSummary,
    StudentLiveStatus,
    ZoneOccupancy,
)
from app.services import alert_service
from app.services.settings_service import get_or_create_alert_settings

logger = logging.getLogger("childtrack.dashboard_service")


async def get_dashboard_live_payload(
    db: AsyncSession,
    class_name: str | None = None,
) -> DashboardLiveResponse:
    """Aggregate complete real-time safety metrics, room occupancy, and student status.

    Uses a single batch subquery to fetch the latest location per student,
    assembling the entire school occupancy grid in memory with O(N) efficiency.
    """
    now_utc = datetime.now(UTC)
    alert_settings = await get_or_create_alert_settings(db)
    offline_threshold = timedelta(minutes=alert_settings.offline_threshold_minutes)
    low_battery_cutoff = alert_settings.low_battery_percent

    # 1. Fetch all active physical zones
    zones_stmt = (
        select(Zone)
        .where(Zone.is_active == True)  # noqa: E712
        .order_by(Zone.name.asc())
    )
    zones_res = await db.execute(zones_stmt)
    zones = zones_res.scalars().all()

    # 2. Fetch active students with their device and allowed zone permissions
    students_stmt = (
        select(Student)
        .where(Student.is_active == True)  # noqa: E712
        .options(
            selectinload(Student.device),
            selectinload(Student.allowed_zones),
        )
        .order_by(Student.full_name.asc())
    )
    if class_name and class_name.strip():
        students_stmt = students_stmt.where(Student.class_name == class_name.strip())

    students_res = await db.execute(students_stmt)
    students = students_res.scalars().all()

    # 3. Batch query the single latest LocationRecord per student using subquery
    subq = (
        select(
            LocationRecord.student_id,
            func.max(LocationRecord.recorded_at).label("latest_recorded_at"),
        )
        .group_by(LocationRecord.student_id)
        .subquery()
    )
    latest_records_stmt = (
        select(LocationRecord)
        .join(
            subq,
            and_(
                LocationRecord.student_id == subq.c.student_id,
                LocationRecord.recorded_at == subq.c.latest_recorded_at,
            ),
        )
        .options(selectinload(LocationRecord.zone))
    )
    latest_res = await db.execute(latest_records_stmt)
    latest_by_student: dict[uuid.UUID, LocationRecord] = {
        rec.student_id: rec for rec in latest_res.scalars().all()
    }

    # 4. In-memory aggregation
    total_students = len(students)
    trackable_students = 0
    attention_students = 0

    occupants_by_zone: dict[uuid.UUID, list[OccupantSummary]] = {z.id: [] for z in zones}
    roaming_occupants: list[OccupantSummary] = []
    student_status_cards: list[StudentLiveStatus] = []

    for s in students:
        device = s.device
        battery = device.battery_percent if device else None
        last_seen = device.last_seen_at if device else None

        # Device connectivity status
        is_online = False
        device_status_str = "unassigned"

        if device:
            # Wearable is online if status is ONLINE and seen within offline_threshold
            if device.status == DeviceStatus.ONLINE and last_seen:
                # Normalize tz if needed
                last_seen_aware = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=UTC)
                if now_utc - last_seen_aware <= offline_threshold:
                    is_online = True
                    device_status_str = "online"
                else:
                    device_status_str = "offline"
            else:
                device_status_str = "offline"

        if is_online:
            trackable_students += 1

        # Student latest location
        latest_rec = latest_by_student.get(s.id)
        current_zone_id = latest_rec.zone_id if latest_rec else None
        current_zone_name = latest_rec.zone.name if (latest_rec and latest_rec.zone) else None
        confidence = latest_rec.confidence if latest_rec else 0.0

        # Allowed safe zones whitelist check
        allowed_ids = {z.id for z in s.allowed_zones}
        is_restricted = False
        if allowed_ids and current_zone_id is not None:
            if current_zone_id not in allowed_ids:
                is_restricted = True

        # Attention required evaluation:
        # 1) Low battery (<= threshold)
        # 2) Paired device went offline
        # 3) Restricted zone breach
        # 4) Low confidence / unknown position while wearable is online
        needs_attention = False
        if device:
            if battery is not None and battery <= low_battery_cutoff:
                needs_attention = True
            elif not is_online:
                needs_attention = True
            elif is_restricted:
                needs_attention = True
            elif current_zone_id is None:
                needs_attention = True

        if needs_attention:
            attention_students += 1
            status_level = "attention"
        elif is_online:
            status_level = "online"
        else:
            status_level = "offline"

        # Occupant chip data (for room cards)
        if device and is_online:
            occ = OccupantSummary(
                student_id=s.id,
                full_name=s.full_name,
                student_code=s.student_code,
                class_name=s.class_name,
                photo_url=s.photo_url,
                device_code=device.device_code,
                battery_percent=battery,
                confidence=confidence,
                is_restricted=is_restricted,
            )
            if current_zone_id and current_zone_id in occupants_by_zone:
                occupants_by_zone[current_zone_id].append(occ)
            else:
                roaming_occupants.append(occ)

        # Full student card representation
        student_status_cards.append(
            StudentLiveStatus(
                student_id=s.id,
                full_name=s.full_name,
                student_code=s.student_code,
                class_name=s.class_name,
                age=s.age,
                photo_url=s.photo_url,
                device_id=device.id if device else None,
                device_code=device.device_code if device else None,
                battery_percent=battery,
                device_status=device_status_str,
                current_zone_id=current_zone_id,
                current_zone_name=current_zone_name,
                confidence=confidence,
                last_seen_at=last_seen,
                is_restricted=is_restricted,
                status_level=status_level,
            )
        )

    # 5. Build ZoneOccupancy objects
    zone_occupancies: list[ZoneOccupancy] = []
    for z in zones:
        occs = occupants_by_zone.get(z.id, [])
        has_restricted = any(o.is_restricted for o in occs)
        zone_occupancies.append(
            ZoneOccupancy(
                zone_id=z.id,
                zone_name=z.name,
                building=z.building,
                floor=z.floor,
                occupant_count=len(occs),
                has_restricted_student=has_restricted,
                occupants=occs,
            )
        )

    roaming_zone = ZoneOccupancy(
        zone_id=None,
        zone_name="Roaming / Low Confidence",
        building=None,
        floor=None,
        occupant_count=len(roaming_occupants),
        has_restricted_student=any(o.is_restricted for o in roaming_occupants),
        occupants=roaming_occupants,
    )

    # 6. Active Alerts
    active_alerts_raw = await alert_service.list_active_alerts(db, limit=10)
    active_alerts_count = await alert_service.get_active_alerts_count(db)
    active_alerts = [AlertResponse.model_validate(a) for a in active_alerts_raw]

    metrics = DashboardMetrics(
        total_students=total_students,
        trackable_students=trackable_students,
        attention_students=attention_students,
        active_alerts_count=active_alerts_count,
    )

    return DashboardLiveResponse(
        timestamp=now_utc,
        metrics=metrics,
        zones=zone_occupancies,
        roaming_zone=roaming_zone,
        students=student_status_cards,
        active_alerts=active_alerts,
    )
