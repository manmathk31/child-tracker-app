"""Security utilities: password hashing and JWT token lifecycle."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify that a plain-text password matches a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Compute a secure bcrypt hash of the provided password."""
    return pwd_context.hash(password)


def create_access_token(subject: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token.

    Args:
        subject: The user's unique identifier (UUID as string).
        role: The user's role (admin or teacher).
        expires_delta: Optional custom token expiration duration.

    Returns:
        str: Encoded JWT access token.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "role": str(role),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a longer-lived JWT refresh token.

    Args:
        subject: The user's unique identifier (UUID as string).
        expires_delta: Optional custom expiration duration.

    Returns:
        str: Encoded JWT refresh token.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a signed JWT token.

    Args:
        token: The encoded JWT token string.

    Returns:
        Dict[str, Any]: Decoded payload.

    Raises:
        UnauthorizedError: If token is expired, malformed, or invalid.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except ExpiredSignatureError as exc:
        raise UnauthorizedError("Session has expired. Please log in again.") from exc
    except JWTError as exc:
        raise UnauthorizedError("Could not validate credentials.") from exc
