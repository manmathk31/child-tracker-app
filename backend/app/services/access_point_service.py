"""Business logic for Wi-Fi Access Point registration and management."""

import logging
import uuid
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.access_point import AccessPoint
from app.models.zone import Zone
from app.schemas.access_point import AccessPointCreate, AccessPointUpdate

logger = logging.getLogger("childtrack.ap_service")


async def list_access_points(
    db: AsyncSession,
    zone_id: Optional[uuid.UUID] = None,
    include_inactive: bool = False,
) -> Sequence[AccessPoint]:
    """Retrieve access points, optionally filtered by zone.

    Args:
        db: Database session.
        zone_id: Optional zone filter.
        include_inactive: Whether to include deactivated APs.

    Returns:
        List of AccessPoint entities.
    """
    stmt = select(AccessPoint).options(selectinload(AccessPoint.zone))
    if not include_inactive:
        stmt = stmt.where(AccessPoint.is_active == True)  # noqa: E712
    if zone_id:
        stmt = stmt.where(AccessPoint.zone_id == zone_id)
    stmt = stmt.order_by(AccessPoint.name)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_access_point_by_id(db: AsyncSession, ap_id: uuid.UUID) -> AccessPoint:
    """Retrieve an access point by UUID.

    Raises:
        NotFoundError: If AP not found.
    """
    stmt = select(AccessPoint).options(selectinload(AccessPoint.zone)).where(AccessPoint.id == ap_id)
    result = await db.execute(stmt)
    ap = result.scalar_one_or_none()
    if not ap:
        raise NotFoundError("AccessPoint", ap_id)
    return ap


async def get_access_point_by_bssid(db: AsyncSession, bssid: str) -> Optional[AccessPoint]:
    """Find an access point by normalized BSSID."""
    clean_bssid = bssid.replace("-", ":").upper()
    stmt = select(AccessPoint).where(func.upper(AccessPoint.bssid) == clean_bssid)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_access_point(db: AsyncSession, ap_in: AccessPointCreate) -> AccessPoint:
    """Register a new Wi-Fi Access Point.

    Raises:
        ConflictError: If BSSID is already registered.
        NotFoundError: If specified zone does not exist.
    """
    clean_bssid = ap_in.bssid.replace("-", ":").upper()
    existing = await get_access_point_by_bssid(db, clean_bssid)
    if existing:
        raise ConflictError(f"Access Point with BSSID '{clean_bssid}' is already registered.")

    if ap_in.zone_id:
        zone_stmt = select(Zone).where(Zone.id == ap_in.zone_id)
        zone_res = await db.execute(zone_stmt)
        if not zone_res.scalar_one_or_none():
            raise NotFoundError("Zone", ap_in.zone_id)

    ap = AccessPoint(
        name=ap_in.name.strip(),
        bssid=clean_bssid,
        channel=ap_in.channel,
        zone_id=ap_in.zone_id,
        is_active=True,
    )
    db.add(ap)
    await db.commit()
    await db.refresh(ap)

    # Re-fetch with relationship
    return await get_access_point_by_id(db, ap.id)


async def update_access_point(
    db: AsyncSession,
    ap_id: uuid.UUID,
    ap_in: AccessPointUpdate,
) -> AccessPoint:
    """Update an existing Access Point."""
    ap = await get_access_point_by_id(db, ap_id)

    if ap_in.bssid:
        clean_bssid = ap_in.bssid.replace("-", ":").upper()
        if clean_bssid != ap.bssid:
            existing = await get_access_point_by_bssid(db, clean_bssid)
            if existing and existing.id != ap_id:
                raise ConflictError(f"BSSID '{clean_bssid}' is registered to another AP.")
            ap.bssid = clean_bssid

    if ap_in.name is not None:
        ap.name = ap_in.name.strip()
    if ap_in.channel is not None:
        ap.channel = ap_in.channel
    if ap_in.zone_id is not None:
        if ap_in.zone_id:
            zone_stmt = select(Zone).where(Zone.id == ap_in.zone_id)
            zone_res = await db.execute(zone_stmt)
            if not zone_res.scalar_one_or_none():
                raise NotFoundError("Zone", ap_in.zone_id)
        ap.zone_id = ap_in.zone_id
    if ap_in.is_active is not None:
        ap.is_active = ap_in.is_active

    await db.commit()
    await db.refresh(ap)
    return await get_access_point_by_id(db, ap.id)


async def delete_access_point(db: AsyncSession, ap_id: uuid.UUID) -> AccessPoint:
    """Soft-delete an access point."""
    ap = await get_access_point_by_id(db, ap_id)
    ap.is_active = False
    await db.commit()
    await db.refresh(ap)
    return ap


# Alias for naming consistency across services
deactivate_access_point = delete_access_point

