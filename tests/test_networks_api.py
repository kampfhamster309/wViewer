"""Tests for GET /api/networks."""
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
    """Client with the small example file already imported."""
    with FILE_SMALL.open("rb") as f:
        resp = await client.post(
            "/api/imports",
            files={"file": (FILE_SMALL.name, f, "text/csv")},
        )
    assert resp.status_code == 201
    return client


# ---------------------------------------------------------------------------
# GeoJSON structure
# ---------------------------------------------------------------------------

async def test_empty_db_returns_feature_collection(client: AsyncClient):
    response = await client.get("/api/networks")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []


async def test_feature_structure(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks")).json()
    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    # GeoJSON coordinates are [longitude, latitude]
    coords = feature["geometry"]["coordinates"]
    assert len(coords) == 2
    assert isinstance(coords[0], float)  # longitude
    assert isinstance(coords[1], float)  # latitude


async def test_feature_properties_fields(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks")).json()
    props = data["features"][0]["properties"]
    expected_keys = {
        "id", "import_id", "mac", "ssid", "auth_mode", "first_seen",
        "channel", "frequency", "rssi", "latitude", "longitude",
        "altitude_meters", "accuracy_meters", "rcois", "mfgr_id", "type",
    }
    assert expected_keys.issubset(props.keys())


async def test_geojson_coordinate_order(populated_client: AsyncClient):
    """Coordinates must be [longitude, latitude], not [latitude, longitude]."""
    data = (await populated_client.get("/api/networks")).json()
    feature = data["features"][0]
    lon = feature["geometry"]["coordinates"][0]
    lat = feature["geometry"]["coordinates"][1]
    props = feature["properties"]
    assert lon == props["longitude"]
    assert lat == props["latitude"]


async def test_all_small_file_records_returned(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks")).json()
    assert len(data["features"]) == 66


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

async def test_filter_by_mac_exact(populated_client: AsyncClient):
    # 08:02:8E:8F:AF:FF appears at exactly one location in the small file
    data = (await populated_client.get(
        "/api/networks", params={"mac": "08:02:8E:8F:AF:FF"}
    )).json()
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["mac"] == "08:02:8E:8F:AF:FF"


async def test_filter_by_mac_substring(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"mac": "DC:92"}
    )).json()
    assert all("DC:92" in f["properties"]["mac"] for f in data["features"])
    assert len(data["features"]) >= 1


async def test_filter_by_mac_case_insensitive(populated_client: AsyncClient):
    upper = (await populated_client.get("/api/networks", params={"mac": "DC:92:72:58:16:1E"})).json()
    lower = (await populated_client.get("/api/networks", params={"mac": "dc:92:72:58:16:1e"})).json()
    assert len(upper["features"]) == len(lower["features"])


async def test_filter_by_ssid_substring(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"ssid": "Magenta"}
    )).json()
    assert len(data["features"]) >= 1
    assert all("Magenta" in f["properties"]["ssid"] for f in data["features"])


async def test_filter_by_auth_mode_substring(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"auth_mode": "WPA3"}
    )).json()
    assert len(data["features"]) >= 1
    assert all("WPA3" in f["properties"]["auth_mode"] for f in data["features"])


async def test_filter_by_type_exact(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"type": "WIFI"}
    )).json()
    assert len(data["features"]) == 66
    assert all(f["properties"]["type"] == "WIFI" for f in data["features"])


async def test_filter_by_type_no_match(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"type": "BLE"}
    )).json()
    assert data["features"] == []


async def test_filter_by_first_seen_from(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"first_seen_from": "2026-04-09T11:20:00"}
    )).json()
    for feature in data["features"]:
        assert feature["properties"]["first_seen"] >= "2026-04-09T11:20:00"


async def test_filter_by_first_seen_to(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"first_seen_to": "2026-04-09T11:10:00"}
    )).json()
    for feature in data["features"]:
        assert feature["properties"]["first_seen"] <= "2026-04-09T11:10:00"


async def test_filter_by_first_seen_range(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks",
        params={
            "first_seen_from": "2026-04-09T11:15:00",
            "first_seen_to": "2026-04-09T11:16:00",
        },
    )).json()
    assert len(data["features"]) > 0
    for feature in data["features"]:
        ts = feature["properties"]["first_seen"]
        assert "2026-04-09T11:15:00" <= ts <= "2026-04-09T11:16:00"


async def test_combined_filters(populated_client: AsyncClient):
    """mac + auth_mode filters are ANDed together."""
    data = (await populated_client.get(
        "/api/networks",
        params={"mac": "08:02:8E:8F:AF:FF", "auth_mode": "WPA2"},
    )).json()
    # This MAC uses WPA2 — should match both filters and return exactly 1 result
    assert len(data["features"]) == 1


async def test_no_filter_returns_all(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks")).json()
    assert len(data["features"]) == 66


async def test_filter_no_match_returns_empty(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"mac": "ZZ:ZZ:ZZ:ZZ:ZZ:ZZ"}
    )).json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

async def test_limit_reduces_results(populated_client: AsyncClient):
    data = (await populated_client.get("/api/networks", params={"limit": 10})).json()
    assert len(data["features"]) == 10


async def test_offset_skips_results(populated_client: AsyncClient):
    all_data = (await populated_client.get("/api/networks")).json()
    offset_data = (await populated_client.get("/api/networks", params={"offset": 10})).json()
    assert len(offset_data["features"]) == 56
    # First result of offset page matches 11th result of full page
    assert offset_data["features"][0]["properties"]["id"] == all_data["features"][10]["properties"]["id"]


async def test_limit_and_offset_together(populated_client: AsyncClient):
    data = (await populated_client.get(
        "/api/networks", params={"limit": 5, "offset": 10}
    )).json()
    assert len(data["features"]) == 5


async def test_invalid_limit_returns_422(populated_client: AsyncClient):
    response = await populated_client.get("/api/networks", params={"limit": 0})
    assert response.status_code == 422
