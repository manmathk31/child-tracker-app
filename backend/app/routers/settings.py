"""Settings router providing REST API endpoints and Jinja2 web views for system configuration."""

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_db, get_optional_current_user, require_admin
from app.models.user import User, UserRole
from app.schemas.settings import (
    AlertSettingsResponse,
    AlertSettingsUpdate,
    SchoolSettingsResponse,
    SchoolSettingsUpdate,
)
from app.services import settings_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Settings"])


# ==============================================================================
# Web Views (Jinja2)
# ==============================================================================

@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render system settings administration panel (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/dashboard", status_code=302)

    school = await settings_service.get_or_create_school_settings(db)
    alerts = await settings_service.get_or_create_alert_settings(db)
    settings = get_settings()

    context = {
        "request": request,
        "page_title": "System Settings",
        "active_page": "settings",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "school": school,
        "alerts": alerts,
    }
    return templates.TemplateResponse(request=request, name="settings/index.html", context=context)


@router.post("/settings/school", response_class=HTMLResponse, include_in_schema=False)
async def update_school_settings_form(
    school_name: str = Form(...),
    building_name: str = Form(...),
    timezone: str = Form(...),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle school settings form submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    settings_in = SchoolSettingsUpdate(
        school_name=school_name,
        building_name=building_name,
        timezone=timezone,
    )
    await settings_service.update_school_settings(db, settings_in)
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/alerts", response_class=HTMLResponse, include_in_schema=False)
async def update_alert_settings_form(
    offline_threshold_minutes: int = Form(...),
    critical_offline_threshold_minutes: int = Form(...),
    low_battery_percent: int = Form(...),
    min_localization_confidence: float = Form(...),
    restricted_zone_alerts_enabled: Optional[str] = Form(None),
    sos_alerts_enabled: Optional[str] = Form(None),
    fall_detection_enabled: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle safety alert thresholds form submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    settings_in = AlertSettingsUpdate(
        offline_threshold_minutes=offline_threshold_minutes,
        critical_offline_threshold_minutes=critical_offline_threshold_minutes,
        low_battery_percent=low_battery_percent,
        min_localization_confidence=min_localization_confidence,
        restricted_zone_alerts_enabled=bool(restricted_zone_alerts_enabled),
        sos_alerts_enabled=bool(sos_alerts_enabled),
        fall_detection_enabled=bool(fall_detection_enabled),
    )
    await settings_service.update_alert_settings(db, settings_in)
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


# ==============================================================================
# REST API Endpoints (/api/v1/settings)
# ==============================================================================

@router.get("/api/v1/settings/school", response_model=SchoolSettingsResponse)
async def get_school_settings_api(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SchoolSettingsResponse:
    """Get organization and campus settings."""
    return await settings_service.get_or_create_school_settings(db)


@router.put("/api/v1/settings/school", response_model=SchoolSettingsResponse)
async def update_school_settings_api(
    settings_in: SchoolSettingsUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SchoolSettingsResponse:
    """Update organization settings (Admin only)."""
    return await settings_service.update_school_settings(db, settings_in)


@router.get("/api/v1/settings/alerts", response_model=AlertSettingsResponse)
async def get_alert_settings_api(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertSettingsResponse:
    """Get safety alert and monitoring thresholds."""
    return await settings_service.get_or_create_alert_settings(db)


@router.put("/api/v1/settings/alerts", response_model=AlertSettingsResponse)
async def update_alert_settings_api(
    settings_in: AlertSettingsUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AlertSettingsResponse:
    """Update safety alert and monitoring thresholds (Admin only)."""
    return await settings_service.update_alert_settings(db, settings_in)
