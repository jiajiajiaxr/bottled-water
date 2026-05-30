from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

database_url = settings.resolved_database_url
is_sqlite = database_url.startswith("sqlite")
async_connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}

# 替换为异步引擎 URL
# sqlite:/// → sqlite+aiosqlite:///
# postgresql:// → postgresql+asyncpg://
if database_url.startswith("sqlite"):
    async_database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
elif database_url.startswith("postgresql"):
    async_database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
else:
    async_database_url = database_url

async_engine = create_async_engine(
    async_database_url,
    pool_pre_ping=True,
    future=True,
    connect_args=async_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()