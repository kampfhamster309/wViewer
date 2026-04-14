"""Tests for GET /api/networks/table."""
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from wviewer.app import app
from wviewer.db import Base, get_session

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


@pytest.fixture
async def populated_client(client: AsyncClient):
    with FILE_SMALL.open("rb") as f:
        resp = await client.post(
            "/api/imports",
            files={"file": (FILE_SMALL.name, f, "text/csv")},
        )
    assert resp.status_code == 201
    return client


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

async def test_returns_200(populated_client: AsyncClient):
    r = await populated_client.get("/api/networks/table")
    assert r.status_code == 200


async def test_response_shape(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks/table")).json()
    assert set(data.keys()) == {"total", "page", "page_size", "items"}


async def test_empty_db_returns_zero_total(client: AsyncClient):
    data = (await client.get("/api/networks/table")).json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_total_reflects_full_dataset(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks/table")).json()
    assert data["total"] == 66


async def test_item_fields(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks/table")).json()
    item = data["items"][0]
    expected_keys = {
        "id", "import_id", "mac", "ssid", "auth_mode", "first_seen",
        "channel", "frequency", "rssi", "latitude", "longitude",
        "altitude_meters", "accuracy_meters", "rcois", "mfgr_id", "type",
    }
    assert expected_keys == set(item.keys())


async def test_no_marker_color_in_table_items(populated_client: AsyncClient):
    """marker_color is a map-only concept and must not appear in table items."""
    data = (await populated_client.get("/api/networks/table")).json()
    for item in data["items"]:
        assert "marker_color" not in item


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

async def test_default_page_size_is_50(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks/table")).json()
    assert data["page_size"] == 50
    assert data["page"] == 1
    assert len(data["items"]) == 50


async def test_page_size_100(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks/table", params={"page_size": 100})).json()
    assert len(data["items"]) == 66  # only 66 total, so all returned


async def test_page_size_150(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks/table", params={"page_size": 150})).json()
    assert len(data["items"]) == 66


async def test_invalid_page_size_returns_422(populated_client: AsyncClient):
    r = await populated_client.get("/api/networks/table", params={"page_size": 25})
    assert r.status_code == 422


async def test_page_2_returns_remaining_rows(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"page": 2, "page_size": 50}
    )).json()
    assert data["page"] == 2
    assert len(data["items"]) == 16  # 66 - 50 = 16


async def test_page_beyond_end_returns_empty_items(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"page": 99, "page_size": 50}
    )).json()
    assert data["total"] == 66
    assert data["items"] == []


async def test_pagination_covers_all_rows(populated_client: AsyncClient):
    """Fetching all pages must yield exactly total rows with no duplicates."""
    all_ids = []
    page = 1
    while True:
        data = (await populated_client.get(
            "/api/networks/table", params={"page": page, "page_size": 50}
        )).json()
        all_ids.extend(item["id"] for item in data["items"])
        if len(data["items"]) < 50:
            break
        page += 1
    assert len(all_ids) == 66
    assert len(set(all_ids)) == 66  # no duplicates


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

async def test_default_sort_is_id_asc(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks/table")).json()
    ids = [item["id"] for item in data["items"]]
    assert ids == sorted(ids)


async def test_sort_by_mac_asc(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"sort_by": "mac", "sort_dir": "asc", "page_size": 100}
    )).json()
    macs = [item["mac"] for item in data["items"]]
    assert macs == sorted(macs)


async def test_sort_by_mac_desc(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"sort_by": "mac", "sort_dir": "desc", "page_size": 100}
    )).json()
    macs = [item["mac"] for item in data["items"]]
    assert macs == sorted(macs, reverse=True)


async def test_sort_by_rssi(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"sort_by": "rssi", "sort_dir": "asc", "page_size": 100}
    )).json()
    rssies = [item["rssi"] for item in data["items"] if item["rssi"] is not None]
    assert rssies == sorted(rssies)


async def test_invalid_sort_by_returns_422(populated_client: AsyncClient):
    r = await populated_client.get("/api/networks/table", params={"sort_by": "not_a_column"})
    assert r.status_code == 422


async def test_invalid_sort_dir_returns_422(populated_client: AsyncClient):
    r = await populated_client.get("/api/networks/table", params={"sort_dir": "sideways"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Filters (same params as GeoJSON endpoint)
# ---------------------------------------------------------------------------

async def test_filter_by_mac(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"mac": "08:02:8E:8F:AF:FF", "page_size": 50}
    )).json()
    assert data["total"] == 1
    assert data["items"][0]["mac"] == "08:02:8E:8F:AF:FF"


async def test_filter_by_ssid(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"ssid": "Magenta", "page_size": 50}
    )).json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert "Magenta" in item["ssid"]


async def test_filter_by_auth_mode(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"auth_mode": "WPA3", "page_size": 50}
    )).json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert "WPA3" in item["auth_mode"]


async def test_filter_by_type(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"type": "WIFI", "page_size": 50}
    )).json()
    assert data["total"] == 66


async def test_filter_no_match(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks/table", params={"mac": "ZZ:ZZ:ZZ:ZZ:ZZ:ZZ", "page_size": 50}
    )).json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_total_consistent_across_pages(populated_client: AsyncClient):
    """Total must be the same on every page of the same query."""
    p1 = (await populated_client.get("/api/networks/table", params={"page": 1, "page_size": 50})).json()
    p2 = (await populated_client.get("/api/networks/table", params={"page": 2, "page_size": 50})).json()
    assert p1["total"] == p2["total"]
