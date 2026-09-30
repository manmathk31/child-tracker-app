"""Devices router providing REST API endpoints and Jinja2 web views for wearable tags."""

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
from app.models.device import DeviceType
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate
from app.services import device_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Devices"])


# ==============================================================================
# Web Views (Jinja2)
# ==============================================================================

@router.get("/devices", response_class=HTMLResponse, include_in_schema=False)
async def devices_list_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render wearables list page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    devices = await device_service.list_devices(db, include_inactive=True)
    settings = get_settings()
    context = {
        "request": request,
        "page_title": "Wearables",
        "active_page": "devices",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "devices": devices,
    }
    return templates.TemplateResponse(request=request, name="devices/list.html", context=context)


@router.get("/devices/new", response_class=HTMLResponse, include_in_schema=False)
async def new_device_page(
    request: Request,
    type: str = "WEARABLE",
    zone_id: Optional[uuid.UUID] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render wearable registration form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/devices", status_code=302)

    from app.services import zone_service
    zones = await zone_service.list_zones(db)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": "Register Wearable",
        "active_page": "devices",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "device": None,
        "type": type,
        "zone_id": zone_id,
        "zones": zones,
        "form_data": {},
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="devices/form.html", context=context)


@router.post("/devices/new", response_class=HTMLResponse, include_in_schema=False)
async def new_device_submit(
    request: Request,
    device_code: str = Form(...),
    mac_address: str = Form(...),
    battery_percent: int = Form(100),
    type: str = Form("wearable"),
    assigned_zone_id: Optional[uuid.UUID] = Form(None),
    firmware_version: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process wearable registration form submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    form_data = {
        "device_code": device_code,
        "mac_address": mac_address,
        "battery_percent": battery_percent,
        "firmware_version": firmware_version,
    }

    try:
        dev_in = DeviceCreate(
            device_code=device_code,
            mac_address=mac_address,
            battery_percent=battery_percent,
            type=DeviceType(type.lower()),
            assigned_zone_id=assigned_zone_id,
            firmware_version=firmware_version,
        )
        await device_service.create_device(db, dev_in)
        return RedirectResponse(url="/devices", status_code=status.HTTP_303_SEE_OTHER)
    except (ConflictError, ValueError) as exc:
        settings = get_settings()
        context = {
            "request": request,
            "page_title": "Register Wearable",
            "active_page": "devices",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "device": None,
            "form_data": form_data,
            "error_message": getattr(exc, "message", str(exc)),
        }
        return templates.TemplateResponse(
            request=request, name="devices/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


@router.get("/devices/{device_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_device_page(
    device_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render wearable edit form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/devices", status_code=302)

    try:
        device = await device_service.get_device_by_id(db, device_id)
    except NotFoundError:
        return RedirectResponse(url="/devices", status_code=302)

    from app.services import zone_service
    zones = await zone_service.list_zones(db)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": f"Edit Wearable: {device.device_code}",
        "active_page": "devices",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "device": device,
        "zones": zones,
        "form_data": {},
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="devices/form.html", context=context)


@router.post("/devices/{device_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_device_submit(
    device_id: uuid.UUID,
    request: Request,
    device_code: str = Form(...),
    mac_address: str = Form(...),
    battery_percent: int = Form(...),
    type: str = Form("wearable"),
    assigned_zone_id: Optional[uuid.UUID] = Form(None),
    firmware_version: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process wearable edit submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    try:
        dev_in = DeviceUpdate(
            device_code=device_code,
            mac_address=mac_address,
            battery_percent=battery_percent,
            type=DeviceType(type.lower()),
            assigned_zone_id=assigned_zone_id,
            firmware_version=firmware_version,
        )
        await device_service.update_device(db, device_id, dev_in)
        return RedirectResponse(url="/devices", status_code=status.HTTP_303_SEE_OTHER)
    except (ConflictError, ValueError) as exc:
        device = await device_service.get_device_by_id(db, device_id)
        settings = get_settings()
        context = {
            "request": request,
            "page_title": f"Edit Wearable: {device_code}",
            "active_page": "devices",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "device": device,
            "zones": await zone_service.list_zones(db),
            "form_data": {
                "device_code": device_code,
                "mac_address": mac_address,
                "battery_percent": battery_percent,
                "firmware_version": firmware_version,
            },
            "error_message": getattr(exc, "message", str(exc)),
        }
        return templates.TemplateResponse(
            request=request, name="devices/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )

@router.post("/devices/{device_id}/toggle", include_in_schema=False)
async def toggle_device_status(
    device_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Toggle the enabled/disabled state of a hardware device."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    device = await device_service.get_device_by_id(db, device_id)
    device.is_active = not device.is_active
    await db.commit()
    return RedirectResponse(url="/devices", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/devices/{device_id}/delete", include_in_schema=False)
async def delete_device(
    device_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Soft delete a device."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    try:
        await device_service.deactivate_device(db, device_id)
    except NotFoundError:
        pass
    
    return RedirectResponse(url="/devices", status_code=status.HTTP_303_SEE_OTHER)


# ==============================================================================
# REST API Endpoints (/api/v1/devices/*)
# ==============================================================================

@router.get("/api/v1/devices", response_model=List[DeviceResponse], summary="List Wearables")
async def api_list_devices(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[DeviceResponse]:
    """List registered ESP32 wearable devices."""
    devices = await device_service.list_devices(db, include_inactive=include_inactive)
    return [
        DeviceResponse(
            id=d.id,
            device_code=d.device_code,
            mac_address=d.mac_address,
            battery_percent=d.battery_percent,
            firmware_version=d.firmware_version,
            last_seen_at=d.last_seen_at,
            status=d.status,
            type=d.type,
            assigned_zone_id=d.assigned_zone_id,
            assigned_zone_name=d.zone.name if getattr(d, 'zone', None) else None,
            student_id=d.student_id,
            student_name=d.student.full_name if d.student else None,
            is_active=d.is_active,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in devices
    ]


@router.post("/api/v1/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED, summary="Register Wearable")
async def api_create_device(
    device_in: DeviceCreate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Register a new ESP32 tag (Admin only)."""
    device = await device_service.create_device(db, device_in)
    return DeviceResponse(
        id=device.id,
        device_code=device.device_code,
        mac_address=device.mac_address,
        battery_percent=device.battery_percent,
        firmware_version=device.firmware_version,
        last_seen_at=device.last_seen_at,
        status=device.status,
        type=device.type,
        assigned_zone_id=device.assigned_zone_id,
        assigned_zone_name=device.zone.name if getattr(device, 'zone', None) else None,
        student_id=device.student_id,
        student_name=device.student.full_name if device.student else None,
        is_active=device.is_active,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


@router.get("/api/v1/devices/{device_id}", response_model=DeviceResponse, summary="Get Wearable")
async def api_get_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Retrieve wearable details by UUID."""
    device = await device_service.get_device_by_id(db, device_id)
    return DeviceResponse(
        id=device.id,
        device_code=device.device_code,
        mac_address=device.mac_address,
        battery_percent=device.battery_percent,
        firmware_version=device.firmware_version,
        last_seen_at=device.last_seen_at,
        status=device.status,
        type=device.type,
        assigned_zone_id=device.assigned_zone_id,
        assigned_zone_name=device.zone.name if getattr(device, 'zone', None) else None,
        student_id=device.student_id,
        student_name=device.student.full_name if device.student else None,
        is_active=device.is_active,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


@router.put("/api/v1/devices/{device_id}", response_model=DeviceResponse, summary="Update Wearable")
async def api_update_device(
    device_id: uuid.UUID,
    device_in: DeviceUpdate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Update wearable metadata or assignment (Admin only)."""
    device = await device_service.update_device(db, device_id, device_in)
    return DeviceResponse(
        id=device.id,
        device_code=device.device_code,
        mac_address=device.mac_address,
        battery_percent=device.battery_percent,
        firmware_version=device.firmware_version,
        last_seen_at=device.last_seen_at,
        status=device.status,
        type=device.type,
        assigned_zone_id=device.assigned_zone_id,
        assigned_zone_name=device.zone.name if getattr(device, 'zone', None) else None,
        student_id=device.student_id,
        student_name=device.student.full_name if device.student else None,
        is_active=device.is_active,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


@router.delete("/api/v1/devices/{device_id}", response_model=DeviceResponse, summary="Deactivate Wearable")
async def api_deactivate_device(
    device_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Deactivate a wearable hardware tag (Admin only)."""
    device = await device_service.deactivate_device(db, device_id)
    return DeviceResponse(
        id=device.id,
        device_code=device.device_code,
        mac_address=device.mac_address,
        battery_percent=device.battery_percent,
        firmware_version=device.firmware_version,
        last_seen_at=device.last_seen_at,
        status=device.status,
        type=device.type,
        assigned_zone_id=device.assigned_zone_id,
        assigned_zone_name=device.zone.name if getattr(device, 'zone', None) else None,
        student_id=device.student_id,
        student_name=None,
        is_active=device.is_active,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )
