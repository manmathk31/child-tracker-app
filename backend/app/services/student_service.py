"""Business logic for student enrollment, device assignment, and zone permissions."""

import logging
import uuid
from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.device import Device
from app.models.student import Student
from app.models.zone import Zone
from app.schemas.student import StudentCreate, StudentUpdate

logger = logging.getLogger("childtrack.student_service")


async def list_students(
    db: AsyncSession,
    class_name: Optional[str] = None,
    include_inactive: bool = False,
) -> Sequence[Student]:
    """Retrieve all students with their assigned wearable and allowed zones."""
    stmt = (
        select(Student)
        .options(selectinload(Student.device), selectinload(Student.allowed_zones))
    )
    if not include_inactive:
        stmt = stmt.where(Student.is_active == True)  # noqa: E712
    if class_name:
        stmt = stmt.where(Student.class_name == class_name.strip())
    stmt = stmt.order_by(Student.full_name)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_student_by_id(db: AsyncSession, student_id: uuid.UUID) -> Student:
    """Retrieve a student profile by UUID."""
    stmt = (
        select(Student)
        .options(selectinload(Student.device), selectinload(Student.allowed_zones))
        .where(Student.id == student_id)
    )
    result = await db.execute(stmt)
    student = result.scalar_one_or_none()
    if not student:
        raise NotFoundError("Student", student_id)
    return student


async def get_student_by_code(db: AsyncSession, student_code: str) -> Optional[Student]:
    """Find a student by unique school student code."""
    stmt = select(Student).where(func.upper(Student.student_code) == student_code.strip().upper())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_student(db: AsyncSession, student_in: StudentCreate) -> Student:
    """Enroll a new student, optionally assigning a wearable and allowed zones."""
    clean_code = student_in.student_code.strip().upper()
    if await get_student_by_code(db, clean_code):
        raise ConflictError(f"Student code '{clean_code}' is already assigned.")

    # Validate device if specified
    device = None
    if student_in.device_id:
        dev_stmt = select(Device).where(Device.id == student_in.device_id)
        dev_res = await db.execute(dev_stmt)
        device = dev_res.scalar_one_or_none()
        if not device:
            raise NotFoundError("Device", student_in.device_id)
        if device.student_id:
            raise ConflictError(f"Device '{device.device_code}' is already assigned to another student.")

    # Fetch allowed zones
    zones: List[Zone] = []
    if student_in.allowed_zone_ids:
        z_stmt = select(Zone).where(Zone.id.in_(student_in.allowed_zone_ids))
        z_res = await db.execute(z_stmt)
        zones = list(z_res.scalars().all())

    student = Student(
        student_code=clean_code,
        full_name=student_in.full_name.strip(),
        class_name=student_in.class_name.strip(),
        age=student_in.age,
        photo_url=student_in.photo_url.strip() if student_in.photo_url else None,
        is_active=True,
        allowed_zones=zones,
    )
    db.add(student)
    await db.flush()

    if device:
        device.student_id = student.id

    await db.commit()
    logger.info("Enrolled student: id=%s code=%s name='%s'", student.id, student.student_code, student.full_name)
    return await get_student_by_id(db, student.id)


async def update_student(db: AsyncSession, student_id: uuid.UUID, student_in: StudentUpdate) -> Student:
    """Update student profile, device pairing, and allowed zones."""
    student = await get_student_by_id(db, student_id)

    if student_in.student_code:
        clean_code = student_in.student_code.strip().upper()
        if clean_code != student.student_code:
            existing = await get_student_by_code(db, clean_code)
            if existing and existing.id != student_id:
                raise ConflictError(f"Student code '{clean_code}' is already assigned.")
            student.student_code = clean_code

    if student_in.full_name is not None:
        student.full_name = student_in.full_name.strip()
    if student_in.class_name is not None:
        student.class_name = student_in.class_name.strip()
    if student_in.age is not None:
        student.age = student_in.age
    if student_in.photo_url is not None:
        student.photo_url = student_in.photo_url.strip() if student_in.photo_url else None
    if student_in.is_active is not None:
        student.is_active = student_in.is_active

    # Manage device pairing
    if student_in.device_id is not None:
        # Clear currently assigned device if changed
        if student.device and student.device.id != student_in.device_id:
            student.device.student_id = None

        if student_in.device_id:  # assigning a new one
            new_dev_stmt = select(Device).where(Device.id == student_in.device_id)
            new_dev_res = await db.execute(new_dev_stmt)
            new_device = new_dev_res.scalar_one_or_none()
            if not new_device:
                raise NotFoundError("Device", student_in.device_id)
            if new_device.student_id and new_device.student_id != student_id:
                raise ConflictError(f"Device '{new_device.device_code}' is assigned to another student.")
            new_device.student_id = student_id

    # Manage allowed zones mapping
    if student_in.allowed_zone_ids is not None:
        z_stmt = select(Zone).where(Zone.id.in_(student_in.allowed_zone_ids))
        z_res = await db.execute(z_stmt)
        student.allowed_zones = list(z_res.scalars().all())

    await db.commit()
    logger.info("Updated student: id=%s code=%s", student.id, student.student_code)
    return await get_student_by_id(db, student.id)


async def deactivate_student(db: AsyncSession, student_id: uuid.UUID) -> Student:
    """Soft-delete student and release assigned wearable."""
    student = await get_student_by_id(db, student_id)
    student.is_active = False
    if student.device:
        student.device.student_id = None
    await db.commit()
    return await get_student_by_id(db, student.id)


async def list_classes(db: AsyncSession) -> Sequence[str]:
    """Retrieve distinct class/grade names for active students."""
    stmt = (
        select(Student.class_name)
        .where(Student.is_active == True)  # noqa: E712
        .distinct()
        .order_by(Student.class_name.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
