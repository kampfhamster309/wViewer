/* wViewer — main application script
 *
 * Initialises the Leaflet map and wires up the sidebar controls.
 * Map starts empty; results are only fetched when the user presses Apply.
 */

// ===== Map setup =====

const map = L.map('map', {
  center: [51.505, 10.09],  // centre of Germany — sensible default
  zoom: 6,
  zoomControl: true,
});

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

let markerClusterGroup = L.markerClusterGroup();
map.addLayer(markerClusterGroup);

// ===== localStorage helpers =====

const STORAGE_KEY = 'wviewer_filters';

function saveFilters() {
  const filters = {
    mac:      document.getElementById('filter-mac').value,
    ssid:     document.getElementById('filter-ssid').value,
    auth:     document.getElementById('filter-auth').value,
    type:     document.getElementById('filter-type').value,
    from:     document.getElementById('filter-from').value,
    to:       document.getElementById('filter-to').value,
    preset:   document.querySelector('.preset-btn.active')?.dataset.hours ?? '',
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
}

function loadFilters() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const f = JSON.parse(raw);
    document.getElementById('filter-mac').value  = f.mac  ?? '';
    document.getElementById('filter-ssid').value = f.ssid ?? '';
    document.getElementById('filter-auth').value = f.auth ?? '';
    document.getElementById('filter-type').value = f.type ?? '';
    document.getElementById('filter-from').value = f.from ?? '';
    document.getElementById('filter-to').value   = f.to   ?? '';
    if (f.preset) {
      document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.hours === f.preset);
      });
    }
  } catch (_) { /* ignore corrupt storage */ }
}

// ===== Relative date presets =====

document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const hours = btn.dataset.hours;

    // Clear active state from all presets
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));

    if (!hours) {
      // "All" button — clear date range
      document.getElementById('filter-from').value = '';
      document.getElementById('filter-to').value   = '';
    } else {
      btn.classList.add('active');
      const to   = new Date();
      const from = new Date(to.getTime() - parseInt(hours, 10) * 3600 * 1000);
      document.getElementById('filter-from').value = toLocalDatetimeInput(from);
      document.getElementById('filter-to').value   = toLocalDatetimeInput(to);
    }
    saveFilters();
  });
});

// Clear preset highlight when user manually edits the date inputs
['filter-from', 'filter-to'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    saveFilters();
  });
});

/** Convert a Date to the value format expected by datetime-local inputs (YYYY-MM-DDTHH:MM). */
function toLocalDatetimeInput(date) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
         `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// Persist filter changes as the user types
['filter-mac', 'filter-ssid', 'filter-auth', 'filter-type'].forEach(id => {
  document.getElementById(id).addEventListener('input', saveFilters);
});

// ===== Apply button =====

document.getElementById('btn-apply').addEventListener('click', applyFilters);

async function applyFilters() {
  const params = new URLSearchParams();

  const mac  = document.getElementById('filter-mac').value.trim();
  const ssid = document.getElementById('filter-ssid').value.trim();
  const auth = document.getElementById('filter-auth').value.trim();
  const type = document.getElementById('filter-type').value;
  const from = document.getElementById('filter-from').value;
  const to   = document.getElementById('filter-to').value;

  if (mac)  params.set('mac', mac);
  if (ssid) params.set('ssid', ssid);
  if (auth) params.set('auth_mode', auth);
  if (type) params.set('type', type);
  if (from) params.set('first_seen_from', from);
  if (to)   params.set('first_seen_to', to);

  saveFilters();
  setFilterStatus('<span class="spinner"></span>Loading…', 'info');

  try {
    const res = await fetch(`/api/networks?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const geojson = await res.json();
    renderMarkers(geojson);
    const count = geojson.features.length;
    setFilterStatus(`${count} network${count !== 1 ? 's' : ''} found.`, 'ok');
  } catch (err) {
    setFilterStatus(`Error: ${err.message}`, 'err');
  }
}

// ===== Marker rendering =====

