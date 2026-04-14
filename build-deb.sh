#!/usr/bin/env bash
# Build a self-contained .deb package for wViewer.
#
# Requirements (all present on a standard Ubuntu 24.04 dev machine):
#   uv        — already used for development
#   dpkg-deb  — part of the dpkg package (always installed on Debian/Ubuntu)
#
# Usage:
#   bash build-deb.sh
#
# Output: wviewer_<version>_amd64.deb in the project root.

set -euo pipefail

PKG="wviewer"
VERSION=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    print(tomllib.load(f)['project']['version'])
")
ARCH="amd64"

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

VENV="$WORK_DIR/venv"
STAGING="$WORK_DIR/staging"

echo "==> Building ${PKG}_${VERSION}_${ARCH}.deb"

# ── 1. Install app + dependencies into a temporary virtualenv ──────────────
echo "  Installing into temporary venv…"
uv venv "$VENV" -q
uv pip install --python "$VENV" . -q

# Detect the Python version used inside the venv
PY_VER=$("$VENV/bin/python3" -c \
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
SITE_PKGS="$VENV/lib/python${PY_VER}/site-packages"

# ── 2. Build the staging directory tree ───────────────────────────────────
echo "  Assembling package tree…"
install -d "$STAGING/DEBIAN"
install -d "$STAGING/usr/bin"
install -d "$STAGING/usr/lib/$PKG"
install -d "$STAGING/usr/share/applications"
install -d "$STAGING/etc/default"

# Copy site-packages; strip pip/setuptools/wheel — not needed at runtime
cp -r "$SITE_PKGS" "$STAGING/usr/lib/$PKG/lib"
for _pkg in pip pip-* setuptools setuptools-* wheel wheel-* \
            pkg_resources _distutils_hack distutils-*.dist-info; do
    rm -rf "${STAGING}/usr/lib/${PKG}/lib/${_pkg}" 2>/dev/null || true
done

# ── 3. Wrapper script (/usr/bin/wviewer) ──────────────────────────────────
cat > "$STAGING/usr/bin/$PKG" << 'WRAPPER'
#!/bin/bash
set -e

# Load port (and any future settings) from the conffile
[ -f /etc/default/wviewer ] && . /etc/default/wviewer
: "${WVIEWER_PORT:=8000}"

# Per-user data directory (XDG-compliant)
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wviewer"
mkdir -p "$DATA_DIR"

export PYTHONPATH="/usr/lib/wviewer/lib${PYTHONPATH:+:$PYTHONPATH}"
export WVIEWER_DB="$DATA_DIR/wviewer.db"

exec python3 -m wviewer --port "$WVIEWER_PORT" "$@"
WRAPPER
chmod 755 "$STAGING/usr/bin/$PKG"

# ── 4. Default configuration conffile ─────────────────────────────────────
cat > "$STAGING/etc/default/$PKG" << 'CONF'
# wViewer configuration
#
# Change WVIEWER_PORT if port 8000 is already occupied on your machine.
# The new value takes effect the next time wViewer is launched.
WVIEWER_PORT=8000
CONF

# ── 5. .desktop file ──────────────────────────────────────────────────────
cp "debian/$PKG.desktop" "$STAGING/usr/share/applications/"

# ── 6. DEBIAN/control ─────────────────────────────────────────────────────
cat > "$STAGING/DEBIAN/control" << EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.11), xdg-utils
Maintainer: Felix Harenbrock
Description: WiGLE WiFi wardriving CSV viewer
 A local desktop application for importing, storing, and visualising
 WiGLE WiFi wardriving CSV exports on an interactive Leaflet.js map.
 .
 Supports filtering by MAC, SSID, AuthMode, and date range. Results
 are rendered on a Leaflet.js map with per-MAC colour coding for
 networks observed at multiple locations. Includes a sortable, paginated
 table view with CSV export.
EOF

# ── 7. DEBIAN/conffiles (protects /etc/default/wviewer on upgrade) ────────
echo "/etc/default/$PKG" > "$STAGING/DEBIAN/conffiles"

# ── 8. Build the .deb ─────────────────────────────────────────────────────
OUTPUT="${PKG}_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$STAGING" "$OUTPUT"

echo ""
echo "Done: $OUTPUT"
echo ""
echo "Install with:  sudo dpkg -i $OUTPUT"
echo "Uninstall with: sudo dpkg -r $PKG"
