"""Tests for the database schema and ORM models."""
import pytest
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.exc import IntegrityError

from wviewer.db import Base
from wviewer.models import Import, Network


@pytest.fixture
async def session():
    """Provide an in-memory SQLite session with the full schema created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def now():
    return datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)


async def test_tables_exist(session: AsyncSession):
    """Both tables must be present after schema creation."""
    result = await session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table'")
    )
    tables = {row[0] for row in result.fetchall()}
    assert "imports" in tables
    assert "networks" in tables


async def test_import_insert(session: AsyncSession, now):
    imp = Import(recon_date=now, imported_at=now, row_count=0)
    session.add(imp)
    await session.commit()
    await session.refresh(imp)
    assert imp.id is not None
    assert imp.row_count == 0


async def test_network_insert(session: AsyncSession, now):
    imp = Import(recon_date=now, imported_at=now, row_count=1)
    session.add(imp)
    await session.flush()

    net = Network(
        import_id=imp.id,
        mac="AA:BB:CC:DD:EE:FF",
        ssid="TestNet",
        auth_mode="[WPA2-PSK-CCMP128]",
        first_seen=now,
        channel=6,
        frequency=2437,
        rssi=-70,
        latitude=51.5072,
        longitude=7.5616,
        altitude_meters=100.0,
        accuracy_meters=5.0,
        type="WIFI",
    )
    session.add(net)
    await session.commit()
    await session.refresh(net)
    assert net.id is not None
    assert net.mac == "AA:BB:CC:DD:EE:FF"


async def test_unique_constraint_mac_lat_lon(session: AsyncSession, now):
    """Inserting the same (mac, lat, lon) twice must raise IntegrityError."""
    imp = Import(recon_date=now, imported_at=now, row_count=2)
    session.add(imp)
    await session.flush()

    def make_net(import_id):
        return Network(
            import_id=import_id,
            mac="AA:BB:CC:DD:EE:FF",
            ssid="TestNet",
            auth_mode="[WPA2-PSK-CCMP128]",
            latitude=51.5072,
            longitude=7.5616,
            type="WIFI",
        )

    session.add(make_net(imp.id))
    await session.flush()

    session.add(make_net(imp.id))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_unique_constraint_allows_different_location(session: AsyncSession, now):
    """Same MAC at a different (lat, lon) must be allowed."""
    imp = Import(recon_date=now, imported_at=now, row_count=2)
    session.add(imp)
    await session.flush()

    session.add(Network(import_id=imp.id, mac="AA:BB:CC:DD:EE:FF", latitude=51.5072, longitude=7.5616, type="WIFI"))
    session.add(Network(import_id=imp.id, mac="AA:BB:CC:DD:EE:FF", latitude=52.0000, longitude=8.0000, type="WIFI"))
    await session.commit()  # must not raise


async def test_import_recon_date_nullable(session: AsyncSession, now):
    """recon_date is nullable (filename may not match expected pattern)."""
    imp = Import(recon_date=None, imported_at=now, row_count=0)
    session.add(imp)
    await session.commit()
    await session.refresh(imp)
    assert imp.recon_date is None
