"""Seed platform admin user for initial deployment."""

import asyncio
import uuid

from sqlalchemy import select

from ai_spm.domain.enums import PlatformRole
from ai_spm.domain.models import PlatformUser
from ai_spm.infrastructure.auth.password import hash_password
from ai_spm.infrastructure.db.session import async_session_factory, get_platform_session


async def seed() -> None:
    email = "platform-admin@aispm.io"
    password = "PlatformAdmin123!"

    async with get_platform_session() as session:
        existing = await session.execute(select(PlatformUser).where(PlatformUser.email == email))
        if existing.scalar_one_or_none():
            print(f"Platform admin {email} already exists")
            return

        session.add(
            PlatformUser(
                id=uuid.uuid4(),
                email=email,
                password_hash=hash_password(password),
                full_name="Platform Administrator",
                role=PlatformRole.PLATFORM_SUPER,
                is_active=True,
            )
        )
        await session.commit()
        print(f"Created platform admin: {email} / {password}")


if __name__ == "__main__":
    asyncio.run(seed())
