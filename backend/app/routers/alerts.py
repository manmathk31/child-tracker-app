"""Alerts router providing endpoints for notification counts, active safety alerts, and triage."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_optional_current_user
from app.models.user import User
from app.schemas.alert import AlertCountResponse, AlertResponse
from app.services import alert_service

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
    summary="List active safety alerts",
)
async def list_active_alerts_api(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertResponse]:
    """Retrieve list of unacknowledged safety alerts for live feed and incident management."""
    alerts = await alert_service.list_active_alerts(db, limit=limit)
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
