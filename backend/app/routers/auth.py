"""Authentication router providing OAuth2/JWT API endpoints and Jinja2 web login/logout views."""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user, get_db, get_optional_current_user, require_admin
from app.core.exceptions import ChildTrackException, UnauthorizedError
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import LoginRequest, TokenResponse, UserCreate, UserResponse
from app.services.auth_service import authenticate_user, create_user

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Authentication"])


# ==============================================================================
# Web Login & Logout Routes (Jinja2)
# ==============================================================================

@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> Any:
    """Render the user login page. Redirects to dashboard if already authenticated."""
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    context = {
        "request": request,
        "page_title": "Sign In",
        "error_message": None,
    }
    return templates.TemplateResponse(request=request, name="auth/login.html", context=context)


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_form_submit(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Process login form submission, set session cookie, and redirect to dashboard."""
    settings = get_settings()
    try:
        user = await authenticate_user(db, email=email, password=password)
        token = create_access_token(subject=str(user.id), role=user.role.value)

        redirect_res = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        redirect_res.set_cookie(
            key="access_token",
            value=token,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=True,
            samesite="lax",
            secure=settings.is_production,
        )
        return redirect_res
    except UnauthorizedError as exc:
        context = {
            "request": request,
            "page_title": "Sign In",
            "error_message": exc.message,
            "email_value": email,
        }
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context=context,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


@router.get("/logout", response_class=RedirectResponse, include_in_schema=False)
async def logout_web(response: Response) -> RedirectResponse:
    """Clear session cookie and redirect to login page."""
    redirect_res = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect_res.delete_cookie(key="access_token")
    return redirect_res


# ==============================================================================
# REST API Endpoints (/api/v1/auth/*)
# ==============================================================================

@router.post(
    "/api/v1/auth/login",
    response_model=TokenResponse,
    summary="User Login",
    description="Authenticate with email and password to obtain a JWT access token.",
)
async def api_login(
    login_data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """API endpoint for authenticating and obtaining an access token."""
    settings = get_settings()
    user = await authenticate_user(db, email=login_data.email, password=login_data.password)
    token = create_access_token(subject=str(user.id), role=user.role.value)

    # Also attach HttpOnly cookie for browser consumers of this API
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/api/v1/auth/logout",
    summary="User Logout",
    description="Clears the authentication session cookie.",
)
async def api_logout(response: Response) -> Dict[str, str]:
    """API endpoint for clearing the session cookie."""
    response.delete_cookie(key="access_token")
    return {"status": "success", "message": "Successfully logged out."}


@router.get(
    "/api/v1/auth/me",
    response_model=UserResponse,
    summary="Current User Profile",
    description="Returns the profile and role of the currently authenticated user.",
)
async def api_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return current authenticated user profile."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/api/v1/auth/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User (Admin only)",
    description="Provision a new user account with administrator or teacher role.",
)
async def api_create_user(
    user_in: UserCreate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Administrator-only endpoint to register a new user account."""
    user = await create_user(db, user_in)
    return UserResponse.model_validate(user)
