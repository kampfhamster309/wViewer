"""Integration smoke tests: import → query → verify GeoJSON output.

One end-to-end scenario per example CSV, plus cross-import and filter
coverage. These tests exercise the full request stack against an
in-memory SQLite database.
"""
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from wviewer.app import app
from wviewer.colors import SINGLE_LOCATION_COLOR
from wviewer.db import Base, get_session

EXAMPLE_DIR = Path(__file__).parent.parent / "example"
FILE_SMALL = EXAMPLE_DIR / "wigle-2026-04-09T114256.838416809+0000.csv"
FILE_LARGE = EXAMPLE_DIR / "wigle-2026-04-14T115444.484977226+0000.csv"
FILE_EMPTY = EXAMPLE_DIR / "wigle-2026-04-14T134308.354936917+0000.csv"

# ---- Known facts about the example files ----
SMALL_ROW_COUNT  = 66
LARGE_ROW_COUNT  = 3971

# DC:92:72:58:16:1E appears at two distinct locations inside the small file
SMALL_MULTI_MAC  = "DC:92:72:58:16:1E"
# 08:02:8E:8F:AF:FF appears at exactly one location in the small file
SMALL_SINGLE_MAC = "08:02:8E:8F:AF:FF"
# 00:05:FE:C9:68:24 appears at multiple distinct locations inside the large file
LARGE_MULTI_MAC  = "00:05:FE:C9:68:24"
# DC:92:72:58:16:1E also appears in the large file at a different coordinate
# → after both files are imported it must have a non-grey marker
CROSS_MAC        = "DC:92:72:58:16:1E"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def do_import(client: AsyncClient, path: Path) -> dict:
    with path.open("rb") as f:
        r = await client.post(
            "/api/imports",
            files={"file": (path.name, f, "text/csv")},
        )
    assert r.status_code == 201
    return r.json()


async def geojson(client: AsyncClient, **params) -> dict:
    r = await client.get("/api/networks", params={"limit": 100000, **params})
    assert r.status_code == 200
    return r.json()


def feature_macs(gj: dict) -> set[str]:
    return {f["properties"]["mac"] for f in gj["features"]}


def colors_for_mac(gj: dict, mac: str) -> set[str]:
    return {
        f["properties"]["marker_color"]
        for f in gj["features"]
        if f["properties"]["mac"] == mac
    }


# ---------------------------------------------------------------------------
# Small file
# ---------------------------------------------------------------------------

async def test_small_import_count(client: AsyncClient):
    result = await do_import(client, FILE_SMALL)
    assert result["rows_imported"] == SMALL_ROW_COUNT
    assert result["rows_skipped"] == 0


async def test_small_query_feature_count(client: AsyncClient):
    await do_import(client, FILE_SMALL)
    gj = await geojson(client)
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == SMALL_ROW_COUNT


async def test_small_known_macs_present(client: AsyncClient):
    await do_import(client, FILE_SMALL)
    macs = feature_macs(await geojson(client))
    assert SMALL_MULTI_MAC in macs
    assert SMALL_SINGLE_MAC in macs


