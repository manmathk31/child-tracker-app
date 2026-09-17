"""Alerts router providing endpoints for notification counts, active safety alerts, and triage."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_optional_current_user, require_admin
from app.models.alert import AlertSeverity, AlertStatus, AlertType
from app.models.user import User
from app.schemas.alert import AlertCountResponse, AlertResponse
from app.services import alert_scheduler, alert_service

router = APIRouter(tags=["Safety Alerts"])


@router.get(
    "/api/v1/alerts/count",
    response_model=AlertCountResponse,
    summary="Get count of active unacknowledged alerts",
)
async def get_alerts_count(
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertCountResponse:
    """Return active alert count for top navigation bar bell notification badge."""
    count = await alert_service.get_active_alerts_count(db)
    return AlertCountResponse(count=count)


@router.get(
    "/api/v1/alerts",
    response_model=list[AlertResponse],
    summary="List safety alerts",
)
async def list_alerts_api(
    alert_status: AlertStatus | None = Query(None, alias="status"),
    severity: AlertSeverity | None = Query(None),
    alert_type: AlertType | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertResponse]:
    """Retrieve safety alerts with optional filtering by status, severity, and type."""
    # If status parameter is omitted, default to ACTIVE for backwards compatibility
    status_filter = alert_status if alert_status is not None else AlertStatus.ACTIVE
    alerts = await alert_service.list_alerts(
        db,
        status=status_filter,
        severity=severity,
        alert_type=alert_type,
        limit=limit,
        offset=offset,
    )
    return [AlertResponse.model_validate(a) for a in alerts]


@router.post(
    "/api/v1/alerts/{alert_id}/acknowledge",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Acknowledge an active safety alert",
)
async def acknowledge_alert_api(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Mark an alert as acknowledged by the current authenticated operator."""
    alert = await alert_service.acknowledge_alert(db, alert_id, current_user.id)
    return AlertResponse.model_validate(alert)


@router.post(
    "/api/v1/alerts/{alert_id}/resolve",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve a safety alert",
)
async def resolve_alert_api(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Mark an alert as resolved and clear it from active triage."""
    alert = await alert_service.resolve_alert(db, alert_id, current_user.id)
    return AlertResponse.model_validate(alert)


@router.post(
    "/api/v1/alerts/sweep",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Trigger immediate automated safety sweep",
)
async def trigger_manual_sweep(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Admin-only endpoint to execute an immediate safety sweep on-demand."""
    return await alert_scheduler.trigger_immediate_sweep()
