"""Business logic for ESP32 wearable hardware management."""

import logging
import uuid
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.device import Device, DeviceStatus
from app.schemas.device import DeviceCreate, DeviceUpdate

logger = logging.getLogger("childtrack.device_service")


async def list_devices(db: AsyncSession, include_inactive: bool = False) -> Sequence[Device]:
    """List all registered wearables."""
    stmt = select(Device).options(selectinload(Device.student))
    if not include_inactive:
        stmt = stmt.where(Device.is_active == True)  # noqa: E712
    stmt = stmt.order_by(Device.device_code)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_device_by_id(db: AsyncSession, device_id: uuid.UUID) -> Device:
    """Retrieve a device by UUID."""
    stmt = select(Device).options(selectinload(Device.student)).where(Device.id == device_id)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()
    if not device:
        raise NotFoundError("Device", device_id)
    return device


async def get_device_by_code(db: AsyncSession, device_code: str) -> Optional[Device]:
    """Retrieve a device by its engraved device code."""
    stmt = select(Device).where(func.upper(Device.device_code) == device_code.strip().upper())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_device_by_mac(db: AsyncSession, mac_address: str) -> Optional[Device]:
    """Retrieve a device by Wi-Fi MAC address."""
    clean_mac = mac_address.replace("-", ":").upper()
    stmt = select(Device).where(func.upper(Device.mac_address) == clean_mac)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_device(db: AsyncSession, device_in: DeviceCreate) -> Device:
    """Register a new ESP32 wearable tag."""
    clean_code = device_in.device_code.strip().upper()
    clean_mac = device_in.mac_address.replace("-", ":").upper()

    if await get_device_by_code(db, clean_code):
        raise ConflictError(f"Device code '{clean_code}' is already registered.")

    if await get_device_by_mac(db, clean_mac):
        raise ConflictError(f"MAC address '{clean_mac}' is already registered.")

    device = Device(
        device_code=clean_code,
        mac_address=clean_mac,
        battery_percent=device_in.battery_percent,
        firmware_version=device_in.firmware_version.strip() if device_in.firmware_version else None,
        status=DeviceStatus.OFFLINE,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    logger.info("Registered wearable: id=%s code=%s mac=%s", device.id, device.device_code, device.mac_address)
    return await get_device_by_id(db, device.id)


async def update_device(db: AsyncSession, device_id: uuid.UUID, device_in: DeviceUpdate) -> Device:
    """Update device metadata or assign to student."""
    device = await get_device_by_id(db, device_id)

    if device_in.device_code:
        clean_code = device_in.device_code.strip().upper()
        if clean_code != device.device_code:
            existing = await get_device_by_code(db, clean_code)
            if existing and existing.id != device_id:
                raise ConflictError(f"Device code '{clean_code}' is already assigned.")
            device.device_code = clean_code

    if device_in.mac_address:
        clean_mac = device_in.mac_address.replace("-", ":").upper()
        if clean_mac != device.mac_address:
            existing = await get_device_by_mac(db, clean_mac)
            if existing and existing.id != device_id:
                raise ConflictError(f"MAC address '{clean_mac}' is already registered.")
            device.mac_address = clean_mac

    if device_in.battery_percent is not None:
        device.battery_percent = device_in.battery_percent
    if device_in.firmware_version is not None:
        device.firmware_version = device_in.firmware_version.strip() if device_in.firmware_version else None
    if device_in.student_id is not None:
        device.student_id = device_in.student_id
    if device_in.is_active is not None:
        device.is_active = device_in.is_active

    await db.commit()
    await db.refresh(device)
    return await get_device_by_id(db, device.id)


async def deactivate_device(db: AsyncSession, device_id: uuid.UUID) -> Device:
    """Soft-delete a wearable."""
    device = await get_device_by_id(db, device_id)
    device.is_active = False
    device.student_id = None
    await db.commit()
    await db.refresh(device)
    return device


async def list_available_for_student(
    db: AsyncSession, current_student_id: Optional[uuid.UUID] = None
) -> Sequence[Device]:
    """List active devices that are unassigned or assigned to current_student_id."""
    stmt = select(Device).where(Device.is_active == True)  # noqa: E712
    if current_student_id:
        stmt = stmt.where((Device.student_id == None) | (Device.student_id == current_student_id))  # noqa: E711
    else:
        stmt = stmt.where(Device.student_id == None)  # noqa: E711
    stmt = stmt.order_by(Device.device_code)
    result = await db.execute(stmt)
    return result.scalars().all()

