"""Business logic for school metadata and safety alert threshold settings."""

import logging
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.settings import AlertSettings, SchoolSettings
from app.schemas.settings import AlertSettingsUpdate, SchoolSettingsUpdate

logger = logging.getLogger("childtrack.settings_service")


async def get_or_create_school_settings(db: AsyncSession) -> SchoolSettings:
    """Retrieve the singleton school settings record or initialize with default values."""
    stmt = select(SchoolSettings).limit(1)
    result = await db.execute(stmt)
    settings_obj = result.scalar_one_or_none()
    if not settings_obj:
        app_settings = get_settings()
        settings_obj = SchoolSettings(
            school_name="ChildTrack Academy",
            building_name="Main Campus",
            timezone=app_settings.DEFAULT_TIMEZONE,
        )
        db.add(settings_obj)
        await db.commit()
        await db.refresh(settings_obj)
        logger.info("Initialized default SchoolSettings record.")
    return settings_obj


async def update_school_settings(db: AsyncSession, settings_in: SchoolSettingsUpdate) -> SchoolSettings:
    """Update organization-level settings."""
    settings_obj = await get_or_create_school_settings(db)

    if settings_in.school_name is not None:
        settings_obj.school_name = settings_in.school_name.strip()
    if settings_in.building_name is not None:
        settings_obj.building_name = settings_in.building_name.strip()
    if settings_in.timezone is not None:
        settings_obj.timezone = settings_in.timezone.strip()

    await db.commit()
    await db.refresh(settings_obj)
    logger.info("Updated SchoolSettings: school='%s'", settings_obj.school_name)
    return settings_obj


async def get_or_create_alert_settings(db: AsyncSession) -> AlertSettings:
    """Retrieve the singleton alert thresholds record or initialize with default values."""
    stmt = select(AlertSettings).limit(1)
    result = await db.execute(stmt)
    settings_obj = result.scalar_one_or_none()
    if not settings_obj:
        app_settings = get_settings()
        settings_obj = AlertSettings(
            offline_threshold_minutes=app_settings.DEFAULT_OFFLINE_THRESHOLD_MINUTES,
            critical_offline_threshold_minutes=app_settings.DEFAULT_CRITICAL_OFFLINE_THRESHOLD_MINUTES,
            low_battery_percent=app_settings.DEFAULT_LOW_BATTERY_PERCENT,
            min_localization_confidence=app_settings.DEFAULT_MIN_LOCALIZATION_CONFIDENCE,
            restricted_zone_alerts_enabled=True,
            fall_detection_enabled=True,
            sos_alerts_enabled=True,
        )
        db.add(settings_obj)
        await db.commit()
        await db.refresh(settings_obj)
        logger.info("Initialized default AlertSettings record.")
    return settings_obj


async def update_alert_settings(db: AsyncSession, settings_in: AlertSettingsUpdate) -> AlertSettings:
    """Update configurable safety alert thresholds."""
    settings_obj = await get_or_create_alert_settings(db)

    if settings_in.offline_threshold_minutes is not None:
        settings_obj.offline_threshold_minutes = settings_in.offline_threshold_minutes
    if settings_in.critical_offline_threshold_minutes is not None:
        settings_obj.critical_offline_threshold_minutes = settings_in.critical_offline_threshold_minutes
    if settings_in.low_battery_percent is not None:
        settings_obj.low_battery_percent = settings_in.low_battery_percent
    if settings_in.min_localization_confidence is not None:
        settings_obj.min_localization_confidence = settings_in.min_localization_confidence
    if settings_in.restricted_zone_alerts_enabled is not None:
        settings_obj.restricted_zone_alerts_enabled = settings_in.restricted_zone_alerts_enabled
    if settings_in.fall_detection_enabled is not None:
        settings_obj.fall_detection_enabled = settings_in.fall_detection_enabled
    if settings_in.sos_alerts_enabled is not None:
        settings_obj.sos_alerts_enabled = settings_in.sos_alerts_enabled

    await db.commit()
    await db.refresh(settings_obj)
    logger.info("Updated AlertSettings: offline=%sm", settings_obj.offline_threshold_minutes)
    return settings_obj
