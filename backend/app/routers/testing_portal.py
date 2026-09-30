"""Dedicated Testing Portal router for Master-Slave ESP proximity and tether monitoring.

Features:
- Isolated testing credentials ('tester' / 'Test@12345') configured via .env.
- Live separation radar dashboard view.
- Real-time JSON telemetry endpoint for live UI updates and alarms.
"""

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.services import testing_tether_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Testing Portal"])

SESSION_COOKIE_NAME = "childtrack_tester_session"


def _is_tester_authenticated(request: Request) -> bool:
    """Verify testing portal session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return token == "tester_authenticated_ok"


# ==============================================================================
# Authentication Views
# ==============================================================================

@router.get("/testing-portal/login", response_class=HTMLResponse, include_in_schema=False)
async def testing_login_page(request: Request) -> Any:
    """Render the isolated testing portal login page."""
    if _is_tester_authenticated(request):
        return RedirectResponse(url="/testing-portal", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="testing_portal/login.html",
        context={"request": request, "error_message": None},
    )


@router.post("/testing-portal/login", response_class=HTMLResponse, include_in_schema=False)
async def testing_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> Any:
    """Validate testing credentials and create testing session."""
    settings = get_settings()

    if (
        username.strip() == settings.TESTING_PORTAL_USERNAME
        and password.strip() == settings.TESTING_PORTAL_PASSWORD
    ):
        response = RedirectResponse(url="/testing-portal", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value="tester_authenticated_ok",
            max_age=86400,  # 24 hours
            httponly=True,
            samesite="lax",
        )
        return response

    return templates.TemplateResponse(
        request=request,
        name="testing_portal/login.html",
        context={
            "request": request,
            "error_message": "Invalid testing credentials. Use username 'tester' and password 'Test@12345'",
            "username": username,
        },
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@router.get("/testing-portal/logout", include_in_schema=False)
async def testing_logout() -> Response:
    """Clear testing portal session."""
    response = RedirectResponse(url="/testing-portal/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# ==============================================================================
# Testing Portal Dashboard View
# ==============================================================================

@router.get("/testing-portal", response_class=HTMLResponse, include_in_schema=False)
async def testing_dashboard_page(request: Request) -> Any:
    """Render the live Master-Slave proximity testing radar dashboard."""
    if not _is_tester_authenticated(request):
        return RedirectResponse(url="/testing-portal/login", status_code=302)

    status_data = testing_tether_service.get_tether_monitor().get_status()
    settings = get_settings()

    context = {
        "request": request,
        "page_title": "ESP Proximity Testing Portal",
        "app_version": settings.APP_VERSION,
        "status_data": status_data,
    }
    return templates.TemplateResponse(
        request=request,
        name="testing_portal/dashboard.html",
        context=context,
    )


# ==============================================================================
# Live JSON Telemetry API
# ==============================================================================

@router.get("/testing-portal/api/status")
async def api_get_testing_status(request: Request) -> Dict[str, Any]:
    """Retrieve real-time proximity state, RSSI, and separation alarm status."""
    if not _is_tester_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    return testing_tether_service.get_tether_monitor().get_status()


@router.post("/testing-portal/api/threshold")
async def api_set_threshold(
    request: Request,
    warning_rssi: int = Form(-75),
    alert_rssi: int = Form(-85),
) -> Dict[str, Any]:
    """Update dynamic proximity alert thresholds from UI slider."""
    if not _is_tester_authenticated(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    testing_tether_service.get_tether_monitor().set_thresholds(warning_rssi, alert_rssi)
    return {"status": "ok", "warning_threshold": warning_rssi, "alert_threshold": alert_rssi}
