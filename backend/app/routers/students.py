"""Students router providing REST API endpoints and Jinja2 web views for student management."""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_db, get_optional_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User, UserRole
from app.schemas.student import StudentCreate, StudentResponse, StudentUpdate
from app.services import (
    device_service,
    student_service,
    zone_service,
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Students"])


# ==============================================================================
# Web Views (Jinja2)
# ==============================================================================

@router.get("/students", response_class=HTMLResponse, include_in_schema=False)
async def students_list_page(
    request: Request,
    class_name: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render the students roster page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    students = await student_service.list_students(db, class_name=class_name)
    settings = get_settings()
    context = {
        "request": request,
        "page_title": "Students Roster",
        "active_page": "students",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "students": students,
        "selected_class": class_name,
    }
    return templates.TemplateResponse(request=request, name="students/list.html", context=context)


@router.get("/students/new", response_class=HTMLResponse, include_in_schema=False)
async def new_student_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render student enrollment form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/students", status_code=302)

    available_devices = await device_service.list_available_for_student(db)
    all_zones = await zone_service.list_zones(db)
    settings = get_settings()

    context = {
        "request": request,
        "page_title": "Enroll Student",
        "active_page": "students",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "student": None,
        "form_data": {},
        "available_devices": available_devices,
        "all_zones": all_zones,
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="students/form.html", context=context)


@router.post("/students/new", response_class=HTMLResponse, include_in_schema=False)
async def new_student_submit(
    request: Request,
    student_code: str = Form(...),
    full_name: str = Form(...),
    class_name: str = Form(...),
    age: int = Form(...),
    device_id: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process student enrollment submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    raw_zone_ids = form.getlist("allowed_zone_ids")

    parsed_device_id: Optional[uuid.UUID] = None
    if device_id and device_id.strip():
        try:
            parsed_device_id = uuid.UUID(device_id.strip())
        except ValueError:
            parsed_device_id = None

    parsed_zone_ids: List[uuid.UUID] = []
    for zid in raw_zone_ids:
        if zid and str(zid).strip():
            try:
                parsed_zone_ids.append(uuid.UUID(str(zid).strip()))
            except ValueError:
                pass

    form_data = {
        "student_code": student_code,
        "full_name": full_name,
        "class_name": class_name,
        "age": age,
        "device_id": str(parsed_device_id) if parsed_device_id else "",
        "allowed_zone_ids": [str(z) for z in parsed_zone_ids],
    }

    try:
        student_in = StudentCreate(
            student_code=student_code,
            full_name=full_name,
            class_name=class_name,
            age=age,
            device_id=parsed_device_id,
            allowed_zone_ids=parsed_zone_ids,
        )
        await student_service.create_student(db, student_in)
        return RedirectResponse(url="/students", status_code=status.HTTP_303_SEE_OTHER)
    except (ConflictError, NotFoundError, ValidationError) as exc:
        available_devices = await device_service.list_available_for_student(db)
        all_zones = await zone_service.list_zones(db)
        settings = get_settings()
        err = exc.message if hasattr(exc, "message") else str(exc)
        context = {
            "request": request,
            "page_title": "Enroll Student",
            "active_page": "students",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "student": None,
            "form_data": form_data,
            "available_devices": available_devices,
            "all_zones": all_zones,
            "error_message": err,
        }
        return templates.TemplateResponse(
            request=request, name="students/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


@router.get("/students/{student_id}", response_class=HTMLResponse, include_in_schema=False)
async def student_detail_page(
    student_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render student detail page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    try:
        student = await student_service.get_student_by_id(db, student_id)
    except NotFoundError:
        return RedirectResponse(url="/students", status_code=302)

    recent_history = []  # await localization_service.get_student_location_history(db, student_id, limit=5)
    live_info = None  # await localization_service.get_student_live_location(db, student_id)

    settings = get_settings()
    context = {
        "request": request,
        "page_title": f"Student: {student.full_name}",
        "active_page": "students",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "student": student,
        "recent_history": recent_history,
        "live_info": live_info,
    }
    return templates.TemplateResponse(request=request, name="students/detail.html", context=context)


@router.get("/students/{student_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_student_page(
    student_id: uuid.UUID,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render student edit form (Admin only)."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/students", status_code=302)

    try:
        student = await student_service.get_student_by_id(db, student_id)
    except NotFoundError:
        return RedirectResponse(url="/students", status_code=302)

    available_devices = await device_service.list_available_for_student(db, current_student_id=student.id)
    all_zones = await zone_service.list_zones(db)
    settings = get_settings()

    context = {
        "request": request,
        "page_title": f"Edit Student: {student.full_name}",
        "active_page": "students",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "student": student,
        "form_data": {},
        "available_devices": available_devices,
        "all_zones": all_zones,
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="students/form.html", context=context)


@router.post("/students/{student_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_student_submit(
    student_id: uuid.UUID,
    request: Request,
    student_code: str = Form(...),
    full_name: str = Form(...),
    class_name: str = Form(...),
    age: int = Form(...),
    device_id: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process student edit form submission."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    raw_zone_ids = form.getlist("allowed_zone_ids")

    parsed_device_id: Optional[uuid.UUID] = None
    if device_id and device_id.strip():
        try:
            parsed_device_id = uuid.UUID(device_id.strip())
        except ValueError:
            parsed_device_id = None

    parsed_zone_ids: List[uuid.UUID] = []
    for zid in raw_zone_ids:
        if zid and str(zid).strip():
            try:
                parsed_zone_ids.append(uuid.UUID(str(zid).strip()))
            except ValueError:
                pass

    try:
        student_in = StudentUpdate(
            student_code=student_code,
            full_name=full_name,
            class_name=class_name,
            age=age,
            device_id=parsed_device_id,
            allowed_zone_ids=parsed_zone_ids,
        )
        await student_service.update_student(db, student_id, student_in)
        return RedirectResponse(url=f"/students/{student_id}", status_code=status.HTTP_303_SEE_OTHER)
    except (ConflictError, NotFoundError, ValidationError) as exc:
        student = await student_service.get_student_by_id(db, student_id)
        available_devices = await device_service.list_available_for_student(db, current_student_id=student_id)
        all_zones = await zone_service.list_zones(db)
        settings = get_settings()
        err = exc.message if hasattr(exc, "message") else str(exc)
        context = {
            "request": request,
            "page_title": f"Edit Student: {student.full_name}",
            "active_page": "students",
            "app_version": settings.APP_VERSION,
            "current_user": current_user,
            "student": student,
            "form_data": {
                "student_code": student_code,
                "full_name": full_name,
                "class_name": class_name,
                "age": age,
            },
            "available_devices": available_devices,
            "all_zones": all_zones,
            "error_message": err,
        }
        return templates.TemplateResponse(
            request=request, name="students/form.html", context=context, status_code=status.HTTP_400_BAD_REQUEST
        )


@router.post("/students/{student_id}/delete", response_class=HTMLResponse, include_in_schema=False)
async def delete_student_form(
    student_id: uuid.UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Deactivate a student and release assigned wearable."""
    if not current_user or current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=302)

    await student_service.deactivate_student(db, student_id)
    return RedirectResponse(url="/students", status_code=status.HTTP_303_SEE_OTHER)


# ==============================================================================
# REST API Endpoints (/api/v1/students)
# ==============================================================================

@router.get("/api/v1/students", response_model=List[StudentResponse])
async def list_students_api(
    class_name: Optional[str] = None,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Sequence[StudentResponse]:
    """List all students enrolled in monitoring with their assigned wearable and allowed zones."""
    return await student_service.list_students(db, class_name=class_name, include_inactive=include_inactive)


@router.post(
    "/api/v1/students",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_api(
    student_in: StudentCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StudentResponse:
    """Enroll a new student and optionally assign a wearable and zone permissions."""
    return await student_service.create_student(db, student_in)


@router.get("/api/v1/students/{student_id}", response_model=StudentResponse)
async def get_student_api(
    student_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudentResponse:
    """Get student details by UUID."""
    return await student_service.get_student_by_id(db, student_id)


@router.put("/api/v1/students/{student_id}", response_model=StudentResponse)
async def update_student_api(
    student_id: uuid.UUID,
    student_in: StudentUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StudentResponse:
    """Update student profile, wearable assignment, or authorized zones."""
    return await student_service.update_student(db, student_id, student_in)


@router.delete("/api/v1/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student_api(
    student_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deactivate student profile and unpair hardware tag."""
    await student_service.deactivate_student(db, student_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
