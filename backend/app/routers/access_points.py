"""Access Points router providing REST API endpoints and Jinja2 web views."""

import uuid
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_db, get_optional_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User, UserRole
from app.schemas.access_point import AccessPointCreate, AccessPointResponse, AccessPointUpdate
from app.services import access_point_service, zone_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Access Points"])


# ==============================================================================
# Web Views (Jinja2)
# ==============================================================================

@router.get("/access-points", response_class=HTMLResponse, include_in_schema=False)
async def access_points_list_page(
    request: Request,
    zone_id: Optional[uuid.UUID] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render access points listing page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    aps = await access_point_service.list_access_points(db, zone_id=zone_id)
    settings = get_settings()
    context = {
        "request": request,
        "page_title": "Access Points",
        "active_page": "access_points",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "access_points": aps,
    }
    return templates.TemplateResponse(request=request, name="access_points/list.html", context=context)


@router.get("/access-points/new", response_class=HTMLResponse, include_in_schema=False)
async def new_access_point_page(
    request: Request,
    zone_id: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render AP registration form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/access-points", status_code=302)

    zones = await zone_service.list_zones(db)
    settings = get_settings()
    context = {
        "request": request,
        "page_title": "Register Access Point",
        "active_page": "access_points",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "zones": zones,
        "selected_zone_id": zone_id,
        "ap": None,
        "form_data": {},
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="access_points/form.html", context=context)


@router.post("/access-points/new", response_class=HTMLResponse, include_in_schema=False)
async def new_access_point_submit(
    request: Request,
    name: str = Form(...),
    bssid: str = Form(...),
    channel: Optional[int] = Form(None),
    zone_id: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process AP registration form submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    parsed_zone_id = uuid.UUID(zone_id) if zone_id and zone_id.strip() else None
    form_data = {"name": name, "bssid": bssid, "channel": channel, "zone_id": zone_id}

    try:
        ap_in = AccessPointCreate(name=name, bssid=bssid, channel=channel, zone_id=parsed_zone_id)
        await access_point_service.create_access_point(db, ap_in)
        return RedirectResponse(url="/access-points", status_code=status.HTTP_303_SEE_OTHER)
    except (ConflictError, NotFoundError, ValueError) as exc:
        zones = await zone_service.list_zones(db)
        settings = get_settings()
        context = {
            "request": request,
            "page_title": "Register Access Point",
            "active_page": "access_points",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "zones": zones,
            "selected_zone_id": zone_id,
            "ap": None,
            "form_data": form_data,
            "error_message": getattr(exc, "message", str(exc)),
        }
        return templates.TemplateResponse(
            request=request, name="access_points/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


@router.get("/access-points/{ap_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_access_point_page(
    ap_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render AP edit form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/access-points", status_code=302)

    try:
        ap = await access_point_service.get_access_point_by_id(db, ap_id)
    except NotFoundError:
        return RedirectResponse(url="/access-points", status_code=302)

    zones = await zone_service.list_zones(db)
    settings = get_settings()
    context = {
        "request": request,
        "page_title": f"Edit AP: {ap.name}",
        "active_page": "access_points",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "zones": zones,
        "selected_zone_id": str(ap.zone_id) if ap.zone_id else None,
        "ap": ap,
        "form_data": {},
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="access_points/form.html", context=context)


@router.post("/access-points/{ap_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_access_point_submit(
    ap_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    bssid: str = Form(...),
    channel: Optional[int] = Form(None),
    zone_id: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process AP modification form submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    parsed_zone_id = uuid.UUID(zone_id) if zone_id and zone_id.strip() else None
    try:
        ap_in = AccessPointUpdate(name=name, bssid=bssid, channel=channel, zone_id=parsed_zone_id)
        await access_point_service.update_access_point(db, ap_id, ap_in)
        return RedirectResponse(url="/access-points", status_code=status.HTTP_303_SEE_OTHER)
    except (ConflictError, NotFoundError, ValueError) as exc:
        ap = await access_point_service.get_access_point_by_id(db, ap_id)
        zones = await zone_service.list_zones(db)
        settings = get_settings()
        context = {
            "request": request,
            "page_title": f"Edit AP: {name}",
            "active_page": "access_points",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "zones": zones,
            "selected_zone_id": zone_id,
            "ap": ap,
            "form_data": {"name": name, "bssid": bssid, "channel": channel, "zone_id": zone_id},
            "error_message": getattr(exc, "message", str(exc)),
        }
        return templates.TemplateResponse(
            request=request, name="access_points/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


# ==============================================================================
# REST API Endpoints (/api/v1/access-points/*)
# ==============================================================================

@router.get("/api/v1/access-points", response_model=List[AccessPointResponse], summary="List Access Points")
async def api_list_access_points(
    zone_id: Optional[uuid.UUID] = None,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AccessPointResponse]:
    """List registered Wi-Fi access points."""
    aps = await access_point_service.list_access_points(db, zone_id=zone_id, include_inactive=include_inactive)
    return [
        AccessPointResponse(
            id=ap.id,
            name=ap.name,
            bssid=ap.bssid,
            channel=ap.channel,
            zone_id=ap.zone_id,
            zone_name=ap.zone.name if ap.zone else None,
            is_active=ap.is_active,
            created_at=ap.created_at,
            updated_at=ap.updated_at,
        )
        for ap in aps
    ]


@router.post("/api/v1/access-points", response_model=AccessPointResponse, status_code=status.HTTP_201_CREATED, summary="Register Access Point")
async def api_create_access_point(
    ap_in: AccessPointCreate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AccessPointResponse:
    """Register a new Access Point (Admin only)."""
    ap = await access_point_service.create_access_point(db, ap_in)
    return AccessPointResponse(
        id=ap.id,
        name=ap.name,
        bssid=ap.bssid,
        channel=ap.channel,
        zone_id=ap.zone_id,
        zone_name=ap.zone.name if ap.zone else None,
        is_active=ap.is_active,
        created_at=ap.created_at,
        updated_at=ap.updated_at,
    )


@router.get("/api/v1/access-points/{ap_id}", response_model=AccessPointResponse, summary="Get Access Point")
async def api_get_access_point(
    ap_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessPointResponse:
    """Retrieve an Access Point by UUID."""
    ap = await access_point_service.get_access_point_by_id(db, ap_id)
    return AccessPointResponse(
        id=ap.id,
        name=ap.name,
        bssid=ap.bssid,
        channel=ap.channel,
        zone_id=ap.zone_id,
        zone_name=ap.zone.name if ap.zone else None,
        is_active=ap.is_active,
        created_at=ap.created_at,
        updated_at=ap.updated_at,
    )


@router.put("/api/v1/access-points/{ap_id}", response_model=AccessPointResponse, summary="Update Access Point")
async def api_update_access_point(
    ap_id: uuid.UUID,
    ap_in: AccessPointUpdate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AccessPointResponse:
    """Update an Access Point (Admin only)."""
    ap = await access_point_service.update_access_point(db, ap_id, ap_in)
    return AccessPointResponse(
        id=ap.id,
        name=ap.name,
        bssid=ap.bssid,
        channel=ap.channel,
        zone_id=ap.zone_id,
        zone_name=ap.zone.name if ap.zone else None,
        is_active=ap.is_active,
        created_at=ap.created_at,
        updated_at=ap.updated_at,
    )


@router.delete("/api/v1/access-points/{ap_id}", response_model=AccessPointResponse, summary="Deactivate Access Point")
async def api_delete_access_point(
    ap_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AccessPointResponse:
    """Soft-delete an Access Point (Admin only)."""
    ap = await access_point_service.delete_access_point(db, ap_id)
    return AccessPointResponse(
        id=ap.id,
        name=ap.name,
        bssid=ap.bssid,
        channel=ap.channel,
        zone_id=ap.zone_id,
        zone_name=ap.zone.name if ap.zone else None,
        is_active=ap.is_active,
        created_at=ap.created_at,
        updated_at=ap.updated_at,
    )
