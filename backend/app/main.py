"""ChildTrack FastAPI Application Factory and Entrypoint."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import request_id_ctx, setup_logging
from app.database.session import close_db_engine, get_engine
from app.routers import (
    alerts,
    auth,
    dashboard,
    devices,
    health,
    pages,
    students,
    testing_portal,
    tracking,
    zones,
)
from app.routers import (
    settings as settings_router,
)
from app.services import alert_scheduler, mqtt_service

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycles."""
    settings = get_settings()
    logger = setup_logging(log_level=settings.LOG_LEVEL, json_format=settings.LOG_JSON_FORMAT)
    logger.info(
        "Starting %s v%s in %s mode",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )

    # Initialize database engine
    get_engine()

    # Start background alert monitor
    alert_scheduler.start_alert_scheduler(interval_seconds=30)

    # Start background cloud MQTT subscriber (HiveMQ Cloud)
    if settings.MQTT_ENABLED:
        mqtt_service.start_mqtt_service(loop=asyncio.get_running_loop())

    yield

    # Shutdown: stop background services and gracefully close database connections
    mqtt_service.stop_mqtt_service()
    alert_scheduler.stop_alert_scheduler()
    logger.info("Shutting down %s...", settings.APP_NAME)
    await close_db_engine()


def create_application() -> FastAPI:
    """Create and configure the ChildTrack FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Indoor child-safety tracking and monitoring platform for schools",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # 1. Request ID & Correlation Tracking Middleware
    @app.middleware("http")
    async def request_correlation_middleware(request: Request, call_next) -> Response:
        # Extract existing X-Request-ID or generate a new UUIDv4
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)

    # 2. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Global Exception Handlers
    register_exception_handlers(app)

    # 4. Mount Static Assets
    static_path = BASE_DIR / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # 5. Register Routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(zones.router)
    app.include_router(devices.router)
    app.include_router(students.router)
    app.include_router(settings_router.router)
    app.include_router(tracking.router)
    app.include_router(alerts.router)
    app.include_router(dashboard.router)
    app.include_router(testing_portal.router)

    # 6. Favicon handler to avoid 404 noise
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    return app


app = create_application()
