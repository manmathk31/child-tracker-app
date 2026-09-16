"""Web page routes delivering server-rendered Jinja2 templates."""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_db, get_optional_current_user
from app.models.user import User

# Configure Jinja2 templates directory
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=RedirectResponse)
async def root_redirect(current_user: Optional[User] = Depends(get_optional_current_user)) -> RedirectResponse:
    """Redirect root access to dashboard if logged in, or login page if not."""
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Render the primary ChildTrack live dashboard with real data counts.

    Redirects unauthenticated visitors to the login page.
    """
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    settings = get_settings()
    context: Dict[str, Any] = {
        "request": request,
        "page_title": "Live Safety Dashboard",
        "active_page": "dashboard",
        "app_version": settings.APP_VERSION,
        "current_user": current_user,
        "total_students": 0,
        "trackable_students": 0,
        "attention_students": 0,
        "active_alerts_count": 0,
        "zones": [],
        "active_alerts": [],
    }
    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context=context,
    )
