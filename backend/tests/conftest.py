"""Pytest configuration and shared test fixtures."""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# Force testing environment before loading app
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_childtrack.db"

from app.core.security import create_access_token  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_engine, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402
from app.services.auth_service import create_user, get_user_by_email  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db() -> AsyncGenerator[None, None]:
    """Create all schema tables in test database and clean up after session."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # Clean up file
    test_db_file = "./test_childtrack.db"
    if os.path.exists(test_db_file):
        try:
            os.remove(test_db_file)
        except Exception:
            pass


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP client wired to the FastAPI test application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session for direct service queries."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Ensure an admin user exists and return it."""
    email = "testadmin@childtrack.local"
    user = await get_user_by_email(db_session, email)
    if not user:
        user = await create_user(
            db_session,
            UserCreate(
                email=email,
                full_name="Admin Tester",
                role=UserRole.ADMIN,
                password="TestPassword123!",
            ),
        )
    return user


@pytest_asyncio.fixture
async def teacher_user(db_session: AsyncSession) -> User:
    """Ensure a teacher user exists and return it."""
    email = "testteacher@childtrack.local"
    user = await get_user_by_email(db_session, email)
    if not user:
        user = await create_user(
            db_session,
            UserCreate(
                email=email,
                full_name="Teacher Tester",
                role=UserRole.TEACHER,
                password="TestPassword123!",
            ),
        )
    return user


@pytest_asyncio.fixture
def admin_headers(admin_user: User) -> dict:
    """Return authorization bearer header for admin user."""
    token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
def teacher_headers(teacher_user: User) -> dict:
    """Return authorization bearer header for teacher user."""
    token = create_access_token(subject=str(teacher_user.id), role=teacher_user.role.value)
    return {"Authorization": f"Bearer {token}"}
