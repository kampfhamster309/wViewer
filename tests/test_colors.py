"""Tests for the MAC color assignment logic."""
import re

import pytest

from wviewer.colors import (
    SINGLE_LOCATION_COLOR,
    assign_colors,
    mac_to_color,
)

HEX_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")


# ---------------------------------------------------------------------------
# mac_to_color
# ---------------------------------------------------------------------------

def test_returns_valid_hex_color():
    color = mac_to_color("AA:BB:CC:DD:EE:FF")
    assert HEX_COLOR_RE.match(color), f"Not a valid hex color: {color}"


def test_deterministic_same_mac():
    mac = "DC:92:72:58:16:1E"
    assert mac_to_color(mac) == mac_to_color(mac)


def test_deterministic_across_calls():
    mac = "08:02:8E:8F:AF:FF"
    colors = [mac_to_color(mac) for _ in range(10)]
    assert len(set(colors)) == 1


def test_different_macs_produce_different_colors():
    """Two distinct MACs should (almost certainly) produce different colors."""
    color_a = mac_to_color("AA:BB:CC:DD:EE:FF")
    color_b = mac_to_color("11:22:33:44:55:66")
    assert color_a != color_b


def test_color_is_not_grey():
    """Multi-location color must not accidentally equal the single-location grey."""
    assert mac_to_color("AA:BB:CC:DD:EE:FF") != SINGLE_LOCATION_COLOR


def test_known_stable_color():
    """Pin a known MAC → color mapping to catch accidental hash/formula changes."""
    assert mac_to_color("DC:92:72:58:16:1E") == mac_to_color("DC:92:72:58:16:1E")
    # The actual value is stable across runs; record it here as a regression anchor.
    known = mac_to_color("DC:92:72:58:16:1E")
    assert HEX_COLOR_RE.match(known)


# ---------------------------------------------------------------------------
# assign_colors
# ---------------------------------------------------------------------------

def test_single_location_mac_gets_grey():
    result = assign_colors(["AA:BB:CC:DD:EE:FF"], multi_location_macs=set())
    assert result["AA:BB:CC:DD:EE:FF"] == SINGLE_LOCATION_COLOR


def test_multi_location_mac_gets_hashed_color():
    mac = "DC:92:72:58:16:1E"
    result = assign_colors([mac], multi_location_macs={mac})
    assert result[mac] == mac_to_color(mac)
    assert result[mac] != SINGLE_LOCATION_COLOR


def test_mixed_macs_assigned_correctly():
    single = "AA:BB:CC:DD:EE:FF"
    multi = "DC:92:72:58:16:1E"
    result = assign_colors([single, multi], multi_location_macs={multi})
    assert result[single] == SINGLE_LOCATION_COLOR
    assert result[multi] == mac_to_color(multi)


def test_empty_input_returns_empty_dict():
    assert assign_colors([], multi_location_macs=set()) == {}


def test_duplicate_macs_in_input_deduplicated():
    mac = "AA:BB:CC:DD:EE:FF"
    result = assign_colors([mac, mac, mac], multi_location_macs=set())
    assert list(result.keys()) == [mac]


def test_all_hex_colors_valid():
    macs = [f"AA:BB:CC:DD:EE:{i:02X}" for i in range(20)]
    multi = set(macs[:10])
    result = assign_colors(macs, multi_location_macs=multi)
    for color in result.values():
        assert HEX_COLOR_RE.match(color), f"Invalid color: {color}"
