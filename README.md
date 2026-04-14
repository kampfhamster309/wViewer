# wViewer

A local desktop app for importing, storing, and visualising [WiGLE](https://wigle.net/) WiFi wardriving CSV exports on an interactive map.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` or see uv install docs)

## Running locally

```bash
# Install dependencies
uv sync

# Apply database migrations
uv run alembic upgrade head

# Start the app (opens browser automatically)
uv run wviewer
```

The app will be available at `http://localhost:8000`.

### Options

```
uv run wviewer --port 9000     # use a different port
uv run wviewer --no-browser    # don't open the browser automatically
```

## Port configuration

### Installed package (.deb)

The default port is **8000**. To change it, edit `/etc/default/wviewer`:

```sh
sudo nano /etc/default/wviewer
```

Set your preferred port:

```sh
WVIEWER_PORT=9000
```

The change takes effect the next time you launch wViewer from the app launcher. The file is marked as a Debian conffile, so package upgrades will never overwrite your custom value.

### Running from source

Pass `--port` directly:

```
uv run wviewer --port 9000
```

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest
```

## Usage

1. Click **Import** in the sidebar and select a WiGLE WiFi CSV file
2. Use the filter controls to narrow down results by MAC, SSID, AuthMode, or date
3. Press **Apply** to render matching networks on the map
4. Click any marker for full record details

Switch to the **Table** tab to browse results in a paginated table:

- Click any column header to sort ascending; click again to sort descending
- Use the page-size selector (50 / 100 / 150 rows) and prev/next controls to paginate
- Press **Export CSV** to download the full filtered result set as a CSV file
- Press **Map** on any row to jump to that network on the map view

## License

Apache 2.0 — see [LICENSE](LICENSE).
