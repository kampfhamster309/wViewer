"""Networks API — GET /api/networks."""
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wviewer.db import get_session
from wviewer.models import Network

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/networks", tags=["networks"])


def _build_geojson(networks: list[Network]) -> dict[str, Any]:
    """Wrap a list of Network ORM rows as a GeoJSON FeatureCollection."""
    features = []
    for net in networks:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    # GeoJSON coordinate order is [longitude, latitude]
                    "coordinates": [net.longitude, net.latitude],
                },
                "properties": {
                    "id": net.id,
                    "import_id": net.import_id,
                    "mac": net.mac,
                    "ssid": net.ssid,
                    "auth_mode": net.auth_mode,
                    "first_seen": net.first_seen.isoformat() if net.first_seen else None,
                    "channel": net.channel,
                    "frequency": net.frequency,
                    "rssi": net.rssi,
                    "latitude": net.latitude,
                    "longitude": net.longitude,
                    "altitude_meters": net.altitude_meters,
                    "accuracy_meters": net.accuracy_meters,
                    "rcois": net.rcois,
                    "mfgr_id": net.mfgr_id,
                    "type": net.type,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("")
async def list_networks(
    mac: str | None = Query(default=None, description="Substring match on MAC address"),
    ssid: str | None = Query(default=None, description="Substring match on SSID"),
    auth_mode: str | None = Query(default=None, description="Substring match on AuthMode"),
    type: str | None = Query(default=None, description="Exact match on network type (WIFI, BT, BLE, GSM)"),
    first_seen_from: datetime | None = Query(default=None, description="Filter FirstSeen >= this ISO datetime"),
    first_seen_to: datetime | None = Query(default=None, description="Filter FirstSeen <= this ISO datetime"),
    limit: int = Query(default=1000, ge=1, le=10000, description="Max number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return networks matching the given filters as a GeoJSON FeatureCollection."""
    stmt = select(Network)

    if mac is not None:
        stmt = stmt.where(Network.mac.icontains(mac))
    if ssid is not None:
        stmt = stmt.where(Network.ssid.icontains(ssid))
    if auth_mode is not None:
        stmt = stmt.where(Network.auth_mode.icontains(auth_mode))
    if type is not None:
        stmt = stmt.where(Network.type == type)
    if first_seen_from is not None:
        stmt = stmt.where(Network.first_seen >= first_seen_from)
    if first_seen_to is not None:
        stmt = stmt.where(Network.first_seen <= first_seen_to)

    stmt = stmt.order_by(Network.id).offset(offset).limit(limit)

    result = await session.execute(stmt)
    networks = result.scalars().all()

    return _build_geojson(networks)
