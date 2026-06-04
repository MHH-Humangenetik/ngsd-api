from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, cast
from sqlalchemy.ext.asyncio import AsyncConnection

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import NgsdSettings
from .types import Run, RunStatus


class NgsdApi:
    """Async API client for the NGSD MariaDB database."""

    def __init__(self, settings: NgsdSettings) -> None:
        self._settings = settings
        dsn = f"mysql+aiomysql://{settings.user}:{settings.password}@{settings.host}:{settings.port}/{settings.database}"
        self._engine = create_async_engine(dsn, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._pool_connection: AsyncConnection | None = None

    async def __aenter__(self) -> "NgsdApi":
        self._pool_connection = await self._engine.connect()
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._pool_connection is not None:
            await self._pool_connection.close()
        await self._engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide a transactional scope for database operations."""
        async with self._session_factory() as session:
            yield session

    async def get_runs_by_processing_system(
        self, processing_system_name: str, status: RunStatus | None = None
    ) -> list[Run]:
        """Fetch runs filtered by processing system and optionally by status."""
        sql_parts = [
            "SELECT DISTINCT sr.name, sr.status",
            "FROM sequencing_run sr",
            "INNER JOIN processed_sample ps ON ps.sequencing_run_id = sr.id",
            "INNER JOIN processing_system pss ON pss.id = ps.processing_system_id",
            "WHERE pss.name_short = :processing_system",
        ]
        params: dict[str, str] = {"processing_system": processing_system_name}
        if status is not None:
            sql_parts.append("AND sr.status = :status")
            params["status"] = status.value
        sql = " ".join(sql_parts)
        async with self.session() as session:
            result = await session.execute(sa.text(sql), params)
            rows = result.fetchall()
            return [Run(name=row[0], status=RunStatus(row[1])) for row in rows]

    async def set_run_status_by_name(self, runname: str, status: RunStatus) -> bool:
        """Update the status of a run by name."""
        sql = "UPDATE sequencing_run SET status = :status WHERE name = :name"
        async with self.session() as session:
            result = await session.execute(sa.text(sql), {"name": runname, "status": status.value})
            await session.commit()
            cursor_result = cast(CursorResult[Any], result)
            return cursor_result.rowcount > 0
