import asyncio
import sys
sys.path.insert(0, '.')
from app.database.session import get_session_factory
from app.schemas.user import UserCreate
from app.models.user import UserRole
from app.services.auth_service import create_user, get_user_by_email

async def main():
    db_context = get_session_factory()()
    async with db_context as db:
        existing = await get_user_by_email(db, 'teacher@childtrack.local')
        if not existing:
            await create_user(db, UserCreate(email='teacher@childtrack.local', password='Teacher@12345', full_name='Demo Teacher', role=UserRole.TEACHER))
            print('Teacher account created successfully.')
        else:
            print('Teacher account already exists.')

if __name__ == '__main__':
    asyncio.run(main())
