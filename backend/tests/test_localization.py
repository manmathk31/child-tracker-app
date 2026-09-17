"""Automated tests for Phase 4: Indoor Localization Engine, Hysteresis, and Telemetry Ingestion."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, DeviceStatus
from app.models.location_record import LocationRecord
from app.schemas.access_point import AccessPointCreate
from app.schemas.device import DeviceCreate
from app.schemas.fingerprint import CalibrationBatchIn, FingerprintCreate, ScanSampleIn
from app.schemas.location import LocationEstimate
from app.schemas.student import StudentCreate
from app.schemas.zone import ZoneCreate
from app.services import (
    access_point_service,
    device_service,
    fingerprint_service,
    localization_service,
    student_service,
    zone_service,
)


@pytest.mark.asyncio
async def test_probabilistic_localization_matching(db_session: AsyncSession, admin_user) -> None:
    """Verify probabilistic RSSI vector localization against known ground-truth fingerprints."""
    # 1. Setup two physical zones
    zone_a = await zone_service.create_zone(db_session, ZoneCreate(name="Classroom 101"))
    zone_b = await zone_service.create_zone(db_session, ZoneCreate(name="Library West"))

    # 2. Setup Access Points
    ap1 = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(
            name="AP-Classroom-1",
            bssid="10:00:00:00:00:01",
            channel=1,
            zone_id=zone_a.id,
        ),
    )
    ap2 = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(
            name="AP-Classroom-2",
            bssid="10:00:00:00:00:02",
            channel=6,
            zone_id=zone_a.id,
        ),
    )
    ap3 = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(
            name="AP-Library-1",
            bssid="20:00:00:00:00:01",
            channel=11,
            zone_id=zone_b.id,
        ),
    )
    ap4 = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(
            name="AP-Library-2",
            bssid="20:00:00:00:00:02",
            channel=36,
            zone_id=zone_b.id,
        ),
    )

    # 3. Create and activate fingerprint for Classroom 101
    # AP1 ~ -55 dBm, AP2 ~ -58 dBm, AP3 ~ -86 dBm
    fp_a = await fingerprint_service.create_fingerprint(
        db_session,
        admin_user.id,
        FingerprintCreate(zone_id=zone_a.id, target_ap_ids=[ap1.id, ap2.id, ap3.id]),
    )
    for _ in range(5):
        await fingerprint_service.ingest_samples_batch(
            db_session,
            fp_a.id,
            CalibrationBatchIn(
                scan=[
                    ScanSampleIn(bssid="10:00:00:00:00:01", rssi=-55),
                    ScanSampleIn(bssid="10:00:00:00:00:02", rssi=-58),
                    ScanSampleIn(bssid="20:00:00:00:00:01", rssi=-86),
                ]
            ),
        )
    await fingerprint_service.activate_fingerprint(db_session, fp_a.id)

    # 4. Create and activate fingerprint for Library West
    # AP3 ~ -50 dBm, AP4 ~ -54 dBm, AP1 ~ -89 dBm
    fp_b = await fingerprint_service.create_fingerprint(
        db_session,
        admin_user.id,
        FingerprintCreate(zone_id=zone_b.id, target_ap_ids=[ap1.id, ap3.id, ap4.id]),
    )
    for _ in range(5):
        await fingerprint_service.ingest_samples_batch(
            db_session,
            fp_b.id,
            CalibrationBatchIn(
                scan=[
                    ScanSampleIn(bssid="20:00:00:00:00:01", rssi=-50),
                    ScanSampleIn(bssid="20:00:00:00:00:02", rssi=-54),
                    ScanSampleIn(bssid="10:00:00:00:00:01", rssi=-89),
                ]
            ),
        )
    await fingerprint_service.activate_fingerprint(db_session, fp_b.id)

    # Invalidate cache to force reload
    localization_service.invalidate_fingerprint_cache()
    cached_profiles = await localization_service.get_cached_active_fingerprints(db_session)
    assert len(cached_profiles) >= 2

    # 5. Test vector clearly matching Classroom 101
    scan_classroom = {
        "10:00:00:00:00:01": -54,
        "10:00:00:00:00:02": -59,
        "20:00:00:00:00:01": -85,
    }
    est_classroom = localization_service.estimate_position_from_profiles(
        scan_map=scan_classroom,
        profiles=cached_profiles,
        min_confidence_threshold=0.45,
    )
    assert est_classroom.zone_name == "Classroom 101"
    assert est_classroom.is_low_confidence is False
    assert est_classroom.confidence >= 0.70

    # 6. Test vector clearly matching Library West
    scan_library = {
        "20:00:00:00:00:01": -51,
        "20:00:00:00:00:02": -53,
    }
    est_library = localization_service.estimate_position_from_profiles(
        scan_map=scan_library,
        profiles=cached_profiles,
        min_confidence_threshold=0.45,
    )
    assert est_library.zone_name == "Library West"
    assert est_library.is_low_confidence is False
    assert est_library.confidence >= 0.70


@pytest.mark.asyncio
async def test_low_confidence_and_ambiguous_scans(db_session: AsyncSession) -> None:
    """Verify weak, distant, or ambiguous scans fall back to Unknown/Low Confidence."""
    cached_profiles = await localization_service.get_cached_active_fingerprints(db_session)

    # 1. Completely unknown BSSIDs
    scan_unknown = {
        "FF:FF:FF:00:00:01": -60,
        "FF:FF:FF:00:00:02": -65,
    }
    est_unknown = localization_service.estimate_position_from_profiles(
        scan_map=scan_unknown,
        profiles=cached_profiles,
        min_confidence_threshold=0.45,
    )
    assert est_unknown.zone_id is None
    assert est_unknown.is_low_confidence is True
    assert est_unknown.confidence == 0.0

    # 2. Extreme signal distance / very weak signals far from all rooms
    scan_distant = {
        "10:00:00:00:00:01": -95,
        "20:00:00:00:00:01": -98,
    }
    est_distant = localization_service.estimate_position_from_profiles(
        scan_map=scan_distant,
        profiles=cached_profiles,
        min_confidence_threshold=0.45,
    )
    assert est_distant.zone_id is None
    assert est_distant.is_low_confidence is True
    assert est_distant.confidence < 0.45


def test_temporal_hysteresis_smoothing() -> None:
    """Verify temporal hysteresis suppresses transient flutter and confirms sustained moves."""
    localization_service.clear_hysteresis_state()
    device_id = uuid.uuid4()
    zone_1 = uuid.uuid4()
    zone_2 = uuid.uuid4()

    # Reading 1: Stable Zone 1
    est1 = LocationEstimate(
        zone_id=zone_1,
        zone_name="Room 1",
        confidence=0.80,
        is_low_confidence=False,
    )
    out1 = localization_service.apply_temporal_hysteresis(device_id, est1)
    assert out1.zone_id == zone_1

    # Reading 2: Stable Zone 1
    est2 = LocationEstimate(
        zone_id=zone_1,
        zone_name="Room 1",
        confidence=0.82,
        is_low_confidence=False,
    )
    out2 = localization_service.apply_temporal_hysteresis(device_id, est2)
    assert out2.zone_id == zone_1

    # Reading 3: Transient Flutter to Zone 2 with moderate confidence (e.g. 0.72)
    flutter = LocationEstimate(
        zone_id=zone_2,
        zone_name="Room 2",
        confidence=0.72,
        is_low_confidence=False,
    )
    out3 = localization_service.apply_temporal_hysteresis(device_id, flutter)
    # MUST retain previous stable Zone 1
    assert out3.zone_id == zone_1
    assert out3.zone_name == "Room 1"

    # Reading 4: Sustained reading in Zone 2 (second consecutive occurrence)
    sustained = LocationEstimate(
        zone_id=zone_2,
        zone_name="Room 2",
        confidence=0.74,
        is_low_confidence=False,
    )
    out4 = localization_service.apply_temporal_hysteresis(device_id, sustained)
    # Transition to Zone 2 is confirmed
    assert out4.zone_id == zone_2
    assert out4.zone_name == "Room 2"


@pytest.mark.asyncio
async def test_telemetry_ingestion_and_audit_trail(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    admin_headers: dict,
) -> None:
    """Verify telemetry ingestion REST API, audit persistence, and history web views."""
    # 1. Register a wearable device and an enrolled student
    device = await device_service.create_device(
        db_session,
        DeviceCreate(
            device_code="WB-LOC-01",
            mac_address="CC:CC:CC:11:22:33",
        ),
    )
    student = await student_service.create_student(
        db_session,
        StudentCreate(
            student_code="LOC-STU-01",
            full_name="Lucas Tracker",
            class_name="Grade 4B",
            age=10,
            device_id=device.id,
        ),
    )

    # Invalidate cache to ensure active profiles loaded
    localization_service.invalidate_fingerprint_cache()
    localization_service.clear_hysteresis_state()

    # 2. Ingest telemetry from the hardware tag
    payload = {
        "device_id": "WB-LOC-01",
        "mac_address": "CC:CC:CC:11:22:33",
        "battery_percent": 88,
        "firmware_version": "v1.2.0",
        "scan": [
            {"bssid": "10:00:00:00:00:01", "rssi": -55},
            {"bssid": "10:00:00:00:00:02", "rssi": -58},
        ],
        "events": {"sos_button_pressed": False},
    }

    resp = await client.post("/api/v1/tracking/ingest", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ack"
    assert data["device_id"] == "WB-LOC-01"
    assert "confidence" in data
    assert data["assigned_zone"] == "Classroom 101"

    # 3. Verify device state updated in DB
    dev_stmt = (
        select(Device)
        .where(Device.id == device.id)
        .execution_options(populate_existing=True)
    )
    dev_res = await db_session.execute(dev_stmt)
    updated_dev = dev_res.scalar_one()
    assert updated_dev.status == DeviceStatus.ONLINE
    assert updated_dev.battery_percent == 88
    assert updated_dev.last_seen_at is not None

    # 4. Verify LocationRecord created in DB
    from sqlalchemy.orm import selectinload

    rec_stmt = (
        select(LocationRecord)
        .where(LocationRecord.student_id == student.id)
        .options(selectinload(LocationRecord.zone))
    )
    rec_res = await db_session.execute(rec_stmt)
    records = rec_res.scalars().all()
    assert len(records) == 1
    rec = records[0]
    assert rec.device_id == device.id
    assert rec.zone_name == "Classroom 101"
    assert rec.confidence >= 0.70

    # 5. Test Live Location API: GET /api/v1/students/{id}/location
    loc_resp = await client.get(f"/api/v1/students/{student.id}/location", headers=admin_headers)
    assert loc_resp.status_code == 200
    loc_data = loc_resp.json()
    assert loc_data["student_id"] == str(student.id)
    assert loc_data["current_zone_name"] == "Classroom 101"
    assert loc_data["device_code"] == "WB-LOC-01"
    assert loc_data["battery_percent"] == 88
    assert len(loc_data["recent_breadcrumbs"]) == 1

    # 6. Test History API: GET /api/v1/students/{id}/history
    hist_resp = await client.get(f"/api/v1/students/{student.id}/history", headers=admin_headers)
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert len(hist_data) == 1
    assert hist_data[0]["student_id"] == str(student.id)

    # 7. Test Web View: GET /students/{id}/history
    from app.core.security import create_access_token

    token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    cookies = {"access_token": token}

    html_resp = await client.get(f"/students/{student.id}/history", cookies=cookies)
    assert html_resp.status_code == 200
    assert "Lucas Tracker" in html_resp.text
    assert "Classroom 101" in html_resp.text
    assert (
        "Movement &amp; Positioning Breadcrumbs" in html_resp.text
        or "Movement & Positioning Breadcrumbs" in html_resp.text
    )

    # 8. Test Error Case: Ingest from unregistered device -> 404
    bad_payload = dict(payload, device_id="UNKNOWN-TAG", mac_address="00:00:00:00:00:00")
    bad_resp = await client.post("/api/v1/tracking/ingest", json=bad_payload)
    assert bad_resp.status_code == 404
    assert "Device" in bad_resp.json()["error"]["message"]

    # 9. Test Error Case: Invalid battery percent -> 422
    invalid_payload = dict(payload, battery_percent=150)
    invalid_resp = await client.post("/api/v1/tracking/ingest", json=invalid_payload)
    assert invalid_resp.status_code == 422
