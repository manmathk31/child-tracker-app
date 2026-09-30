"""Automated tests for Student domain models, services, REST API, and web views."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.device import DeviceCreate
from app.schemas.student import StudentCreate, StudentUpdate
from app.schemas.zone import ZoneCreate
from app.services import device_service, student_service, zone_service


@pytest.mark.asyncio
async def test_student_service_lifecycle(db_session: AsyncSession) -> None:
    """Verify student enrollment, device pairing, zone authorization, and release on deactivation."""
    # 1. Setup zone and device
    zone1 = await zone_service.create_zone(db_session, ZoneCreate(name="Classroom 3A"))
    zone2 = await zone_service.create_zone(db_session, ZoneCreate(name="Playground Main"))
    device = await device_service.create_device(
        db_session,
        DeviceCreate(device_code="TAG-STU-01", mac_address="12:34:56:78:90:AB"),
    )

    # 2. Enroll student
    student_in = StudentCreate(
        student_code="STU-001",
        full_name="Emma Watson",
        class_name="Grade 3A",
        age=8,
        device_id=device.id,
        allowed_zone_ids=[zone1.id, zone2.id],
    )
    student = await student_service.create_student(db_session, student_in)
    assert student.id is not None
    assert student.student_code == "STU-001"
    assert student.device is not None
    assert student.device.id == device.id
    assert len(student.allowed_zones) == 2

    # 3. Duplicate code raises ConflictError
    with pytest.raises(ConflictError):
        await student_service.create_student(
            db_session,
            StudentCreate(
                student_code="STU-001",
                full_name="Another Student",
                class_name="Grade 3A",
                age=9,
            ),
        )

    # 4. Enrolling another student with the same device raises ConflictError
    with pytest.raises(ConflictError):
        await student_service.create_student(
            db_session,
            StudentCreate(
                student_code="STU-002",
                full_name="Harry Potter",
                class_name="Grade 3A",
                age=9,
                device_id=device.id,
            ),
        )

    # 5. Update student: change name and remove one zone
    updated = await student_service.update_student(
        db_session,
        student.id,
        StudentUpdate(full_name="Emma Charlotte Watson", allowed_zone_ids=[zone1.id]),
    )
    assert updated.full_name == "Emma Charlotte Watson"
    assert len(updated.allowed_zones) == 1
    assert updated.allowed_zones[0].id == zone1.id

    # 6. Deactivate student: sets is_active=False and releases device
    deactivated = await student_service.deactivate_student(db_session, student.id)
    assert deactivated.is_active is False
    # Re-fetch device and verify unassigned
    reloaded_device = await device_service.get_device_by_id(db_session, device.id)
    assert reloaded_device.student_id is None


@pytest.mark.asyncio
async def test_student_api_endpoints(
    client: AsyncClient, admin_headers: dict, teacher_headers: dict, db_session: AsyncSession
) -> None:
    """Verify REST API authorization and CRUD operations on /api/v1/students."""
    zone = await zone_service.create_zone(db_session, ZoneCreate(name="Art Room"))

    # 1. Unauthenticated request rejected
    resp = await client.get("/api/v1/students")
    assert resp.status_code == 401

    # 2. Teacher can view students roster
    resp = await client.get("/api/v1/students", headers=teacher_headers)
    assert resp.status_code == 200

    # 3. Teacher cannot enroll student
    stu_payload = {
        "student_code": "STU-API-01",
        "full_name": "Oliver Twist",
        "class_name": "Grade 4B",
        "age": 10,
        "allowed_zone_ids": [str(zone.id)],
    }
    resp = await client.post("/api/v1/students", headers=teacher_headers, json=stu_payload)
    assert resp.status_code == 403

    # 4. Admin enrolls student
    resp = await client.post("/api/v1/students", headers=admin_headers, json=stu_payload)
    assert resp.status_code == 201
    created = resp.json()
    student_id = created["id"]
    assert created["student_code"] == "STU-API-01"
    assert len(created["allowed_zones"]) == 1

    # 5. Admin updates student
    resp = await client.put(
        f"/api/v1/students/{student_id}",
        headers=admin_headers,
        json={"age": 11},
    )
    assert resp.status_code == 200
    assert resp.json()["age"] == 11

    # 6. Admin deactivates student
    resp = await client.delete(f"/api/v1/students/{student_id}", headers=admin_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_student_web_views(client: AsyncClient, admin_user) -> None:
    """Verify HTML web views for student management."""
    from app.core.security import create_access_token
    token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    cookies = {"access_token": token}

    # GET /students list page
    resp = await client.get("/students", cookies=cookies)
    assert resp.status_code == 200
    assert "Students Roster" in resp.text

    # GET /students/new enrollment form
    resp = await client.get("/students/new", cookies=cookies)
    assert resp.status_code == 200
    assert "Enroll Student" in resp.text
