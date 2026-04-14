"""Tests for the WiGLE CSV parser."""
import io
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from wviewer.parser import ParseResult, parse_recon_date, parse_wigle_csv

EXAMPLE_DIR = Path(__file__).parent.parent / "example"

FILE_SMALL = EXAMPLE_DIR / "wigle-2026-04-09T114256.838416809+0000.csv"
FILE_LARGE = EXAMPLE_DIR / "wigle-2026-04-14T115444.484977226+0000.csv"
FILE_EMPTY = EXAMPLE_DIR / "wigle-2026-04-14T134308.354936917+0000.csv"


# ---------------------------------------------------------------------------
# parse_recon_date
# ---------------------------------------------------------------------------

def test_recon_date_parsed_correctly():
    dt = parse_recon_date("wigle-2026-04-09T114256.838416809+0000.csv")
    assert dt == datetime(2026, 4, 9, 11, 42, 56, tzinfo=timezone.utc)


def test_recon_date_second_file():
    dt = parse_recon_date("wigle-2026-04-14T115444.484977226+0000.csv")
    assert dt == datetime(2026, 4, 14, 11, 54, 44, tzinfo=timezone.utc)


def test_recon_date_returns_none_for_unknown_filename():
    assert parse_recon_date("unknown_export.csv") is None


def test_recon_date_returns_none_for_empty_string():
    assert parse_recon_date("") is None


# ---------------------------------------------------------------------------
# Example file: small (66 data rows)
# ---------------------------------------------------------------------------

def test_small_file_row_count():
    result = parse_wigle_csv(FILE_SMALL.open(), FILE_SMALL.name)
    # File has 68 lines total: 1 metadata + 1 header + 66 data rows
    assert len(result.records) == 66
    assert result.rows_skipped == 0


def test_small_file_recon_date():
    result = parse_wigle_csv(FILE_SMALL.open(), FILE_SMALL.name)
    assert result.recon_date == datetime(2026, 4, 9, 11, 42, 56, tzinfo=timezone.utc)


def test_small_file_first_record():
    result = parse_wigle_csv(FILE_SMALL.open(), FILE_SMALL.name)
    rec = result.records[0]
    assert rec.mac == "DC:92:72:58:16:1E"
    assert rec.ssid == "MagentaWLAN-LDCC"
    assert rec.auth_mode == "[WPA3-PSK+SAE-CCMP128 WPA2-PSK+SAE-CCMP128]"
    assert rec.first_seen == datetime(2026, 4, 9, 11, 16, 30, tzinfo=timezone.utc)
    assert rec.channel == 1
    assert rec.frequency == 2412
    assert rec.rssi == -62
    assert rec.latitude == pytest.approx(51.507200634)
    assert rec.longitude == pytest.approx(7.561651556)
    assert rec.type == "WIFI"


def test_small_file_all_records_have_valid_lat_lon():
    result = parse_wigle_csv(FILE_SMALL.open(), FILE_SMALL.name)
    for rec in result.records:
        assert isinstance(rec.latitude, float)
        assert isinstance(rec.longitude, float)


# ---------------------------------------------------------------------------
# Example file: large (~3971 data rows)
# ---------------------------------------------------------------------------

def test_large_file_parses_without_error():
    result = parse_wigle_csv(FILE_LARGE.open(), FILE_LARGE.name)
    assert len(result.records) > 0
    assert result.rows_skipped == 0


def test_large_file_recon_date():
    result = parse_wigle_csv(FILE_LARGE.open(), FILE_LARGE.name)
    assert result.recon_date == datetime(2026, 4, 14, 11, 54, 44, tzinfo=timezone.utc)


def test_large_file_all_records_have_mac():
    result = parse_wigle_csv(FILE_LARGE.open(), FILE_LARGE.name)
    for rec in result.records:
        assert rec.mac


# ---------------------------------------------------------------------------
# Example file: empty (only headers, no data rows)
# ---------------------------------------------------------------------------

