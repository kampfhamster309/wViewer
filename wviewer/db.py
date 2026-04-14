import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


def _db_path() -> Path:
    """Return the database file path.

    When installed as a .deb the wrapper script sets WVIEWER_DB to a
    user-writable location (~/.local/share/wviewer/wviewer.db).
    When running from source the database sits at the project root.
    """
    env = os.environ.get("WVIEWER_DB")
    if env:
        return Path(env)
    return Path(__file__).parent.parent / "wviewer.db"


_DB_PATH = _db_path()
DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

# NullPool: no connection caching. Each request gets a fresh connection that
# is closed immediately after use. This avoids stale-connection errors when
# the engine is shared across asyncio event loops (e.g. __main__ setup vs
# uvicorn's loop) and is perfectly fine for a single-user local SQLite app.
engine = create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
