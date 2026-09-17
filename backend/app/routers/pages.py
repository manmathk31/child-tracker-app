"""Web page routes delivering server-rendered Jinja2 templates."""

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_db, get_optional_current_user
from app.models.alert import AlertSeverity, AlertStatus, AlertType
from app.models.user import User
from app.services import alert_service, dashboard_service, student_service

# Configure Jinja2 templates directory
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=RedirectResponse)
async def root_redirect(
    current_user: User | None = Depends(get_optional_current_user),
) -> RedirectResponse:
    """Redirect root access to dashboard if logged in, or login page if not."""
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    class_name: str | None = None,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render the primary ChildTrack live safety dashboard with real data counts.

    Redirects unauthenticated visitors to the login page.
    """
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    settings = get_settings()
    live_data = await dashboard_service.get_dashboard_live_payload(db, class_name=class_name)
    all_classes = await student_service.list_classes(db)

    context: dict[str, Any] = {
        "request": request,
        "page_title": "Live Safety Dashboard",
        "active_page": "dashboard",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "metrics": live_data.metrics,
        "total_students": live_data.metrics.total_students,
        "trackable_students": live_data.metrics.trackable_students,
        "attention_students": live_data.metrics.attention_students,
        "active_alerts_count": live_data.metrics.active_alerts_count,
        "zones": live_data.zones,
        "roaming_zone": live_data.roaming_zone,
        "students": live_data.students,
        "active_alerts": live_data.active_alerts,
        "selected_class": class_name,
        "all_classes": all_classes,
    }
    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context=context,
    )


@router.get("/alerts", response_class=HTMLResponse)
async def alerts_page(
    request: Request,
    status_filter: str = Query("active", alias="status"),
    severity: str | None = None,
    alert_type: str | None = Query(None, alias="type"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render the safety alerts management log with filter tabs and resolution actions."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    settings = get_settings()

    # Parse filters
    status_enum: AlertStatus | None = None
    if status_filter and status_filter.lower() != "all":
        try:
            status_enum = AlertStatus(status_filter.lower())
        except ValueError:
            status_enum = AlertStatus.ACTIVE
            status_filter = "active"

    severity_enum: AlertSeverity | None = None
    if severity:
        try:
            severity_enum = AlertSeverity(severity.lower())
        except ValueError:
            severity_enum = None

    type_enum: AlertType | None = None
    if alert_type:
        try:
            type_enum = AlertType(alert_type.lower())
        except ValueError:
            type_enum = None

    # Retrieve filtered alerts
    alerts = await alert_service.list_alerts(
        db,
        status=status_enum,
        severity=severity_enum,
        alert_type=type_enum,
        limit=100,
    )

    # Compute tab counts
    active_count = await alert_service.get_active_alerts_count(db)

    context: dict[str, Any] = {
        "request": request,
        "page_title": "Safety Alerts & Incidents",
        "active_page": "alerts",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "alerts": alerts,
        "active_tab": status_filter.lower(),
        "selected_severity": severity or "",
        "selected_type": alert_type or "",
        "active_count": active_count,
        "alert_types": [t.value for t in AlertType],
        "alert_severities": [s.value for s in AlertSeverity],
    }
    return templates.TemplateResponse(
        request=request,
        name="alerts/index.html",
        context=context,
    )


@router.post("/alerts/{alert_id}/acknowledge", response_class=RedirectResponse)
async def web_acknowledge_alert(
    alert_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle web UI form action to acknowledge an alert."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    await alert_service.acknowledge_alert(db, alert_id, current_user.id)
    return RedirectResponse(url="/alerts", status_code=303)


@router.post("/alerts/{alert_id}/resolve", response_class=RedirectResponse)
async def web_resolve_alert(
    alert_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle web UI form action to resolve an alert."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    await alert_service.resolve_alert(db, alert_id, current_user.id)
    return RedirectResponse(url="/alerts", status_code=303)
