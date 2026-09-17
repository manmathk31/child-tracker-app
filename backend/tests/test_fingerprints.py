"""Automated tests for Fingerprint Collection, AP Filtering, and Calibration Survey domain."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.fingerprint import FingerprintStatus
from app.schemas.access_point import AccessPointCreate
from app.schemas.fingerprint import CalibrationBatchIn, FingerprintCreate, ScanSampleIn
from app.schemas.zone import ZoneCreate
from app.services import access_point_service, fingerprint_service, zone_service


@pytest.mark.asyncio
async def test_fingerprint_filtering_and_statistics(db_session: AsyncSession, admin_user) -> None:
    """Verify AP whitelisting, noise filtering, mathematical stats calculation, and single active survey enforcement."""
    # 1. Setup zone and 3 registered APs
    zone = await zone_service.create_zone(db_session, ZoneCreate(name="Science Lab Calibration"))
    ap1 = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(name="Lab-AP-1", bssid="AA:AA:AA:01:01:01", channel=1, zone_id=zone.id),
    )
    ap2 = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(name="Lab-AP-2", bssid="AA:AA:AA:02:02:02", channel=6, zone_id=zone.id),
    )
    ap3 = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(name="Lab-AP-3", bssid="AA:AA:AA:03:03:03", channel=11, zone_id=zone.id),
    )

    # 2. Create survey whitelisting only ap1 and ap2 (ap3 excluded, min_rssi_cutoff = -85)
    fp_in = FingerprintCreate(
        zone_id=zone.id,
        min_rssi_cutoff=-85,
        target_ap_ids=[ap1.id, ap2.id],
        notes="Automated unit test survey",
    )
    fp = await fingerprint_service.create_fingerprint(db_session, admin_user.id, fp_in)
    assert fp.id is not None
    assert fp.status == FingerprintStatus.DRAFT
    assert fp.sample_count == 0

    # 3. Ingest batch of scans containing:
    # - ap1 with valid readings: -60, -62, -58
    # - ap2 with valid readings: -70, -72, -68
    # - ap3 with reading: -65 (SHOULD BE FILTERED OUT by whitelist)
    # - rogue unlisted BSSID: -50 (SHOULD BE FILTERED OUT because not registered)
    # - ap1 with weak reading: -92 (SHOULD BE FILTERED OUT because < -85 cutoff)
    for _ in range(5):
        batch = CalibrationBatchIn(
            scan=[
                ScanSampleIn(bssid="aa:aa:aa:01:01:01", rssi=-60, channel=1),
                ScanSampleIn(bssid="aa:aa:aa:01:01:01", rssi=-92, channel=1),  # filtered out (< -85)
                ScanSampleIn(bssid="aa:aa:aa:02:02:02", rssi=-70, channel=6),
                ScanSampleIn(bssid="aa:aa:aa:03:03:03", rssi=-65, channel=11),  # filtered out (not in whitelist)
                ScanSampleIn(bssid="ff:ff:ff:99:99:99", rssi=-50, channel=6),   # filtered out (unregistered)
            ]
        )
        accepted = await fingerprint_service.ingest_samples_batch(db_session, fp.id, batch)
        # Should accept exactly 2 readings per sweep (ap1 at -60 and ap2 at -70)
        assert accepted == 2

    # Verify survey scan counter incremented
    reloaded_fp = await fingerprint_service.get_fingerprint_by_id(db_session, fp.id)
    assert reloaded_fp.sample_count == 5

    # 4. Calculate AP Statistics
    analyzed = await fingerprint_service.calculate_and_save_ap_stats(db_session, fp.id)
    assert len(analyzed.ap_stats) == 2  # Only ap1 and ap2
    assert analyzed.quality_score is not None
    assert 0.0 <= analyzed.quality_score <= 1.0

    stat1 = next(s for s in analyzed.ap_stats if s.access_point_id == ap1.id)
    assert stat1.median_rssi == -60.0
    assert stat1.mean_rssi == -60.0
    assert stat1.sample_count == 5

    # 5. Activate survey
    activated = await fingerprint_service.activate_fingerprint(db_session, fp.id)
    assert activated.status == FingerprintStatus.ACTIVE

    active_fp = await fingerprint_service.get_active_fingerprint_for_zone(db_session, zone.id)
    assert active_fp is not None
    assert active_fp.id == activated.id

    # 6. Single active survey rule: create second survey for same zone and activate it
    fp2_in = FingerprintCreate(zone_id=zone.id, min_rssi_cutoff=-90)
    fp2 = await fingerprint_service.create_fingerprint(db_session, admin_user.id, fp2_in)
    await fingerprint_service.ingest_samples_batch(
        db_session, fp2.id, CalibrationBatchIn(scan=[ScanSampleIn(bssid="aa:aa:aa:01:01:01", rssi=-55)])
    )
    activated2 = await fingerprint_service.activate_fingerprint(db_session, fp2.id)
    assert activated2.status == FingerprintStatus.ACTIVE

    # The previous survey must now be ARCHIVED
    old_fp = await fingerprint_service.get_fingerprint_by_id(db_session, fp.id)
    assert old_fp.status == FingerprintStatus.ARCHIVED


@pytest.mark.asyncio
async def test_fingerprint_api_endpoints(
    client: AsyncClient, admin_headers: dict, teacher_headers: dict, db_session: AsyncSession
) -> None:
    """Verify REST API authorization, automated sample streaming, and activation."""
    zone = await zone_service.create_zone(db_session, ZoneCreate(name="Library Study Zone"))
    ap = await access_point_service.create_access_point(
        db_session,
        AccessPointCreate(name="Lib-AP-Primary", bssid="BB:BB:BB:11:11:11", channel=1, zone_id=zone.id),
    )

    # 1. Unauthenticated request rejected
    resp = await client.get("/api/v1/fingerprints")
    assert resp.status_code == 401

    # 2. Teacher cannot create survey
    fp_payload = {
        "zone_id": str(zone.id),
        "min_rssi_cutoff": -85,
        "notes": "Teacher attempt",
    }
    resp = await client.post("/api/v1/fingerprints", headers=teacher_headers, json=fp_payload)
    assert resp.status_code == 403

    # 3. Admin creates survey
    resp = await client.post("/api/v1/fingerprints", headers=admin_headers, json=fp_payload)
    assert resp.status_code == 201
    created_fp = resp.json()
    fp_id = created_fp["id"]
    assert created_fp["status"] == "draft"

    # 4. Stream automated scan samples
    batch_data = {
        "device_id": "CALIB-TOOL-01",
        "scan": [
            {"bssid": "bb:bb:bb:11:11:11", "rssi": -55, "channel": 1},
            {"bssid": "bb:bb:bb:11:11:11", "rssi": -57, "channel": 1},
        ],
    }
    resp = await client.post(f"/api/v1/fingerprints/{fp_id}/samples", json=batch_data)
    assert resp.status_code == 200
    assert resp.json()["accepted_readings"] == 2

    # 5. Teacher cannot activate survey
    resp = await client.post(f"/api/v1/fingerprints/{fp_id}/activate", headers=teacher_headers)
    assert resp.status_code == 403

    # 6. Admin activates survey
    resp = await client.post(f"/api/v1/fingerprints/{fp_id}/activate", headers=admin_headers)
    assert resp.status_code == 200
    active_report = resp.json()
    assert active_report["status"] == "active"
    assert len(active_report["ap_stats"]) == 1
    assert active_report["ap_stats"][0]["mean_rssi"] == -56.0


@pytest.mark.asyncio
async def test_fingerprint_web_views(client: AsyncClient, admin_user) -> None:
    """Verify HTML web views and interactive calibration dashboard."""
    from app.core.security import create_access_token

    token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    cookies = {"access_token": token}

    # GET /fingerprints list view
    resp = await client.get("/fingerprints", cookies=cookies)
    assert resp.status_code == 200
    assert "Radio Fingerprint Calibration" in resp.text

    # GET /fingerprints/new setup form
    resp = await client.get("/fingerprints/new", cookies=cookies)
    assert resp.status_code == 200
    assert "Configure Calibration Session" in resp.text
    assert "Access Point Filtering" in resp.text
