"""Deterministic marker color assignment for network MACs.

Single-location MACs (seen at only one lat/lon in the DB) get a neutral grey.
Multi-location MACs each get a stable, visually distinct color derived by
hashing the MAC address into an HSL value and converting to hex.
"""
import colorsys
import hashlib

# Neutral color for MACs seen at a single location
SINGLE_LOCATION_COLOR = "#909090"

# HSL parameters for multi-location MAC colors
_SATURATION = 0.70
_LIGHTNESS = 0.45


def mac_to_color(mac: str) -> str:
    """Return a stable hex color for a multi-location MAC.

    Uses SHA-256 of the MAC string to derive a hue in [0, 360), then
    converts HSL(hue, 70%, 45%) to a hex color string.
    The result is deterministic: the same MAC always produces the same color.
    """
    digest = hashlib.sha256(mac.encode()).digest()
    # Use the first two bytes for an evenly distributed hue
    hue_int = (digest[0] << 8 | digest[1]) % 360
    hue = hue_int / 360.0

    # colorsys uses HLS order (hue, lightness, saturation)
    r, g, b = colorsys.hls_to_rgb(hue, _LIGHTNESS, _SATURATION)

    return "#{:02x}{:02x}{:02x}".format(
        round(r * 255), round(g * 255), round(b * 255)
    )


def assign_colors(
    networks: list[str], multi_location_macs: set[str]
) -> dict[str, str]:
    """Return a MAC → hex color mapping for a list of MAC addresses.

    Args:
        networks: iterable of MAC address strings to assign colors for.
        multi_location_macs: set of MACs known to appear at more than one location.

    Returns:
        dict mapping each unique MAC to its hex color string.
    """
    return {
        mac: (mac_to_color(mac) if mac in multi_location_macs else SINGLE_LOCATION_COLOR)
        for mac in set(networks)
    }
