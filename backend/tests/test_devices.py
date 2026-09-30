"""Automated tests for Device (ESP32 Wearable) domain models, services, REST API, and web views."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.device import DeviceStatus
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.services import device_service


@pytest.mark.asyncio
async def test_device_service_lifecycle(db_session: AsyncSession) -> None:
    """Verify wearable registration, normalization, uniqueness checks, and soft-delete."""
    dev_in = DeviceCreate(
        device_code="TAG-2001",
        mac_address="24:6f:28:ab:cd:ef",
        battery_percent=95,
        firmware_version="1.0.0",
    )
    device = await device_service.create_device(db_session, dev_in)
    assert device.id is not None
    assert device.device_code == "TAG-2001"
    assert device.mac_address == "24:6F:28:AB:CD:EF"
    assert device.battery_percent == 95
    assert device.status == DeviceStatus.OFFLINE

    # Duplicate device_code raises ConflictError
    with pytest.raises(ConflictError):
        await device_service.create_device(
            db_session,
            DeviceCreate(device_code="TAG-2001", mac_address="24:6f:28:ab:cd:00"),
        )

    # Duplicate MAC address raises ConflictError
    with pytest.raises(ConflictError):
        await device_service.create_device(
            db_session,
            DeviceCreate(device_code="TAG-2002", mac_address="24:6f:28:ab:cd:ef"),
        )

    # Retrieval by code and MAC
    by_code = await device_service.get_device_by_code(db_session, "tag-2001")
    assert by_code is not None
    assert by_code.id == device.id

    by_mac = await device_service.get_device_by_mac(db_session, "24-6f-28-ab-cd-ef")
    assert by_mac is not None
    assert by_mac.id == device.id

    # Update
    updated = await device_service.update_device(
        db_session, device.id, DeviceUpdate(battery_percent=88, firmware_version="1.1.0")
    )
    assert updated.battery_percent == 88
    assert updated.firmware_version == "1.1.0"

    # Soft delete
    deactivated = await device_service.deactivate_device(db_session, device.id)
    assert deactivated.is_active is False


@pytest.mark.asyncio
async def test_device_api_endpoints(
    client: AsyncClient, admin_headers: dict, teacher_headers: dict
) -> None:
    """Verify REST API authorization and CRUD operations on /api/v1/devices."""
    # 1. Unauthenticated request rejected
    resp = await client.get("/api/v1/devices")
    assert resp.status_code == 401

    # 2. Teacher can view devices
    resp = await client.get("/api/v1/devices", headers=teacher_headers)
    assert resp.status_code == 200

    # 3. Teacher cannot register device
    dev_payload = {
        "device_code": "TAG-TEACHER",
        "mac_address": "AA:BB:CC:11:22:33",
        "battery_percent": 100,
    }
    resp = await client.post("/api/v1/devices", headers=teacher_headers, json=dev_payload)
    assert resp.status_code == 403

    # 4. Admin registers device
    admin_payload = {
        "device_code": "TAG-3001",
        "mac_address": "AA:11:22:33:44:55",
        "battery_percent": 90,
        "firmware_version": "1.0.0",
    }
    resp = await client.post("/api/v1/devices", headers=admin_headers, json=admin_payload)
    assert resp.status_code == 201
    created_dev = resp.json()
    dev_id = created_dev["id"]
    assert created_dev["device_code"] == "TAG-3001"

    # 5. Admin updates device
    resp = await client.put(
        f"/api/v1/devices/{dev_id}",
        headers=admin_headers,
        json={"battery_percent": 45},
    )
    assert resp.status_code == 200
    assert resp.json()["battery_percent"] == 45

    # 6. Admin deletes device
    resp = await client.delete(f"/api/v1/devices/{dev_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

