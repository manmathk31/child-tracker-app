"""Shared FastAPI dependency injections (database session, authentication, role verification)."""

import uuid
from typing import AsyncGenerator, Optional

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.database.session import get_db
from app.models.user import User, UserRole
from app.services.auth_service import get_user_by_id


async def _extract_token(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Cookie(None),
) -> Optional[str]:
    """Extract token from either Authorization header (Bearer) or session cookie."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    if access_token:
        return access_token.strip()
    return None


async def get_optional_current_user(
    token: Optional[str] = Depends(_extract_token),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Return the authenticated user if a valid session exists, or None."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        user = await get_user_by_id(db, user_id)
        if user and user.is_active:
            return user
    except Exception:
        return None
    return None


async def get_current_user(
    token: Optional[str] = Depends(_extract_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate JWT token from header or cookie and return the active User entity.

    Raises:
        UnauthorizedError: If token is missing, invalid, or user does not exist.
    """
    if not token:
        raise UnauthorizedError("Authentication credentials were not provided.")

    payload = decode_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedError("Invalid token subject.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise UnauthorizedError("Invalid token user identifier.") from exc

    user = await get_user_by_id(db, user_id)
    if not user:
        raise UnauthorizedError("The user associated with this token no longer exists.")

    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated.")

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Enforce that the authenticated user possesses Administrator privileges.

    Raises:
        ForbiddenError: If user is not an admin.
    """
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenError("Administrator privileges are required to perform this action.")
    return current_user


__all__ = [
    "get_db",
    "get_optional_current_user",
    "get_current_user",
    "require_admin",
]
