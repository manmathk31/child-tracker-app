"""Business logic for safety alerts, notifications, and triage workflow."""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.alert import Alert, AlertStatus

logger = logging.getLogger("childtrack.alert_service")


async def get_active_alerts_count(db: AsyncSession) -> int:
    """Return the total count of currently active unacknowledged alerts."""
    stmt = select(func.count(Alert.id)).where(Alert.status == AlertStatus.ACTIVE)
    count = await db.scalar(stmt)
    return count or 0


async def list_active_alerts(db: AsyncSession, limit: int = 20) -> Sequence[Alert]:
    """Retrieve recent active safety alerts for feeds and dashboards."""
    stmt = (
        select(Alert)
        .where(Alert.status == AlertStatus.ACTIVE)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .options(
            selectinload(Alert.student),
            selectinload(Alert.device),
            selectinload(Alert.zone),
            selectinload(Alert.acknowledger),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_alert_by_id(db: AsyncSession, alert_id: uuid.UUID) -> Alert:
    """Retrieve a single alert record by UUID."""
    stmt = (
        select(Alert)
        .where(Alert.id == alert_id)
        .options(
            selectinload(Alert.student),
            selectinload(Alert.device),
            selectinload(Alert.zone),
            selectinload(Alert.acknowledger),
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError("Alert", alert_id)
    return alert


async def acknowledge_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Alert:
    """Acknowledge an active alert and record the user timestamp."""
    alert = await get_alert_by_id(db, alert_id)
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = user_id
    alert.acknowledged_at = datetime.now(UTC)
    await db.commit()
    logger.info("Alert %s acknowledged by user %s", alert_id, user_id)
    return alert
