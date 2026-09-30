"""Zones router providing REST API endpoints and Jinja2 web views for zone management."""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_db, get_optional_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User, UserRole
from app.schemas.zone import ZoneCreate, ZoneResponse, ZoneUpdate
from app.services import zone_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Zones"])


# ==============================================================================
# Web Views (Jinja2)
# ==============================================================================

@router.get("/zones", response_class=HTMLResponse, include_in_schema=False)
async def zones_list_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render the school zones list page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    zones = await zone_service.list_zones(db)
    settings = get_settings()
    context = {
        "request": request,
        "page_title": "School Zones",
        "active_page": "zones",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "zones": zones,
    }
    return templates.TemplateResponse(request=request, name="zones/list.html", context=context)


@router.get("/zones/new", response_class=HTMLResponse, include_in_schema=False)
async def new_zone_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> Any:
    """Render zone creation form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/zones", status_code=302)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": "Add New Zone",
        "active_page": "zones",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "zone": None,
        "form_data": {},
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="zones/form.html", context=context)


@router.post("/zones/new", response_class=HTMLResponse, include_in_schema=False)
async def new_zone_submit(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    building: Optional[str] = Form(None),
    floor: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process zone creation form submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    form_data = {"name": name, "description": description, "building": building, "floor": floor}
    try:
        zone_in = ZoneCreate(name=name, description=description, building=building, floor=floor)
        await zone_service.create_zone(db, zone_in)
        return RedirectResponse(url="/zones", status_code=status.HTTP_303_SEE_OTHER)
    except ConflictError as exc:
        settings = get_settings()
        context = {
            "request": request,
            "page_title": "Add New Zone",
            "active_page": "zones",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "zone": None,
            "form_data": form_data,
            "error_message": exc.message,
        }
        return templates.TemplateResponse(
            request=request, name="zones/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


@router.get("/zones/{zone_id}", response_class=HTMLResponse, include_in_schema=False)
async def zone_detail_page(
    zone_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render zone detail page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    try:
        zone = await zone_service.get_zone_by_id(db, zone_id)
    except NotFoundError:
        return RedirectResponse(url="/zones", status_code=302)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": f"Zone: {zone.name}",
        "active_page": "zones",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "zone": zone,
    }
    return templates.TemplateResponse(request=request, name="zones/detail.html", context=context)


@router.get("/zones/{zone_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_zone_page(
    zone_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render zone edit form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url=f"/zones/{zone_id}", status_code=302)

    try:
        zone = await zone_service.get_zone_by_id(db, zone_id)
    except NotFoundError:
        return RedirectResponse(url="/zones", status_code=302)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": f"Edit Zone: {zone.name}",
        "active_page": "zones",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "zone": zone,
        "form_data": {},
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="zones/form.html", context=context)


@router.post("/zones/{zone_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_zone_submit(
    zone_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    building: Optional[str] = Form(None),
    floor: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process zone edit submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    try:
        zone_in = ZoneUpdate(name=name, description=description, building=building, floor=floor)
        await zone_service.update_zone(db, zone_id, zone_in)
        return RedirectResponse(url=f"/zones/{zone_id}", status_code=status.HTTP_303_SEE_OTHER)
    except ConflictError as exc:
        zone = await zone_service.get_zone_by_id(db, zone_id)
        settings = get_settings()
        context = {
            "request": request,
            "page_title": f"Edit Zone: {zone.name}",
            "active_page": "zones",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "zone": zone,
            "form_data": {"name": name, "description": description, "building": building, "floor": floor},
            "error_message": exc.message,
        }
        return templates.TemplateResponse(
            request=request, name="zones/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


@router.post("/zones/{zone_id}/delete", include_in_schema=False)
async def delete_zone(
    zone_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Soft delete a zone."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    try:
        await zone_service.deactivate_zone(db, zone_id)
    except NotFoundError:
        pass
    
    return RedirectResponse(url="/zones", status_code=status.HTTP_303_SEE_OTHER)


# ==============================================================================
# REST API Endpoints (/api/v1/zones/*)
# ==============================================================================

@router.get("/api/v1/zones", response_model=List[ZoneResponse], summary="List Zones")
async def api_list_zones(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ZoneResponse]:
    """List all registered school zones."""
    zones = await zone_service.list_zones(db, include_inactive=include_inactive)
    return [
        ZoneResponse(
            id=z.id,
            name=z.name,
            description=z.description,
            building=z.building,
            floor=z.floor,
            is_active=z.is_active,
            created_at=z.created_at,
            updated_at=z.updated_at,
            scanner_devices_count=len(z.scanner_devices),
        )
        for z in zones
    ]


@router.post("/api/v1/zones", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED, summary="Create Zone")
async def api_create_zone(
    zone_in: ZoneCreate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ZoneResponse:
    """Create a new zone (Administrator only)."""
    zone = await zone_service.create_zone(db, zone_in)
    return ZoneResponse.model_validate(zone)


@router.get("/api/v1/zones/{zone_id}", response_model=ZoneResponse, summary="Get Zone Details")
async def api_get_zone(
    zone_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ZoneResponse:
    """Get zone metadata and access points count."""
    zone = await zone_service.get_zone_by_id(db, zone_id)
    return ZoneResponse(
        id=zone.id,
        name=zone.name,
        description=zone.description,
        building=zone.building,
        floor=zone.floor,
        is_active=zone.is_active,
        created_at=zone.created_at,
        updated_at=zone.updated_at,
        scanner_devices_count=len(zone.scanner_devices),
    )


@router.put("/api/v1/zones/{zone_id}", response_model=ZoneResponse, summary="Update Zone")
async def api_update_zone(
    zone_id: uuid.UUID,
    zone_in: ZoneUpdate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ZoneResponse:
    """Update zone metadata (Administrator only)."""
    zone = await zone_service.update_zone(db, zone_id, zone_in)
    return ZoneResponse.model_validate(zone)


@router.delete("/api/v1/zones/{zone_id}", response_model=ZoneResponse, summary="Deactivate Zone")
async def api_deactivate_zone(
    zone_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ZoneResponse:
    """Soft-delete/deactivate a zone (Administrator only)."""
    zone = await zone_service.deactivate_zone(db, zone_id)
    return ZoneResponse.model_validate(zone)
