"""Shared FastAPI dependency injections (database session, authentication stubs)."""

from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db

__all__ = ["get_db"]
