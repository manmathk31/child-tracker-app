"""Tracking router providing hardware telemetry ingestion and live positioning estimates."""

import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_db, get_optional_current_user
from app.models.user import User
from app.schemas.location import (
    LocationRecordResponse,
    StudentLiveLocationResponse,
    MasterTelemetryIngest,
    TelemetryIngestResponse,
)
from app.services import proximity_service, student_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Tracking & Localization"])


# ==============================================================================
# Web Views (Jinja2)
# ==============================================================================

@router.get("/students/{student_id}/history", response_class=HTMLResponse, include_in_schema=False)
async def student_history_page(
    request: Request,
    student_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render the student location history timeline page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    student = await student_service.get_student_by_id(db, student_id)
    history = await proximity_service.get_student_location_history(db, student_id, limit=limit)
    live_info = await proximity_service.get_student_live_location(db, student_id)
    settings = get_settings()

    context = {
        "request": request,
        "page_title": f"Location History: {student.full_name}",
        "active_page": "students",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "student": student,
        "history": history,
        "live_info": live_info,
    }
    return templates.TemplateResponse(
        request=request,
        name="students/history.html",
        context=context,
    )


@router.post("/students/{student_id}/history/clear", response_class=HTMLResponse, include_in_schema=False)
async def clear_student_history(
    student_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Clear the location history for a specific student."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    from sqlalchemy import delete
    from app.models.location_record import LocationRecord
    await db.execute(delete(LocationRecord).where(LocationRecord.student_id == student_id))
    await db.commit()
    
    return RedirectResponse(url=f"/students/{student_id}/history", status_code=303)


# ==============================================================================
# Operational Hardware Telemetry Ingest (ESP32 Protocol)
# ==============================================================================

@router.post(
    "/api/v1/tracking/ingest",
    response_model=TelemetryIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="ESP32 hardware telemetry ingestion endpoint",
)
async def ingest_telemetry(
    payload: MasterTelemetryIngest,
    db: AsyncSession = Depends(get_db),
) -> TelemetryIngestResponse:
    """Receive Bluetooth/Wi-Fi RSSI scan burst from a Master ESP hardware scanner.

    Processes proximity for all detected wearable tags and records location audit entries.
    """
    return await proximity_service.process_telemetry_scan(db, payload)


# ==============================================================================
# REST API Endpoints (/api/v1/students/{id}/location & history)
# ==============================================================================

@router.get(
    "/api/v1/students/{student_id}/location",
    response_model=StudentLiveLocationResponse,
    summary="Get student live positioning estimate and recent breadcrumbs",
)
async def get_student_live_location_api(
    student_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudentLiveLocationResponse:
    """Retrieve current estimated room location, confidence score, and recent breadcrumbs."""
    return await proximity_service.get_student_live_location(db, student_id)


@router.get(
    "/api/v1/students/{student_id}/history",
    response_model=list[LocationRecordResponse],
    summary="Get chronological location audit records for a student",
)
async def get_student_history_api(
    student_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Sequence[LocationRecordResponse]:
    """Retrieve historical location breadcrumb records for a student."""
    records = await proximity_service.get_student_location_history(db, student_id, limit=limit)
    return [LocationRecordResponse.model_validate(r) for r in records]
