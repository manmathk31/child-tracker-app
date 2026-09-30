"""Business logic for school zone management."""

import logging
import uuid
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.zone import Zone
from app.schemas.zone import ZoneCreate, ZoneResponse, ZoneUpdate

logger = logging.getLogger("childtrack.zone_service")


async def list_zones(db: AsyncSession, include_inactive: bool = False) -> Sequence[Zone]:
    """Retrieve all school zones ordered by name.

    Args:
        db: Database session.
        include_inactive: Whether to include soft-deleted zones.

    Returns:
        List of Zone entities.
    """
    stmt = select(Zone).options(selectinload(Zone.scanner_devices))
    if not include_inactive:
        stmt = stmt.where(Zone.is_active == True)  # noqa: E712
    stmt = stmt.order_by(Zone.name)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_zone_by_id(db: AsyncSession, zone_id: uuid.UUID) -> Zone:
    """Retrieve a specific zone by UUID or raise NotFoundError.

    Args:
        db: Database session.
        zone_id: Zone UUID.

    Returns:
        Zone entity.

    Raises:
        NotFoundError: If zone does not exist.
    """
    stmt = select(Zone).options(selectinload(Zone.scanner_devices)).where(Zone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()
    if not zone:
        raise NotFoundError("Zone", zone_id)
    return zone


async def get_zone_by_name(db: AsyncSession, name: str) -> Optional[Zone]:
    """Find a zone by exact name (case-insensitive)."""
    stmt = select(Zone).where(func.lower(Zone.name) == name.strip().lower())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_zone(db: AsyncSession, zone_in: ZoneCreate) -> Zone:
    """Create and persist a new school zone.

    Args:
        db: Database session.
        zone_in: Validated zone creation data.

    Returns:
        Created Zone entity.

    Raises:
        ConflictError: If a zone with this name already exists.
    """
    existing = await get_zone_by_name(db, zone_in.name)
    if existing:
        raise ConflictError(f"A zone with name '{zone_in.name}' already exists.")

    zone = Zone(
        name=zone_in.name.strip(),
        description=zone_in.description.strip() if zone_in.description else None,
        building=zone_in.building.strip() if zone_in.building else None,
        floor=zone_in.floor.strip() if zone_in.floor else None,
        is_active=True,
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)

    logger.info("Created zone: id=%s name='%s'", zone.id, zone.name)
    return zone


async def update_zone(db: AsyncSession, zone_id: uuid.UUID, zone_in: ZoneUpdate) -> Zone:
    """Update an existing zone.

    Args:
        db: Database session.
        zone_id: Zone UUID.
        zone_in: Fields to update.

    Returns:
        Updated Zone entity.

    Raises:
        NotFoundError: If zone not found.
        ConflictError: If new name conflicts with an existing zone.
    """
    zone = await get_zone_by_id(db, zone_id)

    if zone_in.name and zone_in.name.strip().lower() != zone.name.lower():
        existing = await get_zone_by_name(db, zone_in.name)
        if existing and existing.id != zone_id:
            raise ConflictError(f"Another zone with name '{zone_in.name}' already exists.")
        zone.name = zone_in.name.strip()

    if zone_in.description is not None:
        zone.description = zone_in.description.strip() if zone_in.description else None
    if zone_in.building is not None:
        zone.building = zone_in.building.strip() if zone_in.building else None
    if zone_in.floor is not None:
        zone.floor = zone_in.floor.strip() if zone_in.floor else None
    if zone_in.is_active is not None:
        zone.is_active = zone_in.is_active

    await db.commit()
    await db.refresh(zone)
    logger.info("Updated zone: id=%s name='%s'", zone.id, zone.name)
    return zone


async def deactivate_zone(db: AsyncSession, zone_id: uuid.UUID) -> Zone:
    """Soft-delete a zone by setting is_active=False.

    Args:
        db: Database session.
        zone_id: Zone UUID.

    Returns:
        Deactivated Zone entity.
    """
    zone = await get_zone_by_id(db, zone_id)
    zone.is_active = False
    await db.commit()
    await db.refresh(zone)
    logger.info("Deactivated zone: id=%s name='%s'", zone.id, zone.name)
    return zone
