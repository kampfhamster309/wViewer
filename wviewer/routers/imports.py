"""Import API — POST /api/imports, GET /api/imports, DELETE /api/imports/{id}."""
import codecs
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
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


class ImportRecord(BaseModel):
    id: int
    recon_date: datetime | None
    imported_at: datetime
    row_count: int

    model_config = {"from_attributes": True}


@router.post("", response_model=ImportResponse, status_code=201)
async def create_import(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> ImportResponse:
    """Accept a WiGLE WiFi CSV upload, parse it and store all network records."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    # Read and decode the uploaded file
    raw = await file.read()
    try:
        text = codecs.decode(raw, "utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")

    # Parse CSV
    try:
        parse_result = parse_wigle_csv(io.StringIO(text), file.filename)
    except Exception as exc:
        logger.exception("Unexpected error parsing '%s'", file.filename)
        raise HTTPException(
            status_code=422, detail=f"Could not parse file: {exc}"
        ) from exc

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


@router.get("", response_model=list[ImportRecord])
async def list_imports(
    session: AsyncSession = Depends(get_session),
) -> list[ImportRecord]:
    """Return all import records ordered by imported_at descending."""
    result = await session.execute(
        select(Import).order_by(Import.imported_at.desc())
    )
    return result.scalars().all()


@router.delete("/{import_id}", status_code=204)
async def delete_import(
    import_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an import record.

    Network rows are NOT deleted — they are deduplicated across imports
    and do not belong exclusively to a single import batch.
    """
    result = await session.execute(select(Import).where(Import.id == import_id))
    imp = result.scalar_one_or_none()
    if imp is None:
        raise HTTPException(status_code=404, detail=f"Import {import_id} not found.")
    await session.delete(imp)
    await session.commit()
