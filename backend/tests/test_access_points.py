"""Automated tests for Access Point domain models, services, REST API, and web views."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.access_point import AccessPointCreate, AccessPointUpdate
from app.schemas.zone import ZoneCreate
from app.services import access_point_service, zone_service


@pytest.mark.asyncio
async def test_access_point_service_lifecycle(db_session: AsyncSession) -> None:
    """Verify access point creation, MAC formatting, duplicate detection, and soft-delete."""
    zone = await zone_service.create_zone(
        db_session, ZoneCreate(name="AP Test Zone Lifecycle")
    )

    ap_in = AccessPointCreate(
        name="AP-Primary-01",
        bssid="aa:bb:cc:dd:ee:01",
        channel=6,
        zone_id=zone.id,
    )
    ap = await access_point_service.create_access_point(db_session, ap_in)
    assert ap.id is not None
    assert ap.name == "AP-Primary-01"
    assert ap.bssid == "AA:BB:CC:DD:EE:01"  # Normalized to uppercase
    assert ap.channel == 6

    # Duplicate BSSID rejected
    with pytest.raises(ConflictError):
        await access_point_service.create_access_point(db_session, ap_in)

    # Retrieval
    fetched = await access_point_service.get_access_point_by_id(db_session, ap.id)
    assert fetched.bssid == "AA:BB:CC:DD:EE:01"

    # Update
    updated = await access_point_service.update_access_point(
        db_session, ap.id, AccessPointUpdate(name="AP-Primary-Renamed")
    )
    assert updated.name == "AP-Primary-Renamed"

    # Soft delete
    deactivated = await access_point_service.deactivate_access_point(db_session, ap.id)
    assert deactivated.is_active is False


@pytest.mark.asyncio
async def test_access_point_api_endpoints(
    client: AsyncClient, admin_headers: dict, teacher_headers: dict, db_session: AsyncSession
) -> None:
    """Verify REST API authorization and CRUD operations on /api/v1/access-points."""
    # Setup a zone
    zone = await zone_service.create_zone(
        db_session, ZoneCreate(name="AP API Test Zone")
    )

    # 1. Unauthenticated request rejected
    resp = await client.get("/api/v1/access-points")
    assert resp.status_code == 401

    # 2. Teacher can view access points
    resp = await client.get("/api/v1/access-points", headers=teacher_headers)
    assert resp.status_code == 200

    # 3. Teacher cannot create access point
    ap_payload = {
        "name": "Teacher-AP-01",
        "bssid": "11:22:33:44:55:66",
        "channel": 1,
        "zone_id": str(zone.id),
    }
    resp = await client.post("/api/v1/access-points", headers=teacher_headers, json=ap_payload)
    assert resp.status_code == 403

    # 4. Admin can create access point
    resp = await client.post("/api/v1/access-points", headers=admin_headers, json=ap_payload)
    assert resp.status_code == 201
    created_ap = resp.json()
    ap_id = created_ap["id"]
    assert created_ap["bssid"] == "11:22:33:44:55:66"
    assert created_ap["name"] == "Teacher-AP-01"

    # 5. Admin can update access point
    resp = await client.put(
        f"/api/v1/access-points/{ap_id}",
        headers=admin_headers,
        json={"name": "Admin-Updated-AP-01"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Admin-Updated-AP-01"

    # 6. Admin can deactivate access point (returns 200 with is_active=False)
    resp = await client.delete(f"/api/v1/access-points/{ap_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
