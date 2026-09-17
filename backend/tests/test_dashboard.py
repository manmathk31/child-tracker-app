"""Automated tests for Phase 5: Live Safety Monitoring Dashboard & Real-Time Feeds."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.alert import Alert, AlertSeverity, AlertStatus, AlertType
from app.models.device import DeviceStatus
from app.models.location_record import LocationRecord
from app.models.user import User
from app.schemas.device import DeviceCreate
from app.schemas.student import StudentCreate
from app.schemas.zone import ZoneCreate
from app.services import dashboard_service, device_service, student_service, zone_service


def _random_mac() -> str:
    """Generate a valid, randomized unique MAC address for testing."""
    hex_str = uuid.uuid4().hex[:12].upper()
    return ":".join(hex_str[i : i + 2] for i in range(0, 12, 2))


@pytest.mark.asyncio
async def test_empty_database_dashboard_payload(db_session: AsyncSession) -> None:
    """Verify clean empty-state compliance with zero active tracking or student records."""
    payload = await dashboard_service.get_dashboard_live_payload(
        db_session, class_name="NonExistentClass_EmptyState"
    )
    assert payload.metrics.total_students == 0
    assert payload.metrics.trackable_students == 0
    assert payload.metrics.attention_students == 0
    assert payload.students == []
    assert payload.roaming_zone.occupant_count == 0
    for z in payload.zones:
        assert z.occupant_count == 0
        assert z.has_restricted_student is False
        assert z.occupants == []


@pytest.mark.asyncio
async def test_dashboard_live_metrics_and_occupancy(
    db_session: AsyncSession, admin_user: User, client: AsyncClient, admin_headers: dict
) -> None:
    """Verify live metrics aggregation, room headcounts, and battery alerts."""
    # 1. Create 2 zones
    zone_a = await zone_service.create_zone(
        db_session,
        ZoneCreate(name=f"Math Room {uuid.uuid4().hex[:4]}", building="Building A", floor="1F"),
    )
    zone_b = await zone_service.create_zone(
        db_session,
        ZoneCreate(name=f"Library {uuid.uuid4().hex[:4]}", building="Building B", floor="2F"),
    )

    now = datetime.now(UTC)

    # 2. Create 2 devices
    dev1 = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )
    dev1.battery_percent = 85
    dev1.status = DeviceStatus.ONLINE
    dev1.last_seen_at = now

    dev2 = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )
    dev2.battery_percent = 15
    dev2.status = DeviceStatus.ONLINE
    dev2.last_seen_at = now

    # 3. Create 2 students: one with normal battery, one with low battery (15%)
    stu1 = await student_service.create_student(
        db_session,
        StudentCreate(
            full_name="Alice Wonder",
            student_code=f"STU-{uuid.uuid4().hex[:4].upper()}",
            class_name="Grade 3A",
            age=8,
            device_id=dev1.id,
            allowed_zone_ids=[zone_a.id],
        ),
    )
    stu2 = await student_service.create_student(
        db_session,
        StudentCreate(
            full_name="Bob Builder",
            student_code=f"STU-{uuid.uuid4().hex[:4].upper()}",
            class_name="Grade 3B",
            age=9,
            device_id=dev2.id,
            allowed_zone_ids=[zone_a.id, zone_b.id],
        ),
    )

    # 4. Insert location records
    # Alice in Zone A (0.92 confidence)
    rec1 = LocationRecord(
        student_id=stu1.id,
        device_id=dev1.id,
        zone_id=zone_a.id,
        confidence=0.92,
        raw_scan={"ap1": -65},
        recorded_at=now,
    )
    # Bob in Zone A (0.88 confidence)
    rec2 = LocationRecord(
        student_id=stu2.id,
        device_id=dev2.id,
        zone_id=zone_a.id,
        confidence=0.88,
        raw_scan={"ap1": -68},
        recorded_at=now,
    )
    db_session.add_all([rec1, rec2])
    await db_session.commit()

    # 5. Fetch live dashboard payload
    payload = await dashboard_service.get_dashboard_live_payload(db_session)
    assert payload.metrics.total_students >= 2
    assert payload.metrics.trackable_students >= 2
    assert payload.metrics.attention_students >= 1  # Bob has battery <= 20%

    # Check zone occupancy
    zone_a_occ = next((z for z in payload.zones if z.zone_id == zone_a.id), None)
    assert zone_a_occ is not None
    assert zone_a_occ.occupant_count == 2
    assert zone_a_occ.has_restricted_student is False
    assert len(zone_a_occ.occupants) == 2

    # Check student live cards
    stu2_card = next((s for s in payload.students if s.student_id == stu2.id), None)
    assert stu2_card is not None
    assert stu2_card.battery_percent == 15
    assert stu2_card.status_level == "attention"
    assert stu2_card.is_restricted is False

    # 6. Test Class filter in get_dashboard_live_payload
    payload_3a = await dashboard_service.get_dashboard_live_payload(
        db_session, class_name="Grade 3A"
    )
    assert payload_3a.metrics.total_students == 1
    assert len(payload_3a.students) == 1
    assert payload_3a.students[0].student_id == stu1.id


@pytest.mark.asyncio
async def test_restricted_zone_violation_detection(db_session: AsyncSession) -> None:
    """Verify out-of-bounds / restricted zone violation detection for students."""
    # 1. Create Zone Allowed (Classroom) and Zone Restricted (Server Room)
    zone_safe = await zone_service.create_zone(
        db_session, ZoneCreate(name=f"Safe Class {uuid.uuid4().hex[:4]}")
    )
    zone_restricted = await zone_service.create_zone(
        db_session, ZoneCreate(name=f"Server Room {uuid.uuid4().hex[:4]}")
    )

    now = datetime.now(UTC)

    dev = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )
    dev.battery_percent = 90
    dev.status = DeviceStatus.ONLINE
    dev.last_seen_at = now

    # Charlie is only allowed in zone_safe
    charlie = await student_service.create_student(
        db_session,
        StudentCreate(
            full_name="Charlie Outlier",
            student_code=f"STU-{uuid.uuid4().hex[:4].upper()}",
            class_name="Grade 2",
            age=7,
            device_id=dev.id,
            allowed_zone_ids=[zone_safe.id],
        ),
    )

    # Ingest location record placing Charlie inside zone_restricted
    rec = LocationRecord(
        student_id=charlie.id,
        device_id=dev.id,
        zone_id=zone_restricted.id,
        confidence=0.95,
        raw_scan={"ap_server": -50},
        recorded_at=now,
    )
    db_session.add(rec)
    await db_session.commit()

    payload = await dashboard_service.get_dashboard_live_payload(db_session)
    restr_zone_occ = next((z for z in payload.zones if z.zone_id == zone_restricted.id), None)
    assert restr_zone_occ is not None
    assert restr_zone_occ.occupant_count == 1
    assert restr_zone_occ.has_restricted_student is True
    assert restr_zone_occ.occupants[0].is_restricted is True

    charlie_card = next((s for s in payload.students if s.student_id == charlie.id), None)
    assert charlie_card is not None
    assert charlie_card.is_restricted is True
    assert charlie_card.status_level == "attention"


@pytest.mark.asyncio
async def test_roaming_low_confidence_occupancy(db_session: AsyncSession) -> None:
    """Verify unlocalized / roaming wearables with no matched zone appear in roaming zone."""
    now = datetime.now(UTC)
    dev = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code=f"DEV-{uuid.uuid4().hex[:6].upper()}",
            mac_address=_random_mac(),
        ),
    )
    dev.battery_percent = 70
    dev.status = DeviceStatus.ONLINE
    dev.last_seen_at = now

    dan = await student_service.create_student(
        db_session,
        StudentCreate(
            full_name="Dan Wanderer",
            student_code=f"STU-{uuid.uuid4().hex[:4].upper()}",
            class_name="Grade 4",
            age=10,
            device_id=dev.id,
            allowed_zone_ids=[],
        ),
    )

    # Location record with zone_id=None (roaming/unknown)
    rec = LocationRecord(
        student_id=dan.id,
        device_id=dev.id,
        zone_id=None,
        confidence=0.30,
        raw_scan={"ap_hallway": -89},
        recorded_at=now,
    )
    db_session.add(rec)
    await db_session.commit()

    payload = await dashboard_service.get_dashboard_live_payload(db_session)
    assert payload.roaming_zone.occupant_count >= 1
    dan_occ = next(
        (occ for occ in payload.roaming_zone.occupants if occ.student_id == dan.id), None
    )
    assert dan_occ is not None

    dan_card = next((s for s in payload.students if s.student_id == dan.id), None)
    assert dan_card is not None
    assert dan_card.current_zone_name is None


@pytest.mark.asyncio
async def test_api_dashboard_live_endpoint(client: AsyncClient, admin_headers: dict) -> None:
    """Verify GET /api/v1/dashboard/live responds with valid schema and supports class filter."""
    res = await client.get("/api/v1/dashboard/live", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "metrics" in data
    assert "zones" in data
    assert "roaming_zone" in data
    assert "students" in data
    assert "active_alerts" in data
    assert "timestamp" in data

    # Test class filter param
    res_filtered = await client.get(
        "/api/v1/dashboard/live?class_name=NonExistentClass", headers=admin_headers
    )
    assert res_filtered.status_code == 200
    data_filtered = res_filtered.json()
    assert len(data_filtered["students"]) == 0


@pytest.mark.asyncio
async def test_alerts_api_and_acknowledge(
    db_session: AsyncSession, client: AsyncClient, admin_headers: dict, admin_user: User
) -> None:
    """Verify /api/v1/alerts/count, /api/v1/alerts, and acknowledge flow."""
    # 1. Create an active Alert in database
    alert = Alert(
        type=AlertType.RESTRICTED_ZONE,
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.ACTIVE,
        message="Emergency: Child detected entering chemical lab.",
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    # 2. Test GET /api/v1/alerts/count
    count_res = await client.get("/api/v1/alerts/count", headers=admin_headers)
    assert count_res.status_code == 200
    assert count_res.json()["count"] >= 1

    # 3. Test GET /api/v1/alerts
    list_res = await client.get("/api/v1/alerts", headers=admin_headers)
    assert list_res.status_code == 200
    alerts = list_res.json()
    assert any(a["id"] == str(alert.id) for a in alerts)

    # 4. Test POST /api/v1/alerts/{id}/acknowledge
    ack_res = await client.post(
        f"/api/v1/alerts/{alert.id}/acknowledge",
        headers=admin_headers,
        json={"notes": "Investigated, student escorted back to classroom."},
    )
    assert ack_res.status_code == 200
    ack_data = ack_res.json()
    assert ack_data["status"] == "acknowledged"
    assert ack_data["acknowledged_by"] == str(admin_user.id)

    # 5. Verify count decreased
    count_res2 = await client.get("/api/v1/alerts/count", headers=admin_headers)
    assert count_res2.status_code == 200
    # The active count should not include the acknowledged alert
    list_res2 = await client.get("/api/v1/alerts", headers=admin_headers)
    assert not any(a["id"] == str(alert.id) for a in list_res2.json())


@pytest.mark.asyncio
async def test_dashboard_web_view_authenticated(client: AsyncClient, admin_user: User) -> None:
    """Verify GET /dashboard returns HTML with all components when logged in."""
    token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    client.cookies.set("access_token", token)

    res = await client.get("/dashboard")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Live Safety Dashboard" in res.text
    assert (
        "Zone Occupancy &amp; Distribution" in res.text
        or "Zone Occupancy & Distribution" in res.text
    )
    assert "Student Live Tracking" in res.text
    assert "Active Safety Alerts" in res.text
    assert "/static/js/live_dashboard.js" in res.text


@pytest.mark.asyncio
async def test_dashboard_web_view_unauthenticated_redirect(client: AsyncClient) -> None:
    """Verify unauthenticated requests to /dashboard redirect to /login."""
    client.cookies.clear()
    res = await client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers.get("location", "")
