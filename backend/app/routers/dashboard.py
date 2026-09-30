"""Dashboard router providing real-time data feeds and occupancy metrics."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.dashboard import DashboardLiveResponse
from app.services import dashboard_service

router = APIRouter(tags=["Live Dashboard"])


@router.get(
    "/api/v1/dashboard/live",
    response_model=DashboardLiveResponse,
    summary="Get aggregated live safety monitoring metrics and room occupancy",
)
async def get_dashboard_live_api(
    class_name: str | None = Query(None, description="Optional class filter (e.g. Grade 3A)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardLiveResponse:
    """Return consolidated live safety metrics, room occupancy grid, and student status cards."""
    return await dashboard_service.get_dashboard_live_payload(db, class_name=class_name)