function renderMarkers(geojson) {
  markerClusterGroup.clearLayers();

  const features = geojson.features;
  const emptyMsg = document.getElementById('map-empty-msg');

  if (features.length === 0) {
    emptyMsg.classList.remove('hidden');
    return;
  }
  emptyMsg.classList.add('hidden');

  features.forEach(feature => {
    const [lon, lat] = feature.geometry.coordinates;
    const props = feature.properties;

    const color = props.marker_color;
    const marker = L.circleMarker([lat, lon], {
      radius: 6,
      fillColor: color,
      color: '#fff',
      weight: 1,
      opacity: 0.9,
      fillOpacity: 0.85,
    });

    marker.bindPopup(buildPopup(props), { maxWidth: 280 });
    markerClusterGroup.addLayer(marker);
  });

  // Fit map to the displayed markers
  const bounds = markerClusterGroup.getBounds();
  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
  }
}

function buildPopup(p) {
  const row = (label, value) =>
    value != null && value !== ''
      ? `<tr><td class="popup-label">${label}</td><td class="popup-value">${escHtml(String(value))}</td></tr>`
      : '';

  return `
    <table class="popup-table">
      ${row('MAC',       p.mac)}
      ${row('SSID',      p.ssid)}
      ${row('Auth',      p.auth_mode)}
      ${row('First Seen',p.first_seen ? p.first_seen.replace('T', ' ') : null)}
      ${row('Channel',   p.channel)}
      ${row('Frequency', p.frequency ? p.frequency + ' MHz' : null)}
      ${row('RSSI',      p.rssi != null ? p.rssi + ' dBm' : null)}
      ${row('Type',      p.type)}
    </table>`;
}

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ===== Status helpers =====

function setFilterStatus(html, type) {
  const el = document.getElementById('filter-status');
  el.innerHTML = html;
  el.className = type ? `status-${type}` : '';
}

function setImportStatus(html, type) {
  const el = document.getElementById('import-status');
  el.innerHTML = html;
  el.className = type ? `status-${type}` : '';
}

// ===== Import section =====

const fileInput  = document.getElementById('file-input');
const btnImport  = document.getElementById('btn-import');
const fileLabelText = document.getElementById('file-label-text');

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (file) {
    fileLabelText.textContent = file.name;
    btnImport.disabled = false;
  } else {
    fileLabelText.textContent = 'Choose CSV file…';
    btnImport.disabled = true;
  }
});

btnImport.addEventListener('click', async () => {
  const file = fileInput.files[0];
  if (!file) return;

  btnImport.disabled = true;
  setImportStatus('<span class="spinner"></span>Importing…', 'info');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/imports', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) {
      setImportStatus(`Error: ${data.detail ?? res.statusText}`, 'err');
    } else {
      setImportStatus(
        `Imported ${data.rows_imported} row${data.rows_imported !== 1 ? 's' : ''}` +
        (data.rows_skipped ? `, ${data.rows_skipped} skipped.` : '.'),
        'ok'
      );
      fileInput.value = '';
      fileLabelText.textContent = 'Choose CSV file…';
      await loadImportHistory();
    }
  } catch (err) {
    setImportStatus(`Error: ${err.message}`, 'err');
  } finally {
    btnImport.disabled = false;
  }
});

// ===== Import history =====

async function loadImportHistory() {
  try {
    const res = await fetch('/api/imports');
    if (!res.ok) return;
    const imports = await res.json();
    renderImportHistory(imports);
  } catch (_) { /* silently ignore — history is non-critical */ }
}

function renderImportHistory(imports) {
  const list = document.getElementById('import-history-list');
  list.innerHTML = '';

  if (imports.length === 0) {
    list.innerHTML = '<li class="history-empty">No imports yet.</li>';
    return;
  }

  imports.forEach(imp => {
    const li = document.createElement('li');

    const dateStr = imp.recon_date
      ? new Date(imp.recon_date).toLocaleString()
      : new Date(imp.imported_at).toLocaleString();

    li.innerHTML = `
      <div class="history-info">
        <div class="history-date">${escHtml(dateStr)}</div>
        <div class="history-meta">${imp.row_count} networks · imported ${new Date(imp.imported_at).toLocaleDateString()}</div>
      </div>
      <button class="btn-delete" title="Delete import" data-id="${imp.id}">×</button>`;

    li.querySelector('.btn-delete').addEventListener('click', async () => {
      if (!confirm('Delete this import record? Network data is preserved.')) return;
      try {
        await fetch(`/api/imports/${imp.id}`, { method: 'DELETE' });
        await loadImportHistory();
      } catch (_) { /* ignore */ }
    });

    list.appendChild(li);
  });
}

// ===== Initialise on page load =====

loadFilters();
loadImportHistory();
