"""Networks API — GET /api/networks, GET /api/networks/table."""
import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wviewer.colors import assign_colors
from wviewer.db import get_session
from wviewer.models import Network

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/networks", tags=["networks"])

# Whitelist of columns the table endpoint may sort by.
# Maps query param name → SQLAlchemy column attribute.
_SORTABLE_COLUMNS: dict[str, Any] = {
    "id":               Network.id,
    "mac":              Network.mac,
    "ssid":             Network.ssid,
    "auth_mode":        Network.auth_mode,
    "first_seen":       Network.first_seen,
    "channel":          Network.channel,
    "frequency":        Network.frequency,
    "rssi":             Network.rssi,
    "latitude":         Network.latitude,
    "longitude":        Network.longitude,
    "altitude_meters":  Network.altitude_meters,
    "accuracy_meters":  Network.accuracy_meters,
    "type":             Network.type,
}

_VALID_PAGE_SIZES = {50, 100, 150}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _apply_filters(
    stmt,
    mac: str | None,
    ssid: str | None,
    auth_mode: str | None,
    type_: str | None,
    first_seen_from: datetime | None,
    first_seen_to: datetime | None,
):
    """Apply filter predicates to a SELECT statement and return it."""
    if mac is not None:
        stmt = stmt.where(Network.mac.icontains(mac))
    if ssid is not None:
        stmt = stmt.where(Network.ssid.icontains(ssid))
    if auth_mode is not None:
        stmt = stmt.where(Network.auth_mode.icontains(auth_mode))
    if type_ is not None:
        stmt = stmt.where(Network.type == type_)
    if first_seen_from is not None:
        stmt = stmt.where(Network.first_seen >= first_seen_from)
    if first_seen_to is not None:
        stmt = stmt.where(Network.first_seen <= first_seen_to)
    return stmt


async def _get_multi_location_macs(
    session: AsyncSession, macs: set[str]
) -> set[str]:
    """Return the subset of macs that appear at more than one distinct (lat, lon) in the DB."""
    if not macs:
        return set()
    stmt = (
        select(Network.mac)
        .where(Network.mac.in_(macs))
        .group_by(Network.mac)
        .having(
            func.count(
                func.distinct(
                    func.printf("%s,%s", Network.latitude, Network.longitude)
                )
            ) > 1
        )
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.fetchall()}


def _network_to_dict(net: Network) -> dict[str, Any]:
    """Serialise a Network ORM row to a plain dict."""
    return {
        "id":               net.id,
        "import_id":        net.import_id,
        "mac":              net.mac,
        "ssid":             net.ssid,
        "auth_mode":        net.auth_mode,
        "first_seen":       net.first_seen.isoformat() if net.first_seen else None,
        "channel":          net.channel,
        "frequency":        net.frequency,
        "rssi":             net.rssi,
        "latitude":         net.latitude,
        "longitude":        net.longitude,
        "altitude_meters":  net.altitude_meters,
        "accuracy_meters":  net.accuracy_meters,
        "rcois":            net.rcois,
        "mfgr_id":          net.mfgr_id,
        "type":             net.type,
    }


# ---------------------------------------------------------------------------
# GET /api/networks  — GeoJSON FeatureCollection
# ---------------------------------------------------------------------------

def _build_geojson(
    networks: list[Network], multi_location_macs: set[str]
) -> dict[str, Any]:
    color_map = assign_colors([net.mac for net in networks], multi_location_macs)
    features = []
    for net in networks:
        props = _network_to_dict(net)
        props["marker_color"] = color_map[net.mac]
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [net.longitude, net.latitude],
                },
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("")
async def list_networks(
    mac: str | None = Query(default=None),
    ssid: str | None = Query(default=None),
    auth_mode: str | None = Query(default=None),
    type: str | None = Query(default=None),
    first_seen_from: datetime | None = Query(default=None),
    first_seen_to: datetime | None = Query(default=None),
    limit: int = Query(default=100000, ge=1, le=100000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return networks matching the given filters as a GeoJSON FeatureCollection."""
    stmt = _apply_filters(
        select(Network), mac, ssid, auth_mode, type, first_seen_from, first_seen_to
    )
    stmt = stmt.order_by(Network.id).offset(offset).limit(limit)

    result = await session.execute(stmt)
    networks = result.scalars().all()

    unique_macs = {net.mac for net in networks}
    multi_location_macs = await _get_multi_location_macs(session, unique_macs)

    return _build_geojson(networks, multi_location_macs)


# ---------------------------------------------------------------------------
# GET /api/networks/table  — paginated plain JSON
# ---------------------------------------------------------------------------

class TableResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[dict[str, Any]]


@router.get("/table", response_model=TableResponse)
async def list_networks_table(
    mac: str | None = Query(default=None),
    ssid: str | None = Query(default=None),
    auth_mode: str | None = Query(default=None),
    type: str | None = Query(default=None),
    first_seen_from: datetime | None = Query(default=None),
    first_seen_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=50, description="Rows per page: 50, 100, or 150"),
    sort_by: str = Query(default="id", description=f"Column to sort by: {', '.join(_SORTABLE_COLUMNS)}"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc", description="Sort direction"),
    session: AsyncSession = Depends(get_session),
) -> TableResponse:
    """Return a paginated, sortable plain-JSON page of network records."""
    if page_size not in _VALID_PAGE_SIZES:
        raise HTTPException(
            status_code=422,
            detail=f"page_size must be one of {sorted(_VALID_PAGE_SIZES)}.",
        )
    if sort_by not in _SORTABLE_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"sort_by must be one of: {', '.join(sorted(_SORTABLE_COLUMNS))}.",
        )

    base_stmt = _apply_filters(
        select(Network), mac, ssid, auth_mode, type, first_seen_from, first_seen_to
    )

    # Total count (same filters, no pagination)
    count_stmt = _apply_filters(
        select(func.count()).select_from(Network),
        mac, ssid, auth_mode, type, first_seen_from, first_seen_to,
    )
    total: int = (await session.execute(count_stmt)).scalar_one()

    # Sorted, paginated page
    sort_col = _SORTABLE_COLUMNS[sort_by]
    order_expr = asc(sort_col) if sort_dir == "asc" else desc(sort_col)
    offset = (page - 1) * page_size

    data_stmt = base_stmt.order_by(order_expr).offset(offset).limit(page_size)
    networks = (await session.execute(data_stmt)).scalars().all()

    return TableResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_network_to_dict(net) for net in networks],
    )
