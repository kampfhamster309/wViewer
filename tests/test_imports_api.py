"""Tests for POST /api/imports."""
import io
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
FILE_EMPTY = EXAMPLE_DIR / "wigle-2026-04-14T134308.354936917+0000.csv"


@pytest.fixture
async def db_session():
    """In-memory SQLite database with schema applied."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    """AsyncClient with the session dependency overridden to use the test DB."""
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_import_small_file(client: AsyncClient):
    with FILE_SMALL.open("rb") as f:
        response = await client.post(
            "/api/imports",
            files={"file": (FILE_SMALL.name, f, "text/csv")},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["import_id"] == 1
    assert data["rows_imported"] == 66
    assert data["rows_skipped"] == 0


async def test_import_empty_file(client: AsyncClient):
    """File with no data rows should succeed and import 0 rows."""
    with FILE_EMPTY.open("rb") as f:
        response = await client.post(
            "/api/imports",
            files={"file": (FILE_EMPTY.name, f, "text/csv")},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["rows_imported"] == 0
    assert data["rows_skipped"] == 0


async def test_import_creates_import_record(client: AsyncClient, db_session: AsyncSession):
    with FILE_SMALL.open("rb") as f:
        await client.post(
            "/api/imports",
            files={"file": (FILE_SMALL.name, f, "text/csv")},
        )
    result = await db_session.execute(select(Import))
    imports = result.scalars().all()
    assert len(imports) == 1
    assert imports[0].row_count == 66
    assert imports[0].recon_date is not None


async def test_import_creates_network_rows(client: AsyncClient, db_session: AsyncSession):
    with FILE_SMALL.open("rb") as f:
        await client.post(
            "/api/imports",
            files={"file": (FILE_SMALL.name, f, "text/csv")},
        )
    result = await db_session.execute(select(Network))
    networks = result.scalars().all()
    assert len(networks) == 66


async def test_import_large_file(client: AsyncClient):
    with FILE_LARGE.open("rb") as f:
        response = await client.post(
            "/api/imports",
            files={"file": (FILE_LARGE.name, f, "text/csv")},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["rows_imported"] > 0
    assert data["rows_skipped"] == 0


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

async def test_reimport_same_file_deduplicates(client: AsyncClient):
    """Importing the same file twice should insert 0 new rows on the second import."""
    for _ in range(2):
        with FILE_SMALL.open("rb") as f:
            response = await client.post(
                "/api/imports",
                files={"file": (FILE_SMALL.name, f, "text/csv")},
            )
        assert response.status_code == 201

    data = response.json()
    assert data["rows_imported"] == 0
    assert data["rows_skipped"] == 66  # all 66 rows were duplicates


async def test_reimport_network_count_unchanged(client: AsyncClient, db_session: AsyncSession):
    """The networks table should not grow after a duplicate import."""
    for _ in range(2):
        with FILE_SMALL.open("rb") as f:
            await client.post(
                "/api/imports",
                files={"file": (FILE_SMALL.name, f, "text/csv")},
            )
    result = await db_session.execute(select(Network))
    assert len(result.scalars().all()) == 66


async def test_two_imports_create_two_import_records(client: AsyncClient, db_session: AsyncSession):
    """Each import call always creates an Import record, even if all rows are dupes."""
    for _ in range(2):
        with FILE_SMALL.open("rb") as f:
            await client.post(
                "/api/imports",
                files={"file": (FILE_SMALL.name, f, "text/csv")},
            )
    result = await db_session.execute(select(Import))
    assert len(result.scalars().all()) == 2


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

async def test_upload_without_file_returns_422(client: AsyncClient):
    response = await client.post("/api/imports")
    assert response.status_code == 422


async def test_upload_invalid_utf8_returns_400(client: AsyncClient):
    bad_bytes = b"\xff\xfe invalid bytes"
    response = await client.post(
        "/api/imports",
        files={"file": ("bad.csv", io.BytesIO(bad_bytes), "text/csv")},
    )
    assert response.status_code == 400


async def test_upload_missing_filename_returns_error(client: AsyncClient):
    """An empty filename is rejected — FastAPI returns 422 at the validation layer."""
    response = await client.post(
        "/api/imports",
        files={"file": ("", io.BytesIO(b"data"), "text/csv")},
    )
    assert response.status_code == 422


async def test_upload_non_csv_extension_returns_400(client: AsyncClient):
    """Files with a non-.csv extension are rejected before any parsing."""
    response = await client.post(
        "/api/imports",
        files={"file": ("export.txt", io.BytesIO(b"some,data\n"), "text/plain")},
    )
    assert response.status_code == 400
    assert "csv" in response.json()["detail"].lower()


async def test_upload_json_extension_returns_400(client: AsyncClient):
    response = await client.post(
        "/api/imports",
        files={"file": ("data.json", io.BytesIO(b'{"key": "val"}'), "application/json")},
    )
    assert response.status_code == 400


async def test_error_response_has_detail_key(client: AsyncClient):
    """All error responses must carry a 'detail' key for consistent frontend handling."""
    response = await client.post(
        "/api/imports",
        files={"file": ("export.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert "detail" in response.json()
