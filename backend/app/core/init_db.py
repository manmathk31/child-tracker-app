"""Database initialization and initial administrator provisioning script."""

import argparse
import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.session import get_engine, get_session_factory
from app.models.user import UserRole
from app.schemas.user import UserCreate
from app.services.auth_service import create_user, get_user_by_email

logger = logging.getLogger("childtrack.init_db")


async def init_admin_user(
    email: str = "admin@childtrack.local",
    password: str = "Admin@12345",
    full_name: str = "System Administrator",
) -> None:
    """Create the initial administrator account if no admin currently exists."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        existing = await get_user_by_email(db, email)
        if existing:
            logger.info("Administrator user with email '%s' already exists.", email)
            return

        user_in = UserCreate(
            email=email,
            password=password,
            full_name=full_name,
            role=UserRole.ADMIN,
        )
        created = await create_user(db, user_in)
        logger.info("Initial administrator account created successfully: %s (%s)", created.email, created.id)


def main() -> None:
    """CLI entrypoint for database initialization."""
    settings = get_settings()
    setup_logging(log_level="INFO", json_format=False)

    parser = argparse.ArgumentParser(description="ChildTrack Database Initialization")
    parser.add_argument("--email", default="admin@childtrack.local", help="Admin email address")
    parser.add_argument("--password", default="Admin@12345", help="Admin password (min 8 chars)")
    parser.add_argument("--name", default="System Administrator", help="Admin full name")

    args = parser.parse_args()

    logger.info("Connecting to database: %s", settings.DATABASE_URL.split("@")[-1])
    asyncio.run(init_admin_user(email=args.email, password=args.password, full_name=args.name))
    logger.info("Database initialization complete.")


if __name__ == "__main__":
    main()
