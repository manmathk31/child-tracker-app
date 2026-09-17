"""Fingerprint router providing REST API endpoints and Jinja2 web views for calibration surveys."""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_db, get_optional_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.models.fingerprint import Fingerprint, FingerprintStatus
from app.models.user import User, UserRole
from app.schemas.fingerprint import (
    CalibrationBatchIn,
    FingerprintAPStatResponse,
    FingerprintCreate,
    FingerprintDetailResponse,
    FingerprintResponse,
    FingerprintUpdate,
)
from app.services import access_point_service, fingerprint_service, zone_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Fingerprints"])


# ==============================================================================
# Web Views (Jinja2)
# ==============================================================================

@router.get("/fingerprints", response_class=HTMLResponse, include_in_schema=False)
async def fingerprints_list_page(
    request: Request,
    zone_id: Optional[uuid.UUID] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render list of radio fingerprint surveys."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    fingerprints = await fingerprint_service.list_fingerprints(db, zone_id=zone_id)
    settings = get_settings()

    context = {
        "request": request,
        "page_title": "Fingerprint Surveys",
        "active_page": "fingerprints",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "fingerprints": fingerprints,
    }
    return templates.TemplateResponse(request=request, name="fingerprints/list.html", context=context)


@router.get("/fingerprints/new", response_class=HTMLResponse, include_in_schema=False)
async def new_fingerprint_page(
    request: Request,
    zone_id: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render survey setup form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/fingerprints", status_code=302)

    all_zones = await zone_service.list_zones(db)
    all_aps = await access_point_service.list_access_points(db)
    settings = get_settings()

    context = {
        "request": request,
        "page_title": "New Calibration Survey",
        "active_page": "fingerprints",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "all_zones": all_zones,
        "all_aps": all_aps,
        "selected_zone_id": zone_id,
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="fingerprints/form.html", context=context)


@router.post("/fingerprints/new", response_class=HTMLResponse, include_in_schema=False)
async def new_fingerprint_submit(
    request: Request,
    zone_id: str = Form(...),
    min_rssi_cutoff: int = Form(-85),
    notes: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new calibration survey session."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    raw_ap_ids = form.getlist("target_ap_ids")
    parsed_ap_ids: List[uuid.UUID] = []
    for ap_str in raw_ap_ids:
        if ap_str and str(ap_str).strip():
            try:
                parsed_ap_ids.append(uuid.UUID(str(ap_str).strip()))
            except ValueError:
                pass

    try:
        parsed_zone_id = uuid.UUID(zone_id.strip())
        fp_in = FingerprintCreate(
            zone_id=parsed_zone_id,
            min_rssi_cutoff=min_rssi_cutoff,
            target_ap_ids=parsed_ap_ids if parsed_ap_ids else None,
            notes=notes,
        )
        fp = await fingerprint_service.create_fingerprint(db, current_user.id, fp_in)
        return RedirectResponse(url=f"/fingerprints/{fp.id}/calibrate", status_code=status.HTTP_303_SEE_OTHER)
    except (NotFoundError, ConflictError, ValueError) as exc:
        all_zones = await zone_service.list_zones(db)
        all_aps = await access_point_service.list_access_points(db)
        settings = get_settings()
        err = exc.message if hasattr(exc, "message") else str(exc)
        context = {
            "request": request,
            "page_title": "New Calibration Survey",
            "active_page": "fingerprints",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "all_zones": all_zones,
            "all_aps": all_aps,
            "selected_zone_id": zone_id,
            "error_message": err,
        }
        return templates.TemplateResponse(
            request=request, name="fingerprints/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


@router.get("/fingerprints/{fingerprint_id}/calibrate", response_class=HTMLResponse, include_in_schema=False)
async def calibrate_fingerprint_page(
    fingerprint_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render interactive calibration screen."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url=f"/fingerprints/{fingerprint_id}", status_code=302)

    try:
        fingerprint = await fingerprint_service.get_fingerprint_by_id(db, fingerprint_id)
    except NotFoundError:
        return RedirectResponse(url="/fingerprints", status_code=302)

    whitelisted_ids = fingerprint_service.parse_whitelisted_ap_ids(fingerprint.notes)
    all_aps = await access_point_service.list_access_points(db)

    if whitelisted_ids:
        whitelisted_aps = [ap for ap in all_aps if ap.id in whitelisted_ids]
    else:
        whitelisted_aps = list(all_aps)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": f"Calibrate: {fingerprint.zone.name}",
        "active_page": "fingerprints",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "fingerprint": fingerprint,
        "whitelisted_aps": whitelisted_aps,
    }
    return templates.TemplateResponse(request=request, name="fingerprints/calibrate.html", context=context)


@router.post("/fingerprints/{fingerprint_id}/activate", response_class=HTMLResponse, include_in_schema=False)
async def activate_fingerprint_form(
    fingerprint_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Calculate statistics and activate fingerprint survey."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    await fingerprint_service.activate_fingerprint(db, fingerprint_id)
    return RedirectResponse(url=f"/fingerprints/{fingerprint_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/fingerprints/{fingerprint_id}", response_class=HTMLResponse, include_in_schema=False)
async def fingerprint_detail_page(
    fingerprint_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render survey statistics report."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    try:
        fingerprint = await fingerprint_service.get_fingerprint_by_id(db, fingerprint_id)
    except NotFoundError:
        return RedirectResponse(url="/fingerprints", status_code=302)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": f"Survey: {fingerprint.zone.name}",
        "active_page": "fingerprints",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "fingerprint": fingerprint,
    }
    return templates.TemplateResponse(request=request, name="fingerprints/detail.html", context=context)


# ==============================================================================
# REST API Endpoints (/api/v1/fingerprints)
# ==============================================================================

@router.get("/api/v1/fingerprints", response_model=List[FingerprintResponse])
async def api_list_fingerprints(
    zone_id: Optional[uuid.UUID] = None,
    status: Optional[FingerprintStatus] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Sequence[Fingerprint]:
    """List all calibration surveys with zone and surveyor metadata."""
    return await fingerprint_service.list_fingerprints(db, zone_id=zone_id, status=status)


@router.post(
    "/api/v1/fingerprints",
    response_model=FingerprintResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_create_fingerprint(
    fingerprint_in: FingerprintCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FingerprintResponse:
    """Initialize a new fingerprint calibration survey (Admin only)."""
    fp = await fingerprint_service.create_fingerprint(db, current_user.id, fingerprint_in)
    return FingerprintResponse(
        id=fp.id,
        zone_id=fp.zone_id,
        zone_name=fp.zone.name if fp.zone else None,
        created_by=fp.created_by,
        creator_name=fp.creator.full_name if fp.creator else None,
        sample_count=fp.sample_count,
        quality_score=fp.quality_score,
        min_rssi_cutoff=fp.min_rssi_cutoff,
        status=fp.status,
        notes=fp.notes,
        created_at=fp.created_at,
        updated_at=fp.updated_at,
    )


@router.get("/api/v1/fingerprints/{fingerprint_id}", response_model=FingerprintDetailResponse)
async def api_get_fingerprint(
    fingerprint_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FingerprintDetailResponse:
    """Retrieve fingerprint report with statistical distribution per Access Point."""
    fp = await fingerprint_service.get_fingerprint_by_id(db, fingerprint_id)
    stats_out = [
        FingerprintAPStatResponse(
            id=s.id,
            access_point_id=s.access_point_id,
            access_point_name=s.access_point.name if s.access_point else None,
            access_point_bssid=s.access_point.bssid if s.access_point else None,
            median_rssi=s.median_rssi,
            mean_rssi=s.mean_rssi,
            stddev_rssi=s.stddev_rssi,
            sample_count=s.sample_count,
        )
        for s in fp.ap_stats
    ]
    return FingerprintDetailResponse(
        id=fp.id,
        zone_id=fp.zone_id,
        zone_name=fp.zone.name if fp.zone else None,
        created_by=fp.created_by,
        creator_name=fp.creator.full_name if fp.creator else None,
        sample_count=fp.sample_count,
        quality_score=fp.quality_score,
        min_rssi_cutoff=fp.min_rssi_cutoff,
        status=fp.status,
        notes=fp.notes,
        created_at=fp.created_at,
        updated_at=fp.updated_at,
        ap_stats=stats_out,
    )


@router.post("/api/v1/fingerprints/{fingerprint_id}/samples")
async def api_ingest_samples(
    fingerprint_id: uuid.UUID,
    batch: CalibrationBatchIn,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Ingest a batch of Wi-Fi scans from an ESP32 calibration tool or automated sweep."""
    accepted = await fingerprint_service.ingest_samples_batch(db, fingerprint_id, batch)
    return {
        "status": "success",
        "fingerprint_id": str(fingerprint_id),
        "accepted_readings": accepted,
    }


@router.post("/api/v1/fingerprints/{fingerprint_id}/activate", response_model=FingerprintDetailResponse)
async def api_activate_fingerprint(
    fingerprint_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FingerprintDetailResponse:
    """Calculate statistical distribution metrics and activate survey (Admin only)."""
    fp = await fingerprint_service.activate_fingerprint(db, fingerprint_id)
    stats_out = [
        FingerprintAPStatResponse(
            id=s.id,
            access_point_id=s.access_point_id,
            access_point_name=s.access_point.name if s.access_point else None,
            access_point_bssid=s.access_point.bssid if s.access_point else None,
            median_rssi=s.median_rssi,
            mean_rssi=s.mean_rssi,
            stddev_rssi=s.stddev_rssi,
            sample_count=s.sample_count,
        )
        for s in fp.ap_stats
    ]
    return FingerprintDetailResponse(
        id=fp.id,
        zone_id=fp.zone_id,
        zone_name=fp.zone.name if fp.zone else None,
        created_by=fp.created_by,
        creator_name=fp.creator.full_name if fp.creator else None,
        sample_count=fp.sample_count,
        quality_score=fp.quality_score,
        min_rssi_cutoff=fp.min_rssi_cutoff,
        status=fp.status,
        notes=fp.notes,
        created_at=fp.created_at,
        updated_at=fp.updated_at,
        ap_stats=stats_out,
    )
