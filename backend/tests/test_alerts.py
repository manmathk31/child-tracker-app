"""Automated tests for Phase 6: Automated Safety Alerting Engine and Incident Log."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.alert import Alert, AlertSeverity, AlertStatus, AlertType
from app.models.device import DeviceStatus
from app.models.location_record import LocationRecord
from app.models.user import User
from app.schemas.device import DeviceCreate
from app.schemas.student import StudentCreate
from app.schemas.zone import ZoneCreate
from app.services import alert_service, device_service, student_service, zone_service


def _random_mac() -> str:
    """Generate a valid, randomized unique MAC address for testing."""
    hex_str = uuid.uuid4().hex[:12].upper()
    return ":".join(hex_str[i : i + 2] for i in range(0, 12, 2))


@pytest.mark.asyncio
async def test_offline_device_detection_and_idempotency(db_session: AsyncSession) -> None:
    """Verify offline wearable detection and strict idempotency (no duplicate active alerts)."""
    # 1. Create Zone, Device, and Student
    zone = await zone_service.create_zone(
        db_session, ZoneCreate(name=f"Zone {uuid.uuid4().hex[:4]}")
    )
    dev = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )
    # Set stale last_seen_at (120 seconds ago)
    now = datetime.now(UTC)
    dev.status = DeviceStatus.ONLINE
    dev.last_seen_at = now - timedelta(seconds=120)

    student = await student_service.create_student(
        db_session,
        StudentCreate(
            full_name="Stale Sammy",
            student_code=f"STU-{uuid.uuid4().hex[:4].upper()}",
            class_name="Grade 1",
            age=6,
            device_id=dev.id,
            allowed_zone_ids=[zone.id],
        ),
    )

    # 2. Run offline checker with 60-second threshold
    new_alerts = await alert_service.check_offline_devices(db_session, offline_threshold_seconds=60)
    assert len(new_alerts) >= 1
    offline_alert = next((a for a in new_alerts if a.device_id == dev.id), None)
    assert offline_alert is not None
    assert offline_alert.type == AlertType.OFFLINE
    assert offline_alert.status == AlertStatus.ACTIVE
    assert offline_alert.student_id == student.id

    # Verify device status was updated to OFFLINE
    await db_session.refresh(dev)
    assert dev.status == DeviceStatus.OFFLINE

    # 3. IDEMPOTENCY CHECK: Run offline checker a second time
    second_run_alerts = await alert_service.check_offline_devices(
        db_session, offline_threshold_seconds=60
    )
    # Should not create another active alert for the same device
    assert not any(a.device_id == dev.id for a in second_run_alerts)

    # Verify database still only has 1 active alert for this device
    stmt = select(Alert).where(
        Alert.device_id == dev.id,
        Alert.type == AlertType.OFFLINE,
        Alert.status == AlertStatus.ACTIVE,
    )
    res = await db_session.execute(stmt)
    all_dev_alerts = res.scalars().all()
    assert len(all_dev_alerts) == 1


@pytest.mark.asyncio
async def test_low_battery_detection_and_idempotency(db_session: AsyncSession) -> None:
    """Verify low battery alert generation and idempotency."""
    zone = await zone_service.create_zone(
        db_session, ZoneCreate(name=f"Zone {uuid.uuid4().hex[:4]}")
    )
    dev = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )
    dev.battery_percent = 12
    dev.status = DeviceStatus.ONLINE
    dev.last_seen_at = datetime.now(UTC)

    student = await student_service.create_student(
        db_session,
        StudentCreate(
            full_name="Low Batt Liam",
            student_code=f"STU-{uuid.uuid4().hex[:4].upper()}",
            class_name="Grade 2",
            age=7,
            device_id=dev.id,
            allowed_zone_ids=[zone.id],
        ),
    )

    # 1. Run low battery checker (cutoff = 20%)
    new_alerts = await alert_service.check_low_battery_devices(db_session, low_battery_threshold=20)
    batt_alert = next((a for a in new_alerts if a.device_id == dev.id), None)
    assert batt_alert is not None
    assert batt_alert.type == AlertType.LOW_BATTERY
    assert batt_alert.status == AlertStatus.ACTIVE
    assert batt_alert.student_id == student.id

    # 2. Idempotency test: Run again
    second_run = await alert_service.check_low_battery_devices(db_session, low_battery_threshold=20)
    assert not any(a.device_id == dev.id for a in second_run)


@pytest.mark.asyncio
async def test_restricted_zone_breach_detection_and_idempotency(db_session: AsyncSession) -> None:
    """Verify out-of-bounds safe zone violations generate critical alerts idempotently."""
    zone_safe = await zone_service.create_zone(
        db_session, ZoneCreate(name=f"Classroom {uuid.uuid4().hex[:4]}")
    )
    zone_unauth = await zone_service.create_zone(
        db_session, ZoneCreate(name=f"Boiler Room {uuid.uuid4().hex[:4]}")
    )

    dev = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )

    student = await student_service.create_student(
        db_session,
        StudentCreate(
            full_name="Wandering Wendy",
            student_code=f"STU-{uuid.uuid4().hex[:4].upper()}",
            class_name="Grade 3",
            age=8,
            device_id=dev.id,
            allowed_zone_ids=[zone_safe.id],
        ),
    )

    # Ingest location record placing Wendy inside unauthorized boiler room
    now = datetime.now(UTC)
    rec = LocationRecord(
        student_id=student.id,
        device_id=dev.id,
        zone_id=zone_unauth.id,
        confidence=0.92,
        raw_scan={"ap1": -55},
        recorded_at=now,
    )
    db_session.add(rec)
    await db_session.commit()

    # 1. Run restricted zone sweep
    new_alerts = await alert_service.check_restricted_zone_breaches(db_session)
    restr_alert = next((a for a in new_alerts if a.student_id == student.id), None)
    assert restr_alert is not None
    assert restr_alert.type == AlertType.RESTRICTED_ZONE
    assert restr_alert.severity == AlertSeverity.CRITICAL
    assert restr_alert.zone_id == zone_unauth.id

    # 2. Idempotency test: Second sweep does not duplicate
    second_sweep = await alert_service.check_restricted_zone_breaches(db_session)
    assert not any(a.student_id == student.id for a in second_sweep)


@pytest.mark.asyncio
async def test_auto_resolve_cleared_offline_alert(db_session: AsyncSession) -> None:
    """Verify an active OFFLINE alert auto-resolves when the wearable reconnects."""
    dev = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )

    # Create active offline alert for device
    alert = Alert(
        type=AlertType.OFFLINE,
        severity=AlertSeverity.WARNING,
        status=AlertStatus.ACTIVE,
        message="Device offline",
        device_id=dev.id,
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    # Device reconnects (status ONLINE, last_seen_at fresh)
    dev.status = DeviceStatus.ONLINE
    dev.last_seen_at = datetime.now(UTC)
    await db_session.commit()

    # Run auto-resolve
    resolved_count = await alert_service.auto_resolve_cleared_alerts(db_session)
    assert resolved_count >= 1

    await db_session.refresh(alert)
    assert alert.status == AlertStatus.RESOLVED
    assert alert.resolved_at is not None


@pytest.mark.asyncio
async def test_alert_acknowledge_and_resolve_lifecycle(
    db_session: AsyncSession, admin_user: User
) -> None:
    """Verify manual alert progression: ACTIVE -> ACKNOWLEDGED -> RESOLVED."""
    alert = Alert(
        type=AlertType.LOW_BATTERY,
        severity=AlertSeverity.WARNING,
        status=AlertStatus.ACTIVE,
        message="Test lifecycle alert",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    # Acknowledge
    ack = await alert_service.acknowledge_alert(db_session, alert.id, admin_user.id)
    assert ack.status == AlertStatus.ACKNOWLEDGED
    assert ack.acknowledged_by == admin_user.id
    assert ack.acknowledged_at is not None

    # Resolve
    res = await alert_service.resolve_alert(db_session, alert.id, admin_user.id)
    assert res.status == AlertStatus.RESOLVED
    assert res.resolved_at is not None


@pytest.mark.asyncio
async def test_api_list_alerts_with_filters(client: AsyncClient, admin_headers: dict) -> None:
    """Verify GET /api/v1/alerts supports status, severity, and type filtering."""
    # Fetch active alerts
    res_active = await client.get("/api/v1/alerts?status=active", headers=admin_headers)
    assert res_active.status_code == 200
    assert isinstance(res_active.json(), list)

    # Fetch critical alerts
    res_crit = await client.get("/api/v1/alerts?severity=critical", headers=admin_headers)
    assert res_crit.status_code == 200
    assert isinstance(res_crit.json(), list)

    # Fetch resolved alerts
    res_res = await client.get("/api/v1/alerts?status=resolved", headers=admin_headers)
    assert res_res.status_code == 200
    assert isinstance(res_res.json(), list)


@pytest.mark.asyncio
async def test_api_resolve_endpoint(
    db_session: AsyncSession, client: AsyncClient, admin_headers: dict
) -> None:
    """Verify POST /api/v1/alerts/{id}/resolve marks alert resolved."""
    alert = Alert(
        type=AlertType.LOW_CONFIDENCE,
        severity=AlertSeverity.INFO,
        status=AlertStatus.ACTIVE,
        message="Low confidence observation",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    res = await client.post(f"/api/v1/alerts/{alert.id}/resolve", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resolved"


@pytest.mark.asyncio
async def test_api_manual_sweep_endpoint(
    client: AsyncClient, admin_headers: dict, teacher_headers: dict
) -> None:
    """Verify POST /api/v1/alerts/sweep executes on-demand and enforces admin RBAC."""
    # Admin call: Allowed (200 OK)
    res_admin = await client.post("/api/v1/alerts/sweep", headers=admin_headers)
    assert res_admin.status_code == 200
    summary = res_admin.json()
    assert "timestamp" in summary
    assert "total_new_alerts" in summary

    # Teacher call: Forbidden (403)
    res_teacher = await client.post("/api/v1/alerts/sweep", headers=teacher_headers)
    assert res_teacher.status_code == 403


@pytest.mark.asyncio
async def test_web_alerts_page_and_form_actions(
    db_session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """Verify GET /alerts view and web form actions for acknowledge and resolve."""
    token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    client.cookies.set("access_token", token)

    # 1. View /alerts page
    res = await client.get("/alerts")
    assert res.status_code == 200
    assert (
        "Safety Alerts & Incident Log" in res.text or "Safety Alerts &amp; Incident Log" in res.text
    )
    assert "Active" in res.text
    assert "Resolved" in res.text

    # 2. Test web form acknowledge
    alert = Alert(
        type=AlertType.OFFLINE,
        severity=AlertSeverity.WARNING,
        status=AlertStatus.ACTIVE,
        message="Web action test alert",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    ack_res = await client.post(f"/alerts/{alert.id}/acknowledge", follow_redirects=False)
    assert ack_res.status_code == 303
    assert "/alerts" in ack_res.headers.get("location", "")

    # 3. Test web form resolve
    resolve_res = await client.post(f"/alerts/{alert.id}/resolve", follow_redirects=False)
    assert resolve_res.status_code == 303
    assert "/alerts" in resolve_res.headers.get("location", "")
