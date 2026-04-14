/* wViewer — main application script
 *
 * Initialises the Leaflet map and wires up the sidebar controls.
 * Map starts empty; results are only fetched when the user presses Apply.
 */

// ===== View switching =====

let currentView = 'map';

function switchView(view) {
  if (view === currentView) return;
  currentView = view;

  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });

  // Show/hide panels
  document.getElementById('map-view').classList.toggle('hidden', view !== 'map');
  document.getElementById('table-view').classList.toggle('hidden', view !== 'table');

  // Leaflet needs a size hint after being revealed
  if (view === 'map') {
    map.invalidateSize();
  }
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

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

// ===== Table view state =====

const tableState = {
  page: 1,
  pageSize: 50,
  sortBy: 'id',
  sortDir: 'asc',
  totalPages: 1,
  total: 0,
};

const TABLE_COLUMNS = [
  { key: 'id',              label: 'ID',          sortable: true  },
  { key: 'mac',             label: 'MAC',         sortable: true  },
  { key: 'ssid',            label: 'SSID',        sortable: true  },
  { key: 'auth_mode',       label: 'Auth Mode',   sortable: true  },
  { key: 'first_seen',      label: 'First Seen',  sortable: true  },
  { key: 'channel',         label: 'Channel',     sortable: true  },
  { key: 'frequency',       label: 'Freq (MHz)',  sortable: true  },
  { key: 'rssi',            label: 'RSSI (dBm)',  sortable: true  },
  { key: 'latitude',        label: 'Latitude',    sortable: true  },
  { key: 'longitude',       label: 'Longitude',   sortable: true  },
  { key: 'altitude_meters', label: 'Alt (m)',     sortable: true  },
  { key: 'accuracy_meters', label: 'Acc (m)',     sortable: true  },
  { key: 'type',            label: 'Type',        sortable: true  },
  { key: 'import_id',       label: 'Import ID',   sortable: false },
  { key: 'rcois',           label: 'RCOIs',       sortable: false },
  { key: 'mfgr_id',         label: 'Mfgr ID',     sortable: false },
];

// ===== Apply button =====

document.getElementById('btn-apply').addEventListener('click', applyFilters);

/** Build URLSearchParams from the current sidebar filter inputs. */
function buildFilterParams() {
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
  return params;
}

async function applyFilters() {
  saveFilters();
  if (currentView === 'map') {
    await applyMapView();
  } else {
    await applyTableView();
  }
}

