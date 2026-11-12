"""Async engine and session management."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Owns the async engine for one database URL.

    ``hide_parameters`` keeps bound values out of error messages, and SQLAlchemy masks the
    password in URL representations, so credentials never reach logs.
    """

    def __init__(self, url: str, *, connect_timeout_s: float = 5.0) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"timeout": connect_timeout_s},
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def ping(self) -> float:
        """Execute ``SELECT 1``; return the round-trip latency in milliseconds."""
        start = time.perf_counter()
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return round((time.perf_counter() - start) * 1000, 3)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
