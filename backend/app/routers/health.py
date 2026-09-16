"""Health check endpoint reporting application and database connectivity status."""

from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.database.session import check_db_connection
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application Health Check",
    description="Reports the operational status of the service and database connectivity.",
)
async def health_check(response: Response) -> HealthResponse:
    """Check connectivity to database and return application health status.

    Returns:
        HealthResponse: Detailed status of application and its backing services.
    """
    settings = get_settings()
    is_db_connected = await check_db_connection()

    if not is_db_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "degraded"
        db_status = "disconnected"
    else:
        overall_status = "healthy"
        db_status = "connected"

    return HealthResponse(
        status=overall_status,
        database=db_status,
        version=settings.APP_VERSION,
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
    )
