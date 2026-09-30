"""Automated test suite for authentication, authorization, and session management."""

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token, decode_token, get_password_hash, verify_password
from app.database.session import get_session_factory
from app.models.user import UserRole
from app.schemas.user import UserCreate
from app.services.auth_service import create_user, get_user_by_email


# ==============================================================================
# Security Unit Tests
# ==============================================================================

def test_password_hashing_and_verification() -> None:
    """Verify password hashing produces salted hashes and verifies accurately."""
    raw_password = "SecurePassword123!"
    hashed = get_password_hash(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_generation_and_decoding() -> None:
    """Verify JWT access tokens encode and decode correctly."""
    subject = "12345678-1234-5678-1234-567812345678"
    role = "admin"
    token = create_access_token(subject=subject, role=role)

    payload = decode_token(token)
    assert payload["sub"] == subject
    assert payload["role"] == role
    assert payload["type"] == "access"
    assert "exp" in payload


# ==============================================================================
# Authentication End-to-End Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_login_page_renders(client: AsyncClient) -> None:
    """Verify that GET /login displays the sign-in template."""
    response = await client.get("/login")
    assert response.status_code == 200
    assert "Sign In" in response.text
    assert 'id="login-form"' in response.text


@pytest.mark.asyncio
async def test_web_login_form_flow(client: AsyncClient) -> None:
    """Verify web login form submission with valid and invalid credentials."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        web_user_email = "formtest@school.edu"
        user = await get_user_by_email(db, web_user_email)
        if not user:
            await create_user(
                db,
                UserCreate(
                    email=web_user_email,
                    password="FormPassword123!",
                    full_name="Form Test User",
                    role=UserRole.TEACHER,
                ),
            )

    # 1. Submit invalid form credentials -> 401
    bad_resp = await client.post(
        "/login",
        data={"email": web_user_email, "password": "WrongPassword!"},
    )
    assert bad_resp.status_code == 401
    assert "Invalid email or password" in bad_resp.text

    # 2. Submit valid form credentials -> 303 redirect with cookie
    good_resp = await client.post(
        "/login",
        data={"email": web_user_email, "password": "FormPassword123!"},
        follow_redirects=False,
    )
    assert good_resp.status_code == 303
    assert good_resp.headers["location"] == "/dashboard"
    assert "access_token" in good_resp.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_api_auth_lifecycle(client: AsyncClient) -> None:
    """Verify user provisioning, API login, me endpoint, and logout."""
    # 1. Provision an admin user in test DB
    session_factory = get_session_factory()
    async with session_factory() as db:
        admin_email = "testadmin@school.edu"
        user = await get_user_by_email(db, admin_email)
        if not user:
            user = await create_user(
                db,
                UserCreate(
                    email=admin_email,
                    password="AdminPassword123!",
                    full_name="Test Administrator",
                    role=UserRole.ADMIN,
                ),
            )

    # 2. Test API login with invalid credentials -> 401
    bad_login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": "WrongPassword"},
    )
    assert bad_login.status_code == 401

    # 3. Test API login with valid credentials -> 200
    good_login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": "AdminPassword123!"},
    )
    assert good_login.status_code == 200
    login_data = good_login.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == admin_email
    assert login_data["user"]["role"] == "admin"
    admin_token = login_data["access_token"]

    # 4. Access /api/v1/auth/me with Bearer token
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == admin_email

    # 5. Admin creates a teacher account via API
    teacher_email = "teacher1@school.edu"
    create_teacher_resp = await client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": teacher_email,
            "password": "TeacherPassword123!",
            "full_name": "Class Teacher 1",
            "role": "teacher",
        },
    )
    assert create_teacher_resp.status_code == 201
    assert create_teacher_resp.json()["role"] == "teacher"

    # 6. Teacher logs in and obtains token
    teacher_login = await client.post(
        "/api/v1/auth/login",
        json={"email": teacher_email, "password": "TeacherPassword123!"},
    )
    assert teacher_login.status_code == 200
    teacher_token = teacher_login.json()["access_token"]

    # 7. Teacher attempts to create a user -> 403 Forbidden
    forbidden_resp = await client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={
            "email": "another@school.edu",
            "password": "Password123!",
            "full_name": "Unauthorized User",
            "role": "teacher",
        },
    )
    assert forbidden_resp.status_code == 403

    # 8. Web dashboard accessed with session cookie
    dash_resp = await client.get(
        "/dashboard",
        cookies={"access_token": admin_token},
    )
    assert dash_resp.status_code == 200
    assert "Live Safety Dashboard" in dash_resp.text
    assert "Test Administrator" in dash_resp.text

    # 9. Web logout
    logout_resp = await client.get("/logout", follow_redirects=False)
    assert logout_resp.status_code == 302
    assert logout_resp.headers["location"] == "/login"
