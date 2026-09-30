"""Authentication and user management business logic."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate

logger = logging.getLogger("childtrack.auth_service")


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Retrieve an active or inactive user by normalized email address.

    Args:
        db: Database session.
        email: User email.

    Returns:
        User or None.
    """
    stmt = select(User).where(func.lower(User.email) == email.strip().lower())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Retrieve a user by unique UUID primary key.

    Args:
        db: Database session.
        user_id: User UUID.

    Returns:
        User or None.
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """Authenticate a user by email and password, updating last login timestamp.

    Args:
        db: Database session.
        email: User email.
        password: Plaintext password.

    Returns:
        User: Authenticated user entity.

    Raises:
        UnauthorizedError: If email not found, password invalid, or account inactive.
    """
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        logger.warning("Failed login attempt for email=%s", email.strip().lower())
        raise UnauthorizedError("Invalid email or password.")

    if not user.is_active:
        logger.warning("Login attempted for deactivated account: %s", user.email)
        raise UnauthorizedError("This account has been deactivated. Please contact an administrator.")

    # Record login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    logger.info("User successfully authenticated: id=%s email=%s role=%s", user.id, user.email, user.role.value)
    return user


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    """Create a new user account. Only administrators may execute this in production.

    Args:
        db: Database session.
        user_in: Validated user creation schema.

    Returns:
        User: Newly created persistent user.

    Raises:
        ConflictError: If a user with the given email already exists.
    """
    existing = await get_user_by_email(db, user_in.email)
    if existing:
        raise ConflictError(f"A user with email '{user_in.email}' already exists.")

    hashed_pw = get_password_hash(user_in.password)
    user = User(
        email=user_in.email.strip().lower(),
        hashed_password=hashed_pw,
        full_name=user_in.full_name.strip(),
        role=user_in.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("New user registered: id=%s email=%s role=%s", user.id, user.email, user.role.value)
    return user


async def list_users(db: AsyncSession) -> Sequence[User]:
    """Retrieve all users in the system."""
    stmt = select(User).order_by(User.full_name)
    result = await db.execute(stmt)
    return result.scalars().all()
