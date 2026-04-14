"""Tests for GET /api/imports and DELETE /api/imports/{id}."""
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from wviewer.app import app
from wviewer.db import Base, get_session
from wviewer.models import Import, Network

EXAMPLE_DIR = Path(__file__).parent.parent / "example"
FILE_SMALL = EXAMPLE_DIR / "wigle-2026-04-09T114256.838416809+0000.csv"
FILE_LARGE = EXAMPLE_DIR / "wigle-2026-04-14T115444.484977226+0000.csv"


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _import_file(client: AsyncClient, path: Path) -> dict:
    with path.open("rb") as f:
        resp = await client.post(
            "/api/imports",
            files={"file": (path.name, f, "text/csv")},
        )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/imports
# ---------------------------------------------------------------------------

async def test_list_imports_empty(client: AsyncClient):
    response = await client.get("/api/imports")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_imports_returns_one_record(client: AsyncClient):
    await _import_file(client, FILE_SMALL)
    response = await client.get("/api/imports")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["row_count"] == 66
    assert data[0]["recon_date"] is not None
    assert data[0]["imported_at"] is not None


async def test_list_imports_returns_multiple_records(client: AsyncClient):
    await _import_file(client, FILE_SMALL)
    await _import_file(client, FILE_LARGE)
    response = await client.get("/api/imports")
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_imports_ordered_newest_first(client: AsyncClient):
    first = await _import_file(client, FILE_SMALL)
    second = await _import_file(client, FILE_LARGE)
    response = await client.get("/api/imports")
    data = response.json()
    # Most recently imported appears first
    assert data[0]["id"] == second["import_id"]
    assert data[1]["id"] == first["import_id"]


async def test_list_imports_fields(client: AsyncClient):
    await _import_file(client, FILE_SMALL)
    data = (await client.get("/api/imports")).json()
    record = data[0]
    assert set(record.keys()) == {"id", "recon_date", "imported_at", "row_count"}


# ---------------------------------------------------------------------------
# DELETE /api/imports/{id}
# ---------------------------------------------------------------------------

async def test_delete_import_returns_204(client: AsyncClient):
    result = await _import_file(client, FILE_SMALL)
    response = await client.delete(f"/api/imports/{result['import_id']}")
    assert response.status_code == 204


async def test_delete_import_removes_import_record(client: AsyncClient, db_session: AsyncSession):
    result = await _import_file(client, FILE_SMALL)
    await client.delete(f"/api/imports/{result['import_id']}")

    remaining = (await db_session.execute(select(Import))).scalars().all()
    assert remaining == []


async def test_delete_import_does_not_remove_networks(client: AsyncClient, db_session: AsyncSession):
    """Network rows must survive import deletion — they are shared across imports."""
    result = await _import_file(client, FILE_SMALL)
    await client.delete(f"/api/imports/{result['import_id']}")

    networks = (await db_session.execute(select(Network))).scalars().all()
    assert len(networks) == 66


async def test_delete_nonexistent_import_returns_404(client: AsyncClient):
    response = await client.delete("/api/imports/999")
    assert response.status_code == 404


async def test_delete_leaves_other_imports_intact(client: AsyncClient, db_session: AsyncSession):
    first = await _import_file(client, FILE_SMALL)
    second = await _import_file(client, FILE_LARGE)

    await client.delete(f"/api/imports/{first['import_id']}")

    remaining = (await db_session.execute(select(Import))).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id == second["import_id"]


async def test_list_imports_after_delete_is_updated(client: AsyncClient):
    result = await _import_file(client, FILE_SMALL)
    await client.delete(f"/api/imports/{result['import_id']}")

    response = await client.get("/api/imports")
    assert response.json() == []
