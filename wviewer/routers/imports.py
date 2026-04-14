"""Import API — POST /api/imports."""
import codecs
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from wviewer.db import get_session
from wviewer.models import Import, Network
from wviewer.parser import parse_wigle_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["imports"])


class ImportResponse(BaseModel):
    import_id: int
    rows_imported: int
    rows_skipped: int


@router.post("", response_model=ImportResponse, status_code=201)
async def create_import(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> ImportResponse:
    """Accept a WiGLE WiFi CSV upload, parse it and store all network records."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    # Read and decode the uploaded file
    raw = await file.read()
    try:
        text = codecs.decode(raw, "utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")

    # Parse CSV
    import io
    parse_result = parse_wigle_csv(io.StringIO(text), file.filename)

    if not parse_result.records and parse_result.rows_skipped == 0:
        # File had no data rows at all — still record the import
        pass

    # Create the Import record
    imp = Import(
        recon_date=parse_result.recon_date,
        imported_at=datetime.now(timezone.utc),
        row_count=0,  # updated below after insert
    )
    session.add(imp)
    await session.flush()  # get imp.id

    rows_imported = 0

    if parse_result.records:
        # Build list of dicts for bulk insert
        values = [
            {
                "import_id": imp.id,
                "mac": rec.mac,
                "ssid": rec.ssid,
                "auth_mode": rec.auth_mode,
                "first_seen": rec.first_seen,
                "channel": rec.channel,
                "frequency": rec.frequency,
                "rssi": rec.rssi,
                "latitude": rec.latitude,
                "longitude": rec.longitude,
                "altitude_meters": rec.altitude_meters,
                "accuracy_meters": rec.accuracy_meters,
                "rcois": rec.rcois,
                "mfgr_id": rec.mfgr_id,
                "type": rec.type,
            }
            for rec in parse_result.records
        ]

        # INSERT OR IGNORE — silently skip rows that violate the (mac, lat, lon) unique constraint
        stmt = sqlite_insert(Network).values(values).on_conflict_do_nothing(
            index_elements=["mac", "latitude", "longitude"]
        )
        result = await session.execute(stmt)
        rows_imported = result.rowcount

    rows_skipped = parse_result.rows_skipped + (len(parse_result.records) - rows_imported)

    # Update the row_count on the Import record
    imp.row_count = rows_imported
    await session.commit()

    return ImportResponse(
        import_id=imp.id,
        rows_imported=rows_imported,
        rows_skipped=rows_skipped,
    )