def test_empty_file_yields_no_records():
    result = parse_wigle_csv(FILE_EMPTY.open(), FILE_EMPTY.name)
    assert result.records == []
    assert result.rows_skipped == 0


def test_empty_file_recon_date():
    result = parse_wigle_csv(FILE_EMPTY.open(), FILE_EMPTY.name)
    assert result.recon_date == datetime(2026, 4, 14, 13, 43, 8, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Edge cases via synthetic CSV strings
# ---------------------------------------------------------------------------

def _make_csv(data_rows: list[str]) -> io.StringIO:
    header = (
        "WigleWifi-1.6,appRelease=1.0\n"
        "MAC,SSID,AuthMode,FirstSeen,Channel,Frequency,RSSI,"
        "CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,RCOIs,MfgrId,Type\n"
    )
    return io.StringIO(header + "\n".join(data_rows))


def test_row_with_missing_latitude_is_skipped():
    csv_io = _make_csv(['AA:BB:CC:DD:EE:FF,"Net","[WPA2]",2026-01-01 00:00:00,6,2437,-70,,7.0,0,0,,,WIFI'])
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert result.records == []
    assert result.rows_skipped == 1


def test_row_with_missing_longitude_is_skipped():
    csv_io = _make_csv(['AA:BB:CC:DD:EE:FF,"Net","[WPA2]",2026-01-01 00:00:00,6,2437,-70,51.5,,0,0,,,WIFI'])
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert result.records == []
    assert result.rows_skipped == 1


def test_row_with_invalid_lat_is_skipped():
    csv_io = _make_csv(['AA:BB:CC:DD:EE:FF,"Net","[WPA2]",2026-01-01 00:00:00,6,2437,-70,not_a_float,7.0,0,0,,,WIFI'])
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert result.records == []
    assert result.rows_skipped == 1


def test_valid_and_invalid_rows_counted_separately():
    csv_io = _make_csv([
        'AA:BB:CC:DD:EE:FF,"Good","[WPA2]",2026-01-01 00:00:00,6,2437,-70,51.5,7.0,0,0,,,WIFI',
        'BB:CC:DD:EE:FF:00,"Bad","[WPA2]",2026-01-01 00:00:00,6,2437,-70,,7.0,0,0,,,WIFI',
        'CC:DD:EE:FF:00:11,"Good2","[WPA2]",2026-01-01 00:00:00,6,2437,-70,52.0,8.0,0,0,,,WIFI',
    ])
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert len(result.records) == 2
    assert result.rows_skipped == 1


def test_empty_ssid_is_allowed():
    csv_io = _make_csv(['AA:BB:CC:DD:EE:FF,"",[WPA2-PSK],2026-01-01 00:00:00,6,2437,-70,51.5,7.0,0,0,,,WIFI'])
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert len(result.records) == 1
    assert result.records[0].ssid == ""


def test_row_with_empty_mac_is_skipped():
    csv_io = _make_csv([',"EmptyMac","[WPA2]",2026-01-01 00:00:00,6,2437,-70,51.5,7.0,0,0,,,WIFI'])
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert result.records == []
    assert result.rows_skipped == 1


def test_file_with_only_metadata_row():
    csv_io = io.StringIO("WigleWifi-1.6,appRelease=1.0\n")
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert result.records == []
    assert result.rows_skipped == 0


def test_completely_empty_file():
    result = parse_wigle_csv(io.StringIO(""), "wigle-2026-01-01T000000.000+0000.csv")
    assert result.records == []
    assert result.rows_skipped == 0


def test_non_wifi_type_is_stored():
    csv_io = _make_csv(['AA:BB:CC:DD:EE:FF,"BtDevice","[BLE]",2026-01-01 00:00:00,0,0,0,51.5,7.0,0,0,,,BLE'])
    result = parse_wigle_csv(csv_io, "wigle-2026-01-01T000000.000+0000.csv")
    assert len(result.records) == 1
    assert result.records[0].type == "BLE"