async def test_small_feature_structure(client: AsyncClient):
    """Every GeoJSON feature must have Point geometry and a marker_color property."""
    await do_import(client, FILE_SMALL)
    for feature in (await geojson(client))["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        lon, lat = feature["geometry"]["coordinates"]
        assert isinstance(lon, float) and isinstance(lat, float)
        props = feature["properties"]
        assert "mac" in props
        assert props.get("marker_color", "").startswith("#")


async def test_small_multi_location_mac_not_grey(client: AsyncClient):
    """DC:92:72:58:16:1E is at 2 locations in the small file → must not be grey."""
    await do_import(client, FILE_SMALL)
    colors = colors_for_mac(await geojson(client), SMALL_MULTI_MAC)
    assert colors, "MAC not found in results"
    assert SINGLE_LOCATION_COLOR not in colors


async def test_small_single_location_mac_is_grey(client: AsyncClient):
    """08:02:8E:8F:AF:FF is at exactly one location → must be grey."""
    await do_import(client, FILE_SMALL)
    colors = colors_for_mac(await geojson(client), SMALL_SINGLE_MAC)
    assert colors, "MAC not found in results"
    assert colors == {SINGLE_LOCATION_COLOR}


async def test_small_recon_date_parsed_from_filename(client: AsyncClient):
    """recon_date on the import record should match the filename timestamp."""
    await do_import(client, FILE_SMALL)
    imports = (await client.get("/api/imports")).json()
    assert len(imports) == 1
    assert imports[0]["recon_date"].startswith("2026-04-09")


# ---------------------------------------------------------------------------
# Large file
# ---------------------------------------------------------------------------

async def test_large_import_count(client: AsyncClient):
    result = await do_import(client, FILE_LARGE)
    assert result["rows_imported"] == LARGE_ROW_COUNT
    assert result["rows_skipped"] == 0


async def test_large_query_feature_count(client: AsyncClient):
    await do_import(client, FILE_LARGE)
    gj = await geojson(client)
    assert len(gj["features"]) == LARGE_ROW_COUNT


async def test_large_multi_location_mac_not_grey(client: AsyncClient):
    """00:05:FE:C9:68:24 appears at multiple locations in the large file."""
    await do_import(client, FILE_LARGE)
    colors = colors_for_mac(await geojson(client), LARGE_MULTI_MAC)
    assert colors, "MAC not found in results"
    assert SINGLE_LOCATION_COLOR not in colors


# ---------------------------------------------------------------------------
# Empty file
# ---------------------------------------------------------------------------

async def test_empty_import_zero_rows(client: AsyncClient):
    result = await do_import(client, FILE_EMPTY)
    assert result["rows_imported"] == 0
    assert result["rows_skipped"] == 0


async def test_empty_query_returns_no_features(client: AsyncClient):
    await do_import(client, FILE_EMPTY)
    gj = await geojson(client)
    assert gj["type"] == "FeatureCollection"
    assert gj["features"] == []


# ---------------------------------------------------------------------------
# Cross-import: small + large together
# ---------------------------------------------------------------------------

async def test_cross_import_macs_from_both_files_present(client: AsyncClient):
    """After importing both files all known MACs are queryable."""
    await do_import(client, FILE_SMALL)
    await do_import(client, FILE_LARGE)
    macs = feature_macs(await geojson(client))
    assert SMALL_SINGLE_MAC in macs
    assert LARGE_MULTI_MAC in macs


async def test_cross_import_total_exceeds_large_alone(client: AsyncClient):
    """Adding the small file to the large one must increase the total feature count."""
    await do_import(client, FILE_LARGE)
    count_large = len((await geojson(client))["features"])

    await do_import(client, FILE_SMALL)
    count_both = len((await geojson(client))["features"])

    assert count_both > count_large


async def test_cross_import_shared_mac_is_multi_location(client: AsyncClient):
    """DC:92:72:58:16:1E appears in both files at different coords → non-grey."""
    await do_import(client, FILE_SMALL)
    await do_import(client, FILE_LARGE)
    colors = colors_for_mac(await geojson(client), CROSS_MAC)
    assert colors, "MAC not found in results"
    assert SINGLE_LOCATION_COLOR not in colors


# ---------------------------------------------------------------------------
# Filter end-to-end (small file)
# ---------------------------------------------------------------------------

async def test_filter_ssid_substring(client: AsyncClient):
    await do_import(client, FILE_SMALL)
    gj = await geojson(client, ssid="Magenta")
    assert len(gj["features"]) >= 1
    for f in gj["features"]:
        assert "Magenta" in f["properties"]["ssid"]


async def test_filter_type_bt_returns_empty_for_wifi_file(client: AsyncClient):
    """The example files contain only WIFI records — BT filter must yield nothing."""
    await do_import(client, FILE_SMALL)
    gj = await geojson(client, type="BT")
    assert gj["features"] == []


async def test_filter_exact_mac(client: AsyncClient):
    await do_import(client, FILE_SMALL)
    gj = await geojson(client, mac=SMALL_SINGLE_MAC)
    assert len(gj["features"]) == 1
    assert gj["features"][0]["properties"]["mac"] == SMALL_SINGLE_MAC


async def test_filter_auth_mode_substring(client: AsyncClient):
    await do_import(client, FILE_SMALL)
    gj = await geojson(client, auth_mode="WPA3")
    assert len(gj["features"]) >= 1
    for f in gj["features"]:
        assert "WPA3" in f["properties"]["auth_mode"]


async def test_filter_no_match_returns_empty(client: AsyncClient):
    await do_import(client, FILE_SMALL)
    gj = await geojson(client, mac="ZZ:ZZ:ZZ:ZZ:ZZ:ZZ")
    assert gj["features"] == []