async function applyMapView() {
  const params = buildFilterParams();
  params.set('limit', '100000');

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

async function applyTableView() {
  tableState.page = 1;
  await fetchTablePage();
}

async function fetchTablePage() {
  const params = buildFilterParams();
  params.set('page', tableState.page);
  params.set('page_size', tableState.pageSize);
  params.set('sort_by', tableState.sortBy);
  params.set('sort_dir', tableState.sortDir);

  setFilterStatus('<span class="spinner"></span>Loading…', 'info');

  try {
    const res = await fetch(`/api/networks/table?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderTable(data);
    const t = data.total;
    setFilterStatus(`${t} network${t !== 1 ? 's' : ''} found.`, 'ok');
  } catch (err) {
    setFilterStatus(`Error: ${err.message}`, 'err');
  }
}

function renderTable(data) {
  const { total, page, page_size, items } = data;

  const start   = total === 0 ? 0 : (page - 1) * page_size + 1;
  const end     = Math.min(page * page_size, total);
  const totalPages = Math.max(1, Math.ceil(total / page_size));

  tableState.totalPages = totalPages;
  tableState.total      = total;

  // Toolbar count
  document.getElementById('table-count').textContent =
    total === 0 ? 'No results' : `Showing ${start}–${end} of ${total}`;

  // Header (built once; WVIEWER-20 will update sort arrows)
  buildTableHead();

  // Body
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';

  if (items.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = TABLE_COLUMNS.length + 1;
    td.textContent = 'No networks match the current filters.';
    td.style.cssText = 'text-align:center;color:#8892b0;padding:20px;';
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    items.forEach(item => tbody.appendChild(buildTableRow(item)));
  }

  // Pagination controls
  document.getElementById('pagination-info').textContent =
    total === 0 ? '' : `${start}–${end} of ${total}`;
  document.getElementById('page-indicator').textContent = `${page} / ${totalPages}`;

  document.getElementById('btn-first-page').disabled = page <= 1;
  document.getElementById('btn-prev-page').disabled  = page <= 1;
  document.getElementById('btn-next-page').disabled  = page >= totalPages;
  document.getElementById('btn-last-page').disabled  = page >= totalPages;
}

function buildTableHead() {
  const thead = document.getElementById('table-head');
  if (thead.querySelector('tr')) {
    // Already built — just refresh the sort arrows
    updateSortArrows();
    return;
  }

  const tr = document.createElement('tr');
  TABLE_COLUMNS.forEach(col => {
    const th = document.createElement('th');
    th.dataset.col = col.key;

    if (col.sortable) {
      th.classList.add('sortable');
      th.textContent = col.label;
      const arrow = document.createElement('span');
      arrow.className = 'sort-arrow';
      th.appendChild(arrow);
      th.addEventListener('click', () => {
        if (tableState.sortBy === col.key) {
          tableState.sortDir = tableState.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          tableState.sortBy  = col.key;
          tableState.sortDir = 'asc';
        }
        tableState.page = 1;
        fetchTablePage();
      });
    } else {
      th.textContent = col.label;
    }

    tr.appendChild(th);
  });

  // Actions column header (no label, no sort)
  tr.appendChild(document.createElement('th'));

  thead.appendChild(tr);
  updateSortArrows();
}

function updateSortArrows() {
  document.querySelectorAll('#table-head th[data-col]').forEach(th => {
    const arrow = th.querySelector('.sort-arrow');
    if (!arrow) return;
    arrow.textContent = th.dataset.col === tableState.sortBy
      ? (tableState.sortDir === 'asc' ? ' ↑' : ' ↓')
      : '';
  });
}

function buildTableRow(item) {
  const tr = document.createElement('tr');

  TABLE_COLUMNS.forEach(col => {
    const td = document.createElement('td');
    const val = item[col.key];
    if (val == null) {
      td.textContent = '';
    } else if (col.key === 'first_seen') {
      // Drop sub-second precision, replace T separator
      td.textContent = String(val).replace('T', ' ').replace(/\.\d+$/, '');
    } else {
      td.textContent = val;
    }
    if (val != null) td.title = String(val);
    tr.appendChild(td);
  });

  // "Show on map" button
  const tdAct = document.createElement('td');
  const btn   = document.createElement('button');
  btn.className   = 'btn-show-map';
  btn.textContent = 'Map';
  btn.title       = 'Show this network on the map';
  btn.addEventListener('click', () => showOnMap(item.mac));
  tdAct.appendChild(btn);
  tr.appendChild(tdAct);

  return tr;
}

/** Switch to map view with this MAC pre-filled and apply. */
function showOnMap(mac) {
  document.getElementById('filter-mac').value = mac;
  saveFilters();
  switchView('map');
  applyMapView();
}

// ===== CSV export =====

document.getElementById('btn-export-csv').addEventListener('click', exportCsv);

async function exportCsv() {
  const btn = document.getElementById('btn-export-csv');
  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Exporting…';

  try {
    // Fetch all pages at max allowed page_size, preserving current sort
    const allItems = [];
    let page = 1;
    let total = null;

    do {
      const params = buildFilterParams();
      params.set('page', page);
      params.set('page_size', '150');
      params.set('sort_by', tableState.sortBy);
      params.set('sort_dir', tableState.sortDir);

      const res = await fetch(`/api/networks/table?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (total === null) total = data.total;
      allItems.push(...data.items);
      page++;
    } while (allItems.length < total);

    const csv      = itemsToCsv(allItems);
    const filename = `wviewer-export-${new Date().toISOString().slice(0, 10)}.csv`;
    downloadBlob(csv, 'text/csv;charset=utf-8;', filename);
  } catch (err) {
    setFilterStatus(`Export failed: ${err.message}`, 'err');
  } finally {
    btn.disabled  = false;
    btn.textContent = origText;
  }
}

/** Convert an array of network item objects to a CSV string. */
function itemsToCsv(items) {
  const header = TABLE_COLUMNS.map(c => csvCell(c.label)).join(',');
  const rows   = items.map(item =>
    TABLE_COLUMNS.map(col => {
      const val = item[col.key];
      if (val == null) return '';
      if (col.key === 'first_seen') {
        return csvCell(String(val).replace('T', ' ').replace(/\.\d+$/, ''));
      }
      return csvCell(String(val));
    }).join(',')
  );
  return [header, ...rows].join('\n');
}

/** Wrap a cell value in quotes if it contains a comma, quote, or newline. */
function csvCell(val) {
  if (/[",\n\r]/.test(val)) return '"' + val.replace(/"/g, '""') + '"';
  return val;
}

/** Trigger a browser download for the given text content. */
function downloadBlob(content, mimeType, filename) {
  const blob = new Blob([content], { type: mimeType });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
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

// ===== Pagination event listeners =====

document.getElementById('btn-first-page').addEventListener('click', () => {
  if (tableState.page > 1) { tableState.page = 1; fetchTablePage(); }
});

document.getElementById('btn-prev-page').addEventListener('click', () => {
  if (tableState.page > 1) { tableState.page--; fetchTablePage(); }
});

document.getElementById('btn-next-page').addEventListener('click', () => {
  if (tableState.page < tableState.totalPages) { tableState.page++; fetchTablePage(); }
});

document.getElementById('btn-last-page').addEventListener('click', () => {
  if (tableState.page < tableState.totalPages) { tableState.page = tableState.totalPages; fetchTablePage(); }
});

document.getElementById('page-size-select').addEventListener('change', e => {
  tableState.pageSize = parseInt(e.target.value, 10);
  tableState.page = 1;
  fetchTablePage();
});

// ===== Initialise on page load =====

loadFilters();
loadImportHistory();
