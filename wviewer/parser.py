"""Parser for WiGLE WiFi CSV exports."""
import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import IO

logger = logging.getLogger(__name__)

# Matches filenames like: wigle-2026-04-09T114256.838416809+0000.csv
# Captures the date and HHMMSS parts separately.
_FILENAME_RE = re.compile(r"wigle-(\d{4}-\d{2}-\d{2})T(\d{6})")


@dataclass
class NetworkRecord:
    mac: str
    ssid: str
    auth_mode: str
    first_seen: datetime | None
    channel: int | None
    frequency: int | None
    rssi: int | None
    latitude: float
    longitude: float
    altitude_meters: float | None
    accuracy_meters: float | None
    rcois: str
    mfgr_id: str
    type: str


@dataclass
class ParseResult:
    recon_date: datetime | None
    records: list[NetworkRecord]
    rows_skipped: int


def parse_recon_date(filename: str) -> datetime | None:
    """Extract the ReconDate from a WiGLE CSV filename.

    Filename format: wigle-YYYY-MM-DDTHHMMSS.<frac>+ZZZZ.csv
    Returns a UTC-aware datetime, or None if the filename does not match.
    """
    m = _FILENAME_RE.search(filename)
    if not m:
        logger.warning("Could not parse ReconDate from filename: %s", filename)
        return None
    date_str, time_str = m.group(1), m.group(2)
    try:
        return datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        logger.warning("Invalid date/time in filename: %s", filename)
        return None


def _parse_optional_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_optional_float(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_wigle_csv(fileobj: IO[str], filename: str) -> ParseResult:
    """Parse a WiGLE WiFi CSV file.

    Row 1: app metadata — skipped.
    Row 2: column headers.
    Rows 3+: network data.

    Rows with missing or unparseable latitude/longitude are skipped and counted.
    All other field errors are logged as warnings and the field is set to None/default.
    """
    recon_date = parse_recon_date(filename)
    records: list[NetworkRecord] = []
    rows_skipped = 0

    reader = csv.reader(fileobj)

    # Skip row 1 (app metadata)
    try:
        next(reader)
    except StopIteration:
        return ParseResult(recon_date=recon_date, records=records, rows_skipped=rows_skipped)

    # Row 2: headers — build a column-name → index map
    try:
        raw_headers = next(reader)
    except StopIteration:
        return ParseResult(recon_date=recon_date, records=records, rows_skipped=rows_skipped)

    headers = [h.strip() for h in raw_headers]
    col = {name: idx for idx, name in enumerate(headers)}

    required = {"MAC", "CurrentLatitude", "CurrentLongitude"}
    missing = required - col.keys()
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    for row_num, row in enumerate(reader, start=3):
        if not any(row):
            continue  # skip fully blank rows

        try:
            mac = row[col["MAC"]].strip()
            if not mac:
                rows_skipped += 1
                logger.debug("Row %d skipped: empty MAC", row_num)
                continue

            lat = _parse_optional_float(row[col["CurrentLatitude"]])
            lon = _parse_optional_float(row[col["CurrentLongitude"]])

            if lat is None or lon is None:
                rows_skipped += 1
                logger.warning("Row %d skipped: missing or invalid lat/lon (mac=%s)", row_num, mac)
                continue

            records.append(
                NetworkRecord(
                    mac=mac,
                    ssid=row[col["SSID"]].strip() if "SSID" in col else "",
                    auth_mode=row[col["AuthMode"]].strip() if "AuthMode" in col else "",
                    first_seen=_parse_datetime(row[col["FirstSeen"]]) if "FirstSeen" in col else None,
                    channel=_parse_optional_int(row[col["Channel"]]) if "Channel" in col else None,
                    frequency=_parse_optional_int(row[col["Frequency"]]) if "Frequency" in col else None,
                    rssi=_parse_optional_int(row[col["RSSI"]]) if "RSSI" in col else None,
                    latitude=lat,
                    longitude=lon,
                    altitude_meters=_parse_optional_float(row[col["AltitudeMeters"]]) if "AltitudeMeters" in col else None,
                    accuracy_meters=_parse_optional_float(row[col["AccuracyMeters"]]) if "AccuracyMeters" in col else None,
                    rcois=row[col["RCOIs"]].strip() if "RCOIs" in col else "",
                    mfgr_id=row[col["MfgrId"]].strip() if "MfgrId" in col else "",
                    type=row[col["Type"]].strip() if "Type" in col else "WIFI",
                )
            )
        except IndexError:
            rows_skipped += 1
            logger.warning("Row %d skipped: too few columns", row_num)

    return ParseResult(recon_date=recon_date, records=records, rows_skipped=rows_skipped)
