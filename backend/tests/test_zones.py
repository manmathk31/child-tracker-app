"""Automated tests for Zone domain models, services, REST API, and web views."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.zone import ZoneCreate, ZoneUpdate
from app.services import zone_service


@pytest.mark.asyncio
async def test_zone_service_lifecycle(db_session: AsyncSession) -> None:
    """Verify zone creation, retrieval, unique constraint, and soft-delete."""
    zone_in = ZoneCreate(
        name="Library North Wing",
        description="Silent study area",
        building="Main Academic",
        floor="Floor 2",
    )
    zone = await zone_service.create_zone(db_session, zone_in)
    assert zone.id is not None
    assert zone.name == "Library North Wing"
    assert zone.is_active is True

    # Duplicate name raises ConflictError
    with pytest.raises(ConflictError):
        await zone_service.create_zone(db_session, zone_in)

    # Retrieval
    fetched = await zone_service.get_zone_by_id(db_session, zone.id)
    assert fetched.name == "Library North Wing"

    # Nonexistent zone raises NotFoundError
    with pytest.raises(NotFoundError):
        await zone_service.get_zone_by_id(db_session, uuid.uuid4())

    # Update
    updated = await zone_service.update_zone(
        db_session, zone.id, ZoneUpdate(name="Library North Reading Room")
    )
    assert updated.name == "Library North Reading Room"

    # Soft delete
    deactivated = await zone_service.deactivate_zone(db_session, zone.id)
    assert deactivated.is_active is False


@pytest.mark.asyncio
async def test_zone_api_endpoints(
    client: AsyncClient, admin_headers: dict, teacher_headers: dict
) -> None:
    """Verify REST API authorization and CRUD operations on /api/v1/zones."""
    # 1. Unauthenticated request rejected
    resp = await client.get("/api/v1/zones")
    assert resp.status_code == 401

    # 2. Teacher can list zones
    resp = await client.get("/api/v1/zones", headers=teacher_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 3. Teacher cannot create a zone (Admin only -> 403)
    resp = await client.post(
        "/api/v1/zones",
        headers=teacher_headers,
        json={"name": "Restricted Zone Teacher Test", "building": "Building A"},
    )
    assert resp.status_code == 403

    # 4. Admin can create a zone
    zone_data = {
        "name": "Science Lab A",
        "description": "Chemistry and physics lab",
        "building": "Science Wing",
        "floor": "Floor 1",
    }
    resp = await client.post("/api/v1/zones", headers=admin_headers, json=zone_data)
    assert resp.status_code == 201
    created_zone = resp.json()
    zone_id = created_zone["id"]
    assert created_zone["name"] == "Science Lab A"

    # 5. Duplicate name returns 409
    resp = await client.post("/api/v1/zones", headers=admin_headers, json=zone_data)
    assert resp.status_code == 409

    # 6. Admin can update zone
    resp = await client.put(
        f"/api/v1/zones/{zone_id}",
        headers=admin_headers,
        json={"description": "Updated chemistry lab"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated chemistry lab"

    # 7. Admin can delete (soft-delete) zone
    resp = await client.delete(f"/api/v1/zones/{zone_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False



@pytest.mark.asyncio
async def test_zone_web_views(client: AsyncClient, admin_user) -> None:
    """Verify HTML web views for zone management."""
    # Unauthenticated redirect to /login
    resp = await client.get("/zones", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]

    # Authenticated admin cookie
    from app.core.security import create_access_token
    token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    cookies = {"access_token": token}

    resp = await client.get("/zones", cookies=cookies)
    assert resp.status_code == 200
    assert "School Zones" in resp.text

    # GET /zones/new form
    resp = await client.get("/zones/new", cookies=cookies)
    assert resp.status_code == 200
    assert "Add New Zone" in resp.text

    # POST /zones/new submission
    resp = await client.post(
        "/zones/new",
        cookies=cookies,
        data={
            "name": "Cafeteria Main Hall",
            "description": "Dining area",
            "building": "Campus Center",
            "floor": "Ground",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/zones"
