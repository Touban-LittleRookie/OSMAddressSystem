/* Possible future improvement (not done): MapLibre GL JS for the map and GeoLibre tools for the editing functions; this file uses Leaflet. */
'use strict';
/* Community address app - front end (Leaflet + plain JS). The backend does all computing; this file only draws and asks. */

const $ = (s, r = document) => r.querySelector(s);
const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (n, d = 0) => (n === null || n === undefined || Number.isNaN(n) ? '-' : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));

async function api(path, body, method) {
  const headers = AuthUI.headers();
  const opt = body === undefined && !method ? { headers } : { method: method || 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) };
  const r = await fetch('api' + path, opt);
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (!r.ok) { if(r.status===401)AuthUI.expired(); const d = data && data.detail; const err = new Error((d && d.message) || (typeof d === 'string' ? d : '') || r.statusText); err.status = r.status; err.detail = d; throw err; }
  return data;
}

const S = { project: null, network: null, addresses: null, roads: null, baseStreets: null, tab: 'ids', mode: null, sel: null,
            idColor: 'id', polling: false, labels: true, planAll: false };
const CLIENT = (() => { try { let c = localStorage.getItem('addr-client'); if (!c) { c = Math.random().toString(36).slice(2, 10); localStorage.setItem('addr-client', c); } return c; } catch (e) { return 'tab' + Math.random().toString(36).slice(2, 8); } })();
const user = () => '';

/* ---------------------------------------------------------------- map */
const map = L.map('map', { preferCanvas: true, maxZoom: 21 }).setView([5.3, 10.2], 13);
let mapResizeFrame = null;
new ResizeObserver(() => {
  cancelAnimationFrame(mapResizeFrame);
  mapResizeFrame = requestAnimationFrame(() => map.invalidateSize({ pan: false }));
}).observe(document.getElementById('map'));
map.on('dragstart zoomstart', () => { S.fitted = true; S.fittedRoads = true; });                // the user moved the map: it is theirs from now on
/* the view (tab, map position, colours, work area) is remembered in this browser so a refresh comes back to it; unsaved drafts are not kept */
const VIEW_KEY = 'addr-view:' + location.pathname;
function savedView() { try { const v = JSON.parse(localStorage.getItem(VIEW_KEY) || 'null'); return v && Number.isFinite(v.lat) && Number.isFinite(v.lon) && Number.isFinite(v.zoom) ? v : null; } catch (e) { return null; } }
function saveView() {
  if (!S.ready) return;
  const c = map.getCenter();
  try { localStorage.setItem(VIEW_KEY, JSON.stringify({ tab: S.tab, lat: c.lat, lon: c.lng, zoom: map.getZoom(), idColor: S.idColor, area: S.activeArea, quartier: S.activeQuartier })); } catch (e) { /* no storage */ }
}
map.on('moveend', saveView);
window.addEventListener('pagehide', saveView);
const hybrid = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', { maxZoom: 21, maxNativeZoom: 20, attribution: 'Imagery &copy; Google' }).addTo(map);
const osmTiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 21, maxNativeZoom: 19, attribution: '&copy; OpenStreetMap' });
const esriTiles = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 21, maxNativeZoom: 18, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics' });
/* Esri Wayback release 49059 (Apr 2026): an older, sharper capture of Fotouni than the current World Imagery */
const esriSharpTiles = L.tileLayer('https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/49059/{z}/{y}/{x}', { maxZoom: 21, maxNativeZoom: 18, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics (Wayback 2026-04-30)' });
L.control.layers({ Satellite: hybrid, 'Satellite (Esri)': esriTiles, 'Satellite (Esri, sharper)': esriSharpTiles, OpenStreetMap: osmTiles }, {}, { position: 'topleft' }).addTo(map);
/* "go to" box: paste "5.33195, 10.22380" (lat, lon; Google Maps order) or "10.22380 5.33195" and press Enter */
let gotoMark = null;
const GoTo = L.Control.extend({
  onAdd() {
    const box = L.DomUtil.create('form', 'goto-box');
    box.innerHTML = I18n.html`<input type="text" placeholder="${I18n.t('Go to: lat, lon')}" title="${I18n.t('Paste coordinates such as 5.33195, 10.22380 and press Enter')}">`;
    L.DomEvent.disableClickPropagation(box); L.DomEvent.disableScrollPropagation(box);
    box.addEventListener('submit', (e) => {
      e.preventDefault();
      const n = (box.firstChild.value.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
      if (n.length < 2) { toast(I18n.t('Write two numbers: latitude, longitude'), 4000); return; }
      let [lat, lon] = n;
      if (Math.abs(lat) > 9 && Math.abs(lon) < 9) [lat, lon] = [lon, lat];          // Cameroon: lat 2-13, lon 8-16; accept either order
      if (Math.abs(lat) > 90 || Math.abs(lon) > 180) { toast(I18n.t('Write two numbers: latitude, longitude'), 4000); return; }
      map.setView([lat, lon], Math.max(map.getZoom(), 18));
      if (gotoMark) gotoMark.remove();
      gotoMark = L.circleMarker([lat, lon], { radius: 14, color: '#ff1744', weight: 3, fill: false }).addTo(map);
      setTimeout(() => { if (gotoMark) { gotoMark.remove(); gotoMark = null; } }, 15000);
    });
    return box;
  },
});
new GoTo({ position: 'topleft' }).addTo(map);
/* opacity slider of the background map inside the layer control */
(() => {
  const box = document.querySelector('.leaflet-control-layers-list'); if (!box) return;
  let v = 100; try { v = +(localStorage.getItem('addr-bg-opacity') || 100); } catch (e) { /* no storage */ }
  const apply = (x) => { hybrid.setOpacity(x / 100); esriTiles.setOpacity(x / 100); esriSharpTiles.setOpacity(x / 100); osmTiles.setOpacity(x / 100); const lbl = box.querySelector('.bg-op-val'); if (lbl) lbl.textContent = `${x}%`; };
  const row = document.createElement('div'); row.className = 'bg-opacity';
  row.innerHTML = I18n.html`<label>Background opacity <span class="bg-op-val">${v}%</span></label><input type="range" min="0" max="100" step="5" value="${v}">`;
  box.appendChild(row);
  L.DomEvent.disableClickPropagation(row); L.DomEvent.disableScrollPropagation(row);
  row.querySelector('input').addEventListener('input', (e) => { const x = +e.target.value; apply(x); try { localStorage.setItem('addr-bg-opacity', String(x)); } catch (err) { /* ignore */ } });
  apply(v);
})();
const G = {};
['area', 'points', 'ref', 'base', 'net', 'cuts', 'labels', 'hl', 'roadEdges', 'roadNodes', 'houses', 'signs', 'access', 'junc', 'refnodes', 'refhover', 'outside', 'check'].forEach((k) => { G[k] = L.layerGroup(); });
const TAB_LAYERS = ['check', 'outside', 'junc', 'base', 'net', 'cuts', 'labels', 'roadEdges', 'roadNodes', 'houses', 'signs', 'access'];
const clearTab = () => { TAB_LAYERS.forEach((k) => { G[k].clearLayers(); map.removeLayer(G[k]); }); G.hl.clearLayers(); };
map.createPane('workareas'); map.getPane('workareas').style.zIndex = 350;
map.createPane('quartierhover'); map.getPane('quartierhover').style.zIndex = 355;
const areaLayer = L.layerGroup().addTo(map);
const quartierHoverLayer = L.layerGroup().addTo(map);
const sharedBoundaryLayer = L.layerGroup().addTo(map);
const boundaryLayer = L.layerGroup().addTo(map);
const AREA_LABELS = { unreviewed: 'Not reviewed', in_progress: 'In progress', reviewed: 'Reviewed', needs_review: 'Needs review' };
const AREA_COLORS = { unreviewed: '#78909c', in_progress: '#1976d2', reviewed: '#2e7d32', needs_review: '#ef6c00' };
const AREA_STAGES = {
  geometry: ['Road geometry', ['not_started', 'in_progress', 'reviewed', 'needs_review']],
  attributes: ['Street attributes', ['not_started', 'in_progress', 'reviewed', 'needs_review']],
  names: ['Names', ['not_started', 'in_progress', 'waiting_for_community', 'complete', 'needs_review']],
  buildings: ['Buildings', ['not_started', 'in_progress', 'reviewed', 'needs_review']],
  addresses: ['Addresses', ['not_started', 'in_progress', 'needs_correction', 'verified']]
};
const STAGE_LABELS = { not_started: 'Not started', in_progress: 'In progress', reviewed: 'Reviewed', needs_review: 'Needs review',
  waiting_for_community: 'Waiting for community', complete: 'Complete', needs_correction: 'Needs correction', verified: 'Verified' };
function activeWorkArea() { return S.project?.work_areas?.kind === 'quartiers' ? null : S.project?.work_areas?.features?.find(f => f.properties.id === S.activeArea); }
function quartierFeatures() { const areas = S.project?.work_areas; return areas?.quartiers?.features || (areas?.kind === 'quartiers' ? areas.features : []) || []; }
function activeQuartier() { return quartierFeatures().find(f => f.properties.id === S.activeQuartier); }
function highlightQuartiers(ids) {
  quartierHoverLayer.clearLayers();
  const wanted = new Set(ids);
  const features = quartierFeatures().filter(f => wanted.has(f.properties.id));
  if (!features.length) return;
  L.geoJSON({ type: 'FeatureCollection', features }, { pane: 'quartierhover', interactive: false,
    style: { color: '#ffb000', weight: 4, opacity: 1, fillColor: '#ffb000', fillOpacity: .14 }
  }).addTo(quartierHoverLayer);
}
function clearQuartierHover() { quartierHoverLayer.clearLayers(); }
function workAreaNumber(id) { const i = (S.project?.work_areas?.features || []).findIndex(f => f.properties.id === id); return i < 0 ? null : i + 1; }
function workAreaRef(f) { const n = workAreaNumber(f.properties.id), p = f.properties; return `${n === null ? '' : n + '. '}${p.kind === 'quartier' ? p.name : p.id}`; }
function areaStages(p) {
  const result = Object.fromEntries(Object.keys(AREA_STAGES).map(k => [k, 'not_started']));
  if (p.stages) Object.keys(result).forEach(k => { if (p.stages[k]) result[k] = p.stages[k]; });
  else result.geometry = { in_progress: 'in_progress', reviewed: 'reviewed', needs_review: 'needs_review' }[p.status] || 'not_started';
  return result;
}
function stageSelect(key, current) {
  const [label, values] = AREA_STAGES[key];
  return I18n.html`<label>${I18n.t(label)}<select data-area-stage="${key}">${values.map(v => I18n.html`<option value="${v}" ${current === v ? 'selected' : ''}>${I18n.t(STAGE_LABELS[v])}</option>`).join('')}</select></label>`;
}
function readFileBase64(file) { return new Promise((resolve, reject) => { const r = new FileReader(); r.onerror = () => reject(new Error('Could not read the CSV file')); r.onload = () => resolve(String(r.result).split(',', 2)[1]); r.readAsDataURL(file); }); }
function inWorkArea(f) { const area = activeWorkArea() || activeQuartier(); return !area || L.geoJSON(f).getBounds().intersects(L.geoJSON(area).getBounds()); }
function chooseQuartier(id) {
  if (S.boundaryEdit) return;
  S.areaView = 'quartiers'; S.activeQuartier = id || null; S.activeArea = null; S.boundaryOptions = null; S.areaBoxOpen = true;
  const area = activeQuartier();
  if (area) map.fitBounds(L.geoJSON(area).getBounds().pad(.05), { maxZoom: 17, animate: false });
  renderWorkAreas(); if (S.tab === 'roads') drawTab();
}
function chooseWorkArea(id) {
  if (S.check) { S.check = null; G.check.clearLayers(); }
  if (S.boundaryEdit) return;
  S.areaView = 'work'; S.activeArea = id || null; S.activeQuartier = null; S.areaBoxOpen = true;
  const area = activeWorkArea();
  if (area) map.fitBounds(L.geoJSON(area).getBounds().pad(.1), { maxZoom: 19, animate: false });
  renderWorkAreas(); if (S.tab === 'roads') drawTab();
}
function chooseAreaView(view) {
  if (S.boundaryEdit) return;
  S.areaView = ['whole', 'quartiers', 'work'].includes(view) ? view : 'whole';
  S.activeArea = null; S.activeQuartier = null; S.boundaryOptions = null; S.areaBoxOpen = true;
  renderWorkAreas(); if (S.tab === 'roads') drawTab();
}
function renderBoundaryDraft() {
  boundaryLayer.clearLayers();
  const d = S.boundaryEdit; if (!d) return;
  L.polyline(d.original, { color: '#ef6c00', weight: 7, opacity: .55, dashArray: '7 6', interactive: false }).addTo(boundaryLayer);
  L.polyline(d.pts, { color: '#00d7e8', weight: 5, opacity: 1, interactive: false }).addTo(boundaryLayer);
  d.pts.forEach((point, index) => {
    const fixed = index === 0 || index === d.pts.length - 1;
    const marker = L.marker(point, { draggable: !fixed, icon: L.divIcon({ className: `road-vertex${fixed ? index === 0 ? ' road-start' : ' road-end' : ''}`, iconSize: [12, 12], iconAnchor: [6, 6] }) }).addTo(boundaryLayer);
    marker.bindTooltip(fixed ? 'Fixed border junction' : 'Drag to adjust; right-click to remove');
    if (!fixed) {
      marker.on('dragend', event => { const p = event.target.getLatLng(); d.pts[index] = [p.lat, p.lng]; renderBoundaryDraft(); });
      marker.on('contextmenu', event => { L.DomEvent.preventDefault(event); if (d.pts.length > 2) { d.pts.splice(index, 1); renderBoundaryDraft(); } });
    }
    if (index < d.pts.length - 1) {
      const next = d.pts[index + 1], middle = [(point[0] + next[0]) / 2, (point[1] + next[1]) / 2];
      L.marker(middle, { icon: L.divIcon({ className: 'road-midpoint', iconSize: [9, 9], iconAnchor: [4, 4] }) }).addTo(boundaryLayer)
        .bindTooltip('Click to insert a border point').on('click', event => { L.DomEvent.stopPropagation(event); d.pts.splice(index + 1, 0, middle); renderBoundaryDraft(); });
    }
  });
}
function boundaryControls(area) {
  if (!area || area.properties.kind !== 'quartier') return '';
  if (S.boundaryEdit?.areaId === area.properties.id) return I18n.html`<div class="boundary-editor"><p><strong>Border with ${esc(S.boundaryEdit.neighbourName)}</strong></p>
    <p class="muted">Move white points or insert intermediate points. Green and red endpoints stay fixed so neighbouring borders remain connected.</p>
    <textarea id="boundary-reason" maxlength="500" placeholder="Field evidence and reason for this correction"></textarea>
    <div class="row"><button id="boundary-save" class="primary">Save corrected border</button><button id="boundary-reset">Reset</button><button id="boundary-cancel">Cancel</button></div></div>`;
  if (S.boundaryOptions?.area_id === area.properties.id) return S.boundaryOptions.neighbours.length ? I18n.html`<div class="boundary-editor"><label>Neighbouring quartier<select id="boundary-neighbour">${S.boundaryOptions.neighbours.map(n => I18n.html`<option value="${esc(n.id)}">${esc(n.name)} · ${fmt(n.length_m)} m</option>`).join('')}</select></label><button id="boundary-start">Adjust this shared border</button></div>` : I18n.html`<p class="muted">No editable neighbouring border was found.</p>`;
  return I18n.html`<button id="boundary-load">Adjust a quartier border</button>`;
}
function renderWorkAreas() {
  const box = $('#workarea-box'); if (!box) return;
  areaLayer.clearLayers(); sharedBoundaryLayer.clearLayers(); clearQuartierHover();
  if (!S.project || S.locked) { box.hidden = true; return; }
  box.hidden = false;
  const cells = S.project.work_areas?.kind === 'quartiers' ? [] : (S.project.work_areas?.features || []), area = activeWorkArea(), quartiers = quartierFeatures(), qArea = activeQuartier();
  const visibleCells = cells, view = S.areaView || 'whole';
  const showQuartiers = view === 'quartiers' || (view === 'work' && S.showQuartierBoundaries === true);
  const showWorkAreas = view === 'work';
  if (quartiers.length && showQuartiers) {
    L.geoJSON({ type: 'FeatureCollection', features: quartiers }, { pane: 'workareas',
      style: f => f.properties.id === S.activeQuartier
        ? { color: '#ffb000', weight: 5, opacity: 1, fillColor: '#ffb000', fillOpacity: .06, className: 'quartier-selected' }
        : { color: '#7e57c2', weight: 2.5, opacity: .82, fillOpacity: .012, dashArray: '10 5', className: 'quartier-boundary' },
      onEachFeature: (f, layer) => { layer._areaKind = 'quartier'; layer._areaSelected = f.properties.id === S.activeQuartier; layer.bindTooltip(`${esc(f.properties.name)}${f.properties.code ? ' (' + esc(f.properties.code) + ')' : ''}`, { sticky: true });
        layer.on('mouseover', () => { if (!S.boundaryEdit) highlightQuartiers([f.properties.id]); });
        layer.on('mouseout', clearQuartierHover);
        layer.on('click', e => { if (view !== 'quartiers' || S.mode || S.draw || S.cut || S.boundaryEdit) return; L.DomEvent.stopPropagation(e); chooseQuartier(f.properties.id); }); }
    }).addTo(areaLayer);
    if (!S.boundaryEdit && S.sharedQuartierBoundaries?.features?.length) {
      L.geoJSON(S.sharedQuartierBoundaries, { pane: 'quartierhover',
        style: { color: '#ffb000', weight: 14, opacity: .001, lineCap: 'round' },
        onEachFeature: (f, layer) => {
          layer._sharedQuartierBoundary = true;
          layer.bindTooltip(`${esc(f.properties.left_name)} \u2194 ${esc(f.properties.right_name)}`, { sticky: true, direction: 'top' });
          layer.on('mouseover', () => { layer.setStyle({ weight: 7, opacity: 1 }); highlightQuartiers([f.properties.left_id, f.properties.right_id]); });
          layer.on('mouseout', () => { layer.setStyle({ weight: 14, opacity: .001 }); clearQuartierHover(); });
          layer.on('click', event => L.DomEvent.stopPropagation(event));
        }
      }).addTo(sharedBoundaryLayer);
    }
  }
  if (visibleCells.length && showWorkAreas) {
    L.geoJSON({ type: 'FeatureCollection', features: visibleCells }, { pane: 'workareas',
      style: f => f.properties.id === S.activeArea
        ? { color: '#00d7e8', weight: 5, opacity: 1, fillColor: '#00d7e8', fillOpacity: .09, className: 'work-area-selected' }
        : { color: AREA_COLORS[f.properties.status] || AREA_COLORS.unreviewed, weight: 1.5, opacity: .72, fillOpacity: .018, dashArray: '5 6', className: 'work-area-grid' },
      onEachFeature: (f, layer) => { layer._areaKind = 'work'; layer._areaSelected = f.properties.id === S.activeArea; layer.bindTooltip(`${esc(workAreaRef(f))}: ${I18n.t(AREA_LABELS[f.properties.status] || 'Not reviewed')}`, { sticky: true });
        layer.on('click', e => { if (S.mode || S.draw || S.cut || S.boundaryEdit) return; L.DomEvent.stopPropagation(e); chooseWorkArea(f.properties.id); }); }
    }).addTo(areaLayer);
    if (area) {
      const ref = esc(workAreaRef(area)), status = I18n.t(AREA_LABELS[area.properties.status] || 'Not reviewed');
      L.marker(L.geoJSON(area).getBounds().getCenter(), { pane: 'workareas', interactive: false,
        icon: L.divIcon({ className: 'work-area-focus-label', html: I18n.html`<strong>${ref}</strong><span>${status}</span>`, iconSize: [0, 0] })
      }).addTo(areaLayer);
    }
  }
  const counts = Object.entries(AREA_LABELS).map(([s, label]) => `${visibleCells.filter(f => f.properties.status === s).length} ${I18n.t(label.toLowerCase())}`).join(' · ');
  const quartier = S.quartierImport, kind = S.project.work_areas?.kind;
  const importReview = quartier?.preview ? I18n.html`<div class="quartier-review">
    <p><strong>${fmt(quartier.preview.catalog?.with_points || 0)} approved quartiers with GPS points</strong> · ${fmt(quartier.preview.inside_rows)} records inside · ${fmt(quartier.preview.outside_rows)} outside</p>
    <p class="muted">The supplied Fotouni catalogue determines the approved spelling, trigram and variants. Balassie is grouped under Lassié as confirmed.</p>
    <div class="quartier-name-list">${quartier.preview.groups.map(g => I18n.html`<label class="${g.catalog_status === 'approved' ? '' : 'muted'}"><span>${esc(g.variants.map(v => `${v.name} (${v.count})`).join(' / '))}</span><input class="quartier-name" data-key="${esc(g.key)}" value="${esc(g.approved_name || 'Not in approved catalogue')}" readonly></label>`).join('')}</div>
    ${quartier.preview.catalog?.without_points?.length ? I18n.html`<p class="muted"><strong>Approved quartiers without GPS observations:</strong> ${esc(quartier.preview.catalog.without_points.map(x => `${x.name} (${x.code})`).join(', '))}. Their approximate areas must be added during the live review.</p>` : ''}
    <button id="quartiers-create">Create provisional quartier areas</button>
    <p class="muted">This keeps the original work grid underneath the quartier level. The boundaries remain approximate.</p>
  </div>` : '';
  box.innerHTML = I18n.html`<details ${S.areaBoxOpen ? 'open' : ''}><summary>Work areas${qArea ? ' · ' + esc(qArea.properties.name) : ''}${area ? ' · ' + esc(workAreaRef(area)) : ''}</summary>
    <p class="muted">${quartiers.length} quartiers · ${visibleCells.length} work areas</p>
    <div class="area-view-modes" role="radiogroup" aria-label="Area view">
      <label><span><input type="radio" name="area-view" value="whole" ${view === 'whole' ? 'checked' : ''}> Whole map</span><small>See everything</small></label>
      <label><span><input type="radio" name="area-view" value="quartiers" ${view === 'quartiers' ? 'checked' : ''}> Quartiers</span><small>Choose a community area</small></label>
      <label><span><input type="radio" name="area-view" value="work" ${view === 'work' ? 'checked' : ''}> Work areas</span><small>Review one small cell</small></label>
    </div>
    <p class="scope-path"><span>Whole map</span>${qArea ? I18n.html`<b>›</b><span>${esc(qArea.properties.name)}</span>` : ''}${area ? I18n.html`<b>›</b><span>${esc(area.properties.id)}</span>` : ''}</p>
    ${view === 'whole' ? I18n.html`<div class="area-selection-card"><strong>Whole map</strong><p class="muted">The complete map is active. No quartier or work-area boundary is highlighted.</p></div>` : ''}
    ${view === 'quartiers' ? I18n.html`<div class="area-selection-card">${quartiers.length ? I18n.html`<label>Choose a quartier<select id="quartier-select"><option value="">Choose...</option>${quartiers.map(f => I18n.html`<option value="${f.properties.id}" ${f.properties.id === S.activeQuartier ? 'selected' : ''}>${esc(f.properties.name)}${f.properties.code ? ` (${esc(f.properties.code)})` : ''}</option>`).join('')}</select></label>` : I18n.html`<p class="muted">No quartier has been generated yet.</p>`}
      ${qArea ? I18n.html`<p><strong>${esc(qArea.properties.name)}</strong> ${qArea.properties.code ? I18n.html`<span class="badge">${esc(qArea.properties.code)}</span>` : ''} <span class="badge">Provisional</span></p><p class="muted">Recorded spellings: ${esc((qArea.properties.aliases || []).map(a => `${a.name} (${a.count})`).join(', ') || '-')}</p>${boundaryControls(qArea)}` : ''}
      </div>` : ''}
    ${view === 'work' ? I18n.html`<div class="area-selection-card"><label class="show-quartier-lines"><input type="checkbox" id="show-quartier-boundaries" ${S.showQuartierBoundaries === true ? 'checked' : ''}> Show quartier boundaries</label>
      ${cells.length ? I18n.html`<label>Choose a work area<select id="area-select"><option value="">Choose...</option>${visibleCells.map(f => I18n.html`<option value="${f.properties.id}" ${f.properties.id === S.activeArea ? 'selected' : ''}>${esc(workAreaRef(f))}${f.properties.quartier_name ? ` · ${esc(f.properties.quartier_name)}` : ''} · ${I18n.t(AREA_LABELS[f.properties.status] || 'Not reviewed')}</option>`).join('')}</select></label>` : I18n.html`<p>Divide this project's area into smaller review cells.</p><label>Cell size <select id="area-size"><option value="auto">Automatic</option>${[100,250,500,1000,2000].map(m=>I18n.html`<option value="${m}">${m} m</option>`).join('')}</select></label><button id="areas-create">Create work areas</button>`}
      <p class="muted">${counts}</p>
      ${area ? I18n.html`
      <details class="area-progress" ${S.areaProgressOpen ? 'open' : ''}><summary>Review progress · ${I18n.t(AREA_LABELS[area.properties.status] || 'Not reviewed')}</summary><div class="area-stage-grid">${Object.entries(areaStages(area.properties)).map(([k, v]) => stageSelect(k, v)).join('')}</div>
      <textarea id="area-note" maxlength="2000" placeholder="What was checked? What is uncertain?">${esc(area.properties.note || '')}</textarea><button id="area-save">Save area progress</button></details>` : ''}</div>` : ''}
    <details class="quartier-import area-advanced"><summary>Area setup (advanced)</summary><p>Select a CSV containing district, latitude and longitude. Only those three values are read.</p><input id="quartier-file" type="file" accept=".csv,text/csv"><button id="quartiers-preview">Preview quartiers</button>${importReview}</details>
  </details>`;
  box.querySelector('details').ontoggle = e => { S.areaBoxOpen = e.target.open; };
  const progress = box.querySelector('.area-progress'); if (progress) progress.ontoggle = e => { S.areaProgressOpen = e.target.open; };
}
document.addEventListener('change', (e) => { if (e.target && e.target.id === 'check-show-ok') { S.checkShowOk = e.target.checked; drawCheck(); renderPanel(); } });
$('#workarea-box').addEventListener('change', e => {
  if (e.target.name === 'area-view') chooseAreaView(e.target.value);
  if (e.target.id === 'quartier-select') chooseQuartier(e.target.value);
  if (e.target.id === 'area-select') chooseWorkArea(e.target.value);
  if (e.target.id === 'show-quartier-boundaries') { S.showQuartierBoundaries = e.target.checked; renderWorkAreas(); }
});
$('#workarea-box').addEventListener('click', async e => {
  try {
    if (e.target.id === 'areas-create') { await api('/work-areas/grid', { cell_m: $('#area-size').value, revision: S.rev }); S.areaBoxOpen = true; await refreshProject(); }
    if (e.target.id === 'area-save') { const stages = {}; document.querySelectorAll('[data-area-stage]').forEach(x => { stages[x.dataset.areaStage] = x.value; }); await api('/work-areas/status', { id: S.activeArea, stages, note: $('#area-note').value, revision: S.rev }); await refreshProject(); toast('Area progress saved'); }
    if (e.target.id === 'boundary-load') { S.boundaryOptions = await api(`/work-areas/boundaries?area_id=${encodeURIComponent(S.activeQuartier)}`); renderWorkAreas(); }
    if (e.target.id === 'boundary-start') {
      const neighbour = S.boundaryOptions.neighbours.find(n => n.id === $('#boundary-neighbour').value);
      S.boundaryEdit = { areaId: S.activeQuartier, neighbourId: neighbour.id, neighbourName: neighbour.name, revision: S.boundaryOptions.revision,
        original: neighbour.geometry.coordinates.map(([lon, lat]) => [lat, lon]) };
      S.boundaryEdit.pts = S.boundaryEdit.original.map(point => [...point]); renderWorkAreas(); renderBoundaryDraft();
    }
    if (e.target.id === 'boundary-reset') { S.boundaryEdit.pts = S.boundaryEdit.original.map(point => [...point]); renderBoundaryDraft(); }
    if (e.target.id === 'boundary-cancel') { S.boundaryEdit = null; boundaryLayer.clearLayers(); renderWorkAreas(); }
    if (e.target.id === 'boundary-save') {
      const d = S.boundaryEdit, reason = $('#boundary-reason').value.trim();
      await api('/work-areas/boundary', { area_id: d.areaId, neighbour_id: d.neighbourId, coords: d.pts.map(([lat, lon]) => [lon, lat]), reason, revision: d.revision });
      S.boundaryEdit = null; S.boundaryOptions = null; boundaryLayer.clearLayers(); await refreshProject(); toast('Quartier border saved');
    }
    if (e.target.id === 'quartiers-preview') {
      const file = $('#quartier-file').files[0]; if (!file) throw new Error('Choose a quartier CSV file first');
      const content_b64 = await readFileBase64(file), preview = await api('/work-areas/quartiers/preview', { content_b64 });
      S.quartierImport = { filename: file.name, content_b64, preview }; S.areaBoxOpen = true; renderWorkAreas();
    }
    if (e.target.id === 'quartiers-create') {
      const mapping = {}; document.querySelectorAll('.quartier-name').forEach(x => { mapping[x.dataset.key] = x.value.trim(); });
      const replace = quartierFeatures().length > 0;
      if (replace && !window.confirm('Replace the current provisional quartier boundaries? The smaller work areas and their progress will be preserved.')) return;
      await api('/work-areas/quartiers', { content_b64: S.quartierImport.content_b64, filename: S.quartierImport.filename, mapping, replace, revision: S.rev });
      S.quartierImport = null; S.activeArea = null; S.activeQuartier = null; await refreshProject(); toast('Quartiers created above the existing work areas');
    }
  } catch (error) { toast(error.message, 6000); }
});
const hueRaw = (id) => `hsl(${Math.round(((id * 0.61803398875) % 1) * 360)},70%,${id % 2 ? 45 : 38}%)`;
/* street colours: streets that meet at a node never get the same or a similar colour (greedy colouring over a palette of well separated colours) */
const PALETTE = (() => { const p = []; for (let k = 0; k < 90; k++) p.push({ h: Math.round((k * 137.508) % 360), l: [36, 48, 58][k % 3], s: [82, 66][(k >> 1) % 2] }); return p; })();   // golden-angle hues, 3 lightnesses, 2 saturations
const hue = (id) => (S.colorOf && S.colorOf[id]) || hueRaw(id);
function colorDistance(a, b) { const dh = Math.min(Math.abs(a.h - b.h), 360 - Math.abs(a.h - b.h)) / 180; return dh + 0.6 * Math.abs(a.l - b.l) / 22 + 0.3 * Math.abs((a.s || 0) - (b.s || 0)) / 16; }
function ensureColors() {
  if (!S.network || S.colorsFor === S.network) return;
  const adj = {};
  (S.network.junctions ? S.network.junctions.features : []).forEach((f) => {
    const ids = [...new Set(f.properties.spokes.map((s) => s.id))];
    ids.forEach((a) => { adj[a] = adj[a] || new Set(); ids.forEach((b) => { if (a !== b) adj[a].add(b); }); });
  });
  const all = S.network.streets.features.map((f) => f.properties.id);
  all.sort((a, b) => ((adj[b] ? adj[b].size : 0) - (adj[a] ? adj[a].size : 0)) || a - b);       // the most connected streets choose first
  const pick = {}, color = {}, usage = new Array(PALETTE.length).fill(0);
  all.forEach((id) => {
    const near = [...(adj[id] || [])];
    const used = near.filter((n) => pick[n] !== undefined).map((n) => PALETTE[pick[n]]);
    const two = new Set(); near.forEach((n) => (adj[n] ? adj[n] : []).forEach((m) => { if (m !== id && pick[m] !== undefined) two.add(pick[m]); }));      // streets two steps away
    let best = 0, bs = 1e9;
    PALETTE.forEach((c, i) => {
      const dmin = used.length ? Math.min(...used.map((u) => colorDistance(c, u))) : 9;
      // neighbours must look different; among the colours that do, take the least used one (and avoid the colours of streets two steps away)
      const score = (dmin < 0.5 ? 1000 * (0.5 - dmin) : 0) + usage[i] * 2 + (two.has(i) ? 5 : 0) - dmin * 0.1;
      if (score < bs) { bs = score; best = i; }
    });
    pick[id] = best; usage[best] += 1; const c = PALETTE[best]; color[id] = `hsl(${c.h},${c.s}%,${c.l}%)`;
  });
  S.colorOf = color; S.colorsFor = S.network;
}
const STATUS = { named: '#2e7d32', derived: '#f9a825', derived2: '#ef6c00', planned: '#d50000', uncovered: '#7b1fa2', other: '#9e9e9e' };
const statusColor = (p) => (p.status === 'derived' && p.level === 2 ? STATUS.derived2 : STATUS[p.status] || STATUS.other);

function toast(msg, ms = 2800) { const t = $('#toast'); t.textContent = I18n.t(msg); t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, ms); }
function banner(text, mode) { const b = $('#banner'); if (!text) { b.hidden = true; return; } b.hidden = false; b.className = mode ? 'mode' : ''; b.innerHTML = esc(I18n.t(text)) + (mode && !S.locked ? I18n.htmlText(' <button id="banner-cancel">Cancel</button>') : ''); const c = $('#banner-cancel'); if (c) c.onclick = () => (S.edgeAccess ? ACT['edge-access-cancel']() : S.draw ? stopDraw() : S.cut ? ACT['cut-cancel']() : setMode(null)); }

/* ---------------------------------------------------------------- project / header */
function renderSaveState() {
  const st=S.project.status,when=t=>t.replace('T',' ').slice(0,16);
  $('#save-state').textContent=(st.last_edit ? I18n.msg`last edit ${when(st.last_edit.ts)}` : I18n.t('no edits yet'))+' · '+I18n.msg`checkpoint "${st.last_label}" ${when(st.last_saved)}`;
}
async function refreshProject() {
  S.project = await api('/project');
  try { S.sharedQuartierBoundaries = quartierFeatures().length ? await api('/work-areas/shared-boundaries') : null; }
  catch (error) { S.sharedQuartierBoundaries = null; }
  const p = S.project, st = p.status;
  updateLock();
  $('#project-name').textContent = p.name + (p.version ? ` · v${p.version}` : '');
  renderSaveState();
  if (S.rev !== undefined && S.rev !== st.revision) { S.baseStreets = null; S.components = null; S.refNodes = null; S.edgeData = null; S.rawBuildings = null; S.pointRanks = null; S.outsideNet = null; }      // anything edited: every cached layer is reloaded
  S.rev = st.revision; S.netHash = p.network_hash;
  $('#btn-undo').disabled = !st.can_undo; $('#btn-redo').disabled = !st.can_redo;
  $('#tabs').querySelectorAll('button').forEach((b) => { b.disabled = !p.reference && b.dataset.tab !== 'roads'; b.classList.toggle('active', b.dataset.tab === S.tab); });
  const bits = [];
  if (p.stale && S.polling) bits.push('updating the street ids...'); else if (p.addresses_stale && S.tab === 'addresses') bits.push('updating the addresses...');
  if (!p.reference) bits.push('choose the reference point');
  $('#job').textContent = bits.map(I18n.t).join(' · ');
  autoCompute();
  updateStaleBar();
  updateWarnBadge();
  renderWorkAreas();
  return p;
}
function allWarnings() {
  const out = [];
  const p = S.project;
  return [...out, ...((S.network && S.network.warnings) || []), ...((S.addresses && S.addresses.warnings) || [])];
}
function updateWarnBadge() { const n = allWarnings().length; const c = $('#warn-count'); c.textContent = n; $('#warn-count2').textContent = n; $('#btn-warnings').style.color = n ? 'var(--warn)' : ''; renderWarnings(); }

/* ---------------------------------------------------------------- static layers: area, points, reference */
async function loadStaticLayers() {
  G.area.clearLayers(); G.points.clearLayers();
  const has = S.project.has;
  if (has.area) { const a = await api('/layers/area'); L.geoJSON(a, { style: { color: '#00897b', weight: 2, fill: false, dashArray: '6 5' }, interactive: false }).addTo(G.area); G.area.addTo(map); }
  if (has.points) {
    const pts = await api('/layers/points');
    S.pointsCount = pts.features.length; S.pointsData = pts;
    L.geoJSON(pts, { pointToLayer: (f, ll) => sqMarker(ll),
      onEachFeature: (f, l) => l.bindTooltip(esc(Object.values(f.properties).filter(Boolean).slice(0, 2).join(' · '))) }).addTo(G.points);
    G.points.addTo(map);
  }
}
function drawReference() {
  const r = S.project.reference; if (!r || S.locked) return;
  G.ref.clearLayers();                // while it is being confirmed or chosen, only the node being asked about is drawn
  refMarkers(r).forEach((m) => m.addTo(G.ref));
  G.ref.addTo(map);
}
/* the reference point is always a node of the road network, drawn so it cannot be missed: pulsing rings, a dot exactly on the node, a star and a label;
   `asking` (while it is being chosen or confirmed) makes it much bigger and brighter */
function refPin(r, asking, label) {
  const html = I18n.html`<div class="refpin${asking ? ' asking' : ''}"><span class="ring r1"></span><span class="ring r2"></span><svg class="star" viewBox="-12 -12 24 24"><polygon points="0,-11 3.2,-3.6 11,-3.4 4.8,1.6 7,9.4 0,5 -7,9.4 -4.8,1.6 -11,-3.4 -3.2,-3.6"/></svg>${label === null ? '' : I18n.html`<span class="lbl">${I18n.t(label || 'REFERENCE POINT')}</span>`}</div>`;
  return L.marker([r.lat, r.lon], { icon: L.divIcon({ className: '', html, iconSize: [0, 0] }), keyboard: false, zIndexOffset: 5000 })
    .bindTooltip(`Reference point (node ${r.node}): the numbering starts here`, { direction: 'bottom', offset: [0, 14] });
}
function refMarkers(r, asking) { return [refPin(r, !!asking, asking ? undefined : null)]; }       // the label only while it is being chosen or confirmed

/* ---------------------------------------------------------------- modes (reference / road point / connect) */
function setMode(kind, data) {
  S.mode = kind ? { kind, data } : null;
  map.getContainer().style.cursor = kind ? 'crosshair' : '';
  const text = { reference: 'Move over the map: the highlighted node is where the reference point goes. Click to choose it - the numbering starts from that node.',
                 access: I18n.msg`Click a road next to house ${data && data.id}: its number will be taken from that point.`,
                 connect: 'Click the existing road or node this end must connect to.',
                 'edge-access': data && data.a ? 'Click B. Both points will snap to the nearest network node.' : 'Click A on or near a road. It will snap to the nearest network node.',
                 cut: 'Click two positions on the selected road. Only the red preview between them will be removed.', draw: '' }[kind];
  banner(kind && kind !== 'reference' ? text : '', !!kind);
  if (kind === 'reference') showRefNodes(); else hideRefNodes();
}
/* while the reference point is chosen: every node of the drivable streets is shown and the nearest one is highlighted; a click takes that node */
async function showRefNodes() {
  if (!S.refNodes) S.refNodes = await api('/base/nodes');
  if (!S.mode || S.mode.kind !== 'reference') return;
  G.refnodes.clearLayers();
  S.refNodes.forEach(([id, lon, lat]) => L.circleMarker([lat, lon], { radius: 3, color: '#4a148c', weight: 1, fillColor: '#fff', fillOpacity: 1, interactive: false }).addTo(G.refnodes));
  G.refnodes.addTo(map);
}
function hideRefNodes() { G.refnodes.clearLayers(); G.refhover.clearLayers(); S.hoverNode = null; }
function nearestNode(ll) {
  if (!S.refNodes) return null;
  const k = Math.cos(ll.lat * Math.PI / 180); let best = null, bd = 1e18;
  for (const n of S.refNodes) { const dx = (n[1] - ll.lng) * k, dy = n[2] - ll.lat, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = n; } }
  return best;
}
map.on('dblclick', (e) => { if (S.draw && !isReshapeMode(S.draw) && S.draw.mode !== 'route' && S.draw.tool === 'points' && !S.draw.saving && S.draw.pts.length >= 3) { S.draw.pts.pop(); S.draw.snaps.pop(); finishDraw(); } });
map.on('mousemove', (e) => {
  if (!S.mode || S.mode.kind !== 'reference') return;
  const n = nearestNode(e.latlng); S.hoverNode = n; G.refhover.clearLayers();
  if (n) { refPin({ lat: n[2], lon: n[1], node: n[0] }, true, 'CLICK TO CHOOSE THIS NODE').addTo(G.refhover); G.refhover.addTo(map); }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !S.locked) { if (S.draw) stopDraw(); else if (S.cut) ACT['cut-cancel'](); else if (S.join) cancelJoin(); else setMode(null); }
  if (e.key === 'Enter' && S.draw && !(e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT'))) finishDraw();
});
/* nothing can be done until the reference point is set / confirmed in this page load: the whole app is locked except the map (to move it) */
function updateLock() {
  const p = S.project;
  S.locked = !p || !p.reference || !S.refConfirmed;
  document.body.classList.toggle('locked', S.locked);
}
map.getContainer().addEventListener('click', (e) => { if (S.locked && !(S.mode && S.mode.kind === 'reference')) { e.stopPropagation(); e.preventDefault(); } }, true);
/* a click on an empty place of the map ends every special style: the selection, its popup, the highlight and the azimuth arrow / road point of a building */
function clearSelection() {
  if (!S.sel && !S.selPopup && !G.hl.getLayers().length && !G.access.getLayers().length) return;
  S.sel = null; G.hl.clearLayers(); G.access.clearLayers();
  if (S.selPopup) { const p = S.selPopup; S.selPopup = null; map.closePopup(p); }
  renderPanel();
}
map.on('click', async (e) => {
  if (!S.mode) { if (!S.locked) clearSelection(); return; }
  const { kind, data } = S.mode;
  try {
    if (kind === 'reference') {
      await showRefNodes(); const pick = S.hoverNode || nearestNode(e.latlng);
      if (!pick) { toast('No road node found here'); return; }
      tentativeReference(pick);                       // nothing is saved or computed until the editor confirms
    } else if (kind === 'access') {
      const snap = await api('/access/snap', { lat: e.latlng.lat, lon: e.latlng.lng });
      await api('/access', { building_id: data.id, lat: snap.lat, lon: snap.lon, user: user() });
      setMode(null); toast(`Road point set on street ${snap.street || snap.street_id}.`);
      await afterEdit(); drawTab();
    } else if (kind === 'edge-access') {
      if (!S.edgeAccess.a) {
        S.edgeAccess.a = { lat: e.latlng.lat, lon: e.latlng.lng };
        setMode('edge-access', { a: true }); renderPanel();
      } else {
        S.edgeAccess.result = await api('/edges/access/path', { a: S.edgeAccess.a, b: { lat: e.latlng.lat, lon: e.latlng.lng } });
        S.edgeAccess.route = 0; setMode(null); drawTab();
      }
    } else if (kind === 'cut') {
      await addCutPoint(e.latlng);
    } else if (kind === 'draw' && S.draw && (!isReshapeMode(S.draw) || S.draw.mode === 'reshape-partial') && S.draw.tool === 'points') {
      await addDrawPoint(e.latlng);
    } else if (kind === 'connect') {
      if (S.stage) {
        const r = await api('/roads/snap', { lat: e.latlng.lat, lon: e.latlng.lng });
        S.stage.connections[data.key] = r.target; setMode(null); await previewStage(false); S.sel = null;
        toast(r.target.type === 'node' ? 'Connected to the node' : 'Connected to the road (it will be split there)'); drawTab(); return;
      }
      const r = await api('/roads/connect', { node: data.key, lat: e.latlng.lat, lon: e.latlng.lng, user: user() });
      setMode(null); toast(r.target.type === 'node' ? 'Connected to the node' : 'Connected to the road (it will be split there)');
      await afterEdit(); await loadRoads(); drawTab();
    }
  } catch (err) { toast(err.message, 4500); }
});

async function afterEdit() { await refreshProject(); if (S.check) runCheck(false); }

/* ---------------------------------------------------------------- road check (gaps, overlaps, stubs, ends, skipped edits) */
const CHECK_KINDS = {
  skipped: ['Edits not applied', '#d50000'], gap: ['Gaps: an end stops close to a road', '#ff1744'],
  overlap: ['Roads on top of each other', '#aa00ff'], crossing: ['Roads cross without a junction', '#ff9100'],
  isolated: ['Not connected to the network', '#c51162'], stub: ['Very short sections', '#ffea00'],
  free_end: ['Drawn road ends not connected', '#ff6d00'], drivable_unknown: ['Drivable not set', '#00b0ff'],
};
function checkText(i) {
  if (i.kind === 'gap') return I18n.msg`${fmt(i.distance_m, 1)} m gap`;
  if (i.kind === 'skipped') return I18n.msg`${I18n.t(i.what)} · edit ${(i.events || []).join(', ')}`;
  if (i.kind === 'drivable_unknown') return I18n.msg`street ${i.street_id ?? '?'} · ${fmt(i.length_m, 0)} m`;
  if (i.length_m !== undefined) return I18n.msg`${fmt(i.length_m, 1)} m`;
  return I18n.msg`at ${i.lat.toFixed(5)}, ${i.lon.toFixed(5)}`;
}
async function runCheck(render = true) {
  const area = S.activeArea || S.activeQuartier || '';
  const r = await api('/roads/check' + (area ? `?area=${encodeURIComponent(area)}` : ''));
  if ((r.area || '') !== (S.activeArea || S.activeQuartier || '')) return;            // the area changed meanwhile
  S.check = r;
  if (S.tab === 'roads') { drawCheck(); if (render || !S.draw) renderPanel(); }
}
function drawCheck() {
  G.check.clearLayers();
  if (!S.check) return;
  S.check.issues.forEach((issue, n) => {
    if (issue.ok && !S.checkShowOk) return;
    const colour = (CHECK_KINDS[issue.kind] || ['', '#ff1744'])[1];
    const layer = L.geoJSON(issue.geometry, { style: { color: colour, weight: issue.kind === 'drivable_unknown' ? 4 : 7, opacity: issue.ok ? .35 : .85, dashArray: issue.kind === 'drivable_unknown' ? '6 6' : null },
      pointToLayer: (_f, ll) => L.circleMarker(ll, { radius: 9, color: '#000', weight: 2, fillColor: colour, fillOpacity: issue.ok ? .3 : .95 }) });
    layer.bindTooltip(`${esc(I18n.t(CHECK_KINDS[issue.kind]?.[0] || issue.kind))}: ${esc(checkText(issue))}`, { sticky: true });
    layer.on('click', (e) => { L.DomEvent.stopPropagation(e); zoomCheck(n); });
    layer.addTo(G.check);
  });
  G.check.addTo(map);
}
function zoomCheck(n) {
  const issue = S.check?.issues[n]; if (!issue) return;
  S.checkFocus = issue.id;
  const b = L.geoJSON(issue.geometry).getBounds();
  if (b.isValid()) map.fitBounds(b.pad(1.5), { maxZoom: 20 }); else map.setView([issue.lat, issue.lon], 19);
  G.hl.clearLayers(); L.geoJSON(issue.geometry, { style: { color: '#00e5ff', weight: 12, opacity: .5 }, pointToLayer: (_f, ll) => L.circleMarker(ll, { radius: 16, color: '#00e5ff', weight: 4, fill: false }), interactive: false }).addTo(G.hl); G.hl.addTo(map);
  renderPanel();
}
function panelCheck() {
  const area = activeWorkArea() || activeQuartier();
  const where = area ? esc(workAreaRef(area)) : I18n.t('the whole map');
  if (!S.check) return I18n.html`<p class="muted">${I18n.msg`Lists what to look at in ${where}: gaps, roads on top of each other, very short sections, unconnected ends, edits that do not apply. Nothing is changed by the check.`}</p><div class="row"><button class="primary" data-act="check-run">${I18n.msg`Check ${where}`}</button></div>`;
  const groups = Object.keys(CHECK_KINDS).map((kind) => {
    const rows = S.check.issues.map((i, n) => [i, n]).filter(([i]) => i.kind === kind && (!i.ok || S.checkShowOk));
    if (!rows.length) return '';
    const body = rows.map(([i, n]) => I18n.html`<tr class="click ${S.checkFocus === i.id ? 'sel' : ''}" data-act="check-zoom" data-n="${n}"><td>${n + 1}</td><td>${checkText(i)}</td><td>${i.ok
      ? I18n.html`<button data-act="check-ok" data-id="${esc(i.id)}" data-ok="0">List again</button>` : I18n.html`<button data-act="check-ok" data-id="${esc(i.id)}" data-ok="1">OK as is</button>`}</td></tr>`).join('');
    return I18n.html`<details ${kind !== 'drivable_unknown' ? 'open' : ''}><summary><span class="dot" style="background:${CHECK_KINDS[kind][1]}"></span> ${I18n.t(CHECK_KINDS[kind][0])} (${rows.filter(([i]) => !i.ok).length})</summary><table>${body}</table></details>`;
  }).join('');
  const left = Object.values(S.check.counts).reduce((a, b) => a + b, 0);
  return I18n.html`<p>${left ? I18n.msg`${left} problems left in ${where}.` : I18n.msg`Nothing left to check in ${where}.`} <span class="muted">Click one to zoom to it.</span></p>
    ${groups}
    <div class="row"><button data-act="check-run">Check again</button>${S.check.ok ? I18n.html`<label><input type="checkbox" id="check-show-ok" ${S.checkShowOk ? 'checked' : ''}> ${I18n.msg`show the ${S.check.ok} marked OK`}</label>` : ''}<button data-act="check-close">Hide</button></div>`;
}

/* ---------------------------------------------------------------- compute */
/* Edits do not recompute by themselves: switching workspace tabs is navigation only.  The stale bar and the address
   panel provide explicit buttons, so geometry can be reviewed in batches without an expensive calculation per tab. */
function recomputeIfStale() { const p = S.project; if (p && p.reference && S.refConfirmed && !S.polling && p.network_ready && p.stale) startCompute('network', true); }
function updateStaleBar() {
  const p = S.project, bar = $('#stalebar'); if (!bar) return;
  const show = !!(p && p.reference && p.network_ready && p.stale && !S.polling && !S.recomputing);
  bar.hidden = !show;
  if (show) bar.innerHTML = I18n.htmlText('Edits not applied yet <button id="recompute-now" class="primary">Recompute ids</button>');
}
document.addEventListener('click', (e) => { if (e.target && e.target.id === 'recompute-now') { $('#stalebar').hidden = true; recomputeIfStale(); } });      // the bar goes away at once
function autoCompute() {
  if(!AuthUI.can('compute'))return;
  const p = S.project; if (!p || !p.reference || !S.refConfirmed || S.polling) return;
  const atStart = !S.startChecked; S.startChecked = true;       // at the start of the map the ids are recomputed once when edits are waiting
  if (!p.network_ready || (atStart && p.stale)) {                // otherwise edits wait (see recomputeIfStale); one try per page load, never after every edit
    if (!S.autoNet) { S.autoNet = true; startCompute('network', true); }
  }
}
async function startCompute(kind, quiet = true) {
  if(!AuthUI.can('compute'))return;
  if (kind === 'network') { S.recomputing = true; updateStaleBar(); }          // the bar stays away from the click until the computation ends
  try {
    const r = await api(kind === 'network' ? '/compute' : '/addresses/compute', {});
    if (!r.started && !quiet) toast('A computation is already running');
  } catch (e) { S.recomputing = false; updateStaleBar(); toast(e.message, 4500); return; }
  pollJob(kind);
}
function showComputeStatus(step, started = S.computeStartedAt) {
  const box = $('#compute-status'); if (!box) return;
  S.computeStartedAt = started || Date.now();
  const elapsed = Math.max(0, Math.floor((Date.now() - S.computeStartedAt) / 1000));
  box.hidden = false;
  box.innerHTML = I18n.html`<span class="compute-spinner" aria-hidden="true"></span><strong>${esc(I18n.t(step || 'Updating the map'))}</strong><small>${elapsed} s · ${esc(I18n.t('The current map stays visible until the update is ready.'))}</small>`;
}
function hideComputeStatus() {
  const box = $('#compute-status'); if (box) box.hidden = true;
  S.computeStartedAt = null;
}
async function pollJob(kind) {
  if (S.polling) return; S.polling = true; S.computeStartedAt = Date.now();
  const run = S.computeRun = (S.computeRun || 0) + 1;
  showComputeStatus('Updating the map');
  const tick = async () => {
    let j;
    try { j = await api('/job'); } catch (e) { $('#job').textContent = 'waiting for computation status...'; setTimeout(tick, 1000); return; }
    if (j.state === 'running') { $('#job').textContent = `computing: ${j.step}...`; showComputeStatus(j.step); setTimeout(tick, 600); return; }
    S.polling = false; S.recomputing = false;
    if (j.state === 'error') { hideComputeStatus(); toast(`Computation failed: ${j.error}`, 7000); await refreshProject(); return; }
    if (j.state === 'done') {
      showComputeStatus('Loading the completed map');
      await loadComputed(j.kind || kind);
      if (S.computeRun === run && !S.polling) hideComputeStatus();
    }
  };
  tick();
}
async function loadComputed(kind) {
  try {
    if (kind === 'addresses') S.addresses = await api('/addresses');
    S.network = await api('/network');
    if (kind !== 'addresses') S.addresses = null;                     // the addresses follow the new street ids
    await refreshProject();
    await loadRoads(true);                                            // prepare every road layer before the old map is replaced
  } catch (e) { /* not available yet */ }
  if (S.tab === 'addresses') S.addresses = S.addresses || null; drawTab();
  if (kind === 'network' && S.network && S.mergeCheck) {
    const parts = S.network.streets.features.filter((f) => f.properties.original === S.mergeCheck.id).length;
    toast(parts > 1 ? `The street with id ${S.mergeCheck.id} was cut again into ${parts} parts at a minimum of the distance to the reference.` : `The street with id ${S.mergeCheck.id} is kept as one street.`, 6000); S.mergeCheck = null;
  }
  if (kind === 'network' && S.network) { const b = S.network.reference; if (!S.fitted) { map.setView([S.project.reference.lat, S.project.reference.lon], 16); S.fitted = true; } toast(I18n.msg`Computed: ${S.network.stats.streets} streets`); }
}
function fitToNetwork() { try { const b = L.geoJSON(S.network.streets).getBounds(); if (b.isValid()) map.fitBounds(b.pad(0.05)); } catch (e) { /* ignore */ } }

/* ---------------------------------------------------------------- warnings */
function renderWarnings() {
  const list = $('#warn-list'); const ws = allWarnings();
  list.innerHTML = ws.length ? ws.map((original, i) => { const w=I18n.warning(original); return I18n.html`<div class="warn-item ${w.severity}" data-warn="${i}"><strong>${esc(w.title)}</strong><small>${esc(w.message)}</small></div>`; }).join('') : I18n.htmlText('<p class="muted">No warnings.</p>');
}
function highlightIds(ids) {
  G.hl.clearLayers(); if (!S.network) return null; const set = new Set(ids); const bounds = [];
  S.network.streets.features.filter((f) => set.has(f.properties.id)).forEach((f) => {
    const l = L.geoJSON(f, { style: { color: '#d50000', weight: 11, opacity: .5 }, interactive: false }).addTo(G.hl); bounds.push(l.getBounds());
  });
  G.hl.addTo(map); return bounds;
}
function focusWarning(w) {
  let bounds = [];
  if (w.streets && w.streets.length) bounds = highlightIds(w.streets) || [];
  if (w.nodes) { G.hl.clearLayers(); w.nodes.forEach((n) => { L.circleMarker([n.lat, n.lon], { radius: 12, color: '#d50000', weight: 3, fill: false }).addTo(G.hl); bounds.push(L.latLngBounds([n.lat, n.lon], [n.lat, n.lon])); }); G.hl.addTo(map); }
  if (w.buildings && S.addresses) {
    const set = new Set(w.buildings); G.hl.clearLayers();
    S.addresses.houses.features.filter((f) => set.has(f.properties.building_id)).forEach((f) => { const l = L.geoJSON(f, { pointToLayer: (ft, ll) => L.circleMarker(ll, { radius: 10, color: '#d50000', weight: 3, fill: false }), style: { color: '#d50000', weight: 3, fill: false }, interactive: false }).addTo(G.hl); bounds.push(l.getBounds()); });
    G.hl.addTo(map);
  }
  if (bounds.length) { let b = bounds[0]; bounds.forEach((x) => { b = b.extend(x); }); map.fitBounds(b.pad(0.2), { maxZoom: 18 }); }
}

/* ---------------------------------------------------------------- tabs */
async function switchTab(tab) {
  if (S.stage && tab !== 'roads' && !confirm('Cancel the new streets you are previewing?')) return;
  if (S.draw && S.draw.preview) map.removeLayer(S.draw.preview);
  S.tab = tab; S.sel = null; S.stage = null; S.del = null; S.reshapePick = null; S.cut = null; S.join = null; S.draw = null; S.edgeAccess = null; map.dragging.enable(); map.doubleClickZoom.enable(); setMode(null); await refreshProject();
  if (tab === 'roads') await loadRoads();
  if ((tab === 'ids' || tab === 'names' || tab === 'addresses') && !S.network) { try { S.network = await api('/network'); } catch (e) { /* not computed */ } }
  if (tab === 'addresses' && !S.addresses) { try { S.addresses = await api('/addresses'); } catch (e) { /* not computed */ } }
  drawTab();
}
$('#tabs').addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b && !b.disabled) switchTab(b.dataset.tab); });

/* the larger road network (outside the area of interest) as a light grey context layer; it is used for the routes to the reference points outside */
async function drawOutside() {
  if (!S.outsideNet) { try { S.outsideNet = await api('/base/outside'); } catch (e) { return; } }
  G.outside.clearLayers();
  L.geoJSON(S.outsideNet, { style: { color: '#b0bec5', weight: 2, opacity: .5 }, interactive: false }).addTo(G.outside); G.outside.addTo(map); G.outside.eachLayer((l) => l.bringToBack && l.bringToBack());
}
function drawTab() {
  S.renderEpoch = (S.renderEpoch || 0) + 1;
  clearTab(); drawReference(); drawOutside();
  if (S.tab !== 'addresses' && S.project.has.points) G.points.addTo(map);
  const p = S.project;
  if (!p.reference) { drawReferencePick(); return; }
  // Never draw an obsolete computed network over pending geometry: it can make an undone or reshaped road appear to
  // have returned.  IDs/names are deliberately hidden until the user explicitly recomputes them.
  if (p.stale && (S.tab === 'ids' || S.tab === 'names')) drawPendingRoadGeometry();
  else ({ roads: drawRoads, ids: drawNetwork, names: drawNetwork, addresses: drawAddresses }[S.tab])();
  if (S.edgeAccess) drawEdgeAccessDraft();
  if (S.tab === 'roads') drawCheck();
  renderPanel();
}
function drawPendingRoadGeometry() {
  const epoch = S.renderEpoch, tab = S.tab;
  const paint = (fc) => {
    if (epoch !== S.renderEpoch || S.tab !== tab || !S.project.stale) return;
    G.base.clearLayers();
    const features = (fc.features || []).filter(inWorkArea);
    L.geoJSON({ type:'FeatureCollection', features }, { style:{ color:'#ffb300', weight:3, opacity:.9 }, interactive:false }).addTo(G.base);
    G.base.addTo(map);
  };
  if (S.baseStreets) paint(S.baseStreets);
  else api('/base/streets').then((fc) => { S.baseStreets = fc; paint(fc); }).catch(() => {});
}
async function drawReferencePick() {
  if (!S.baseStreets) S.baseStreets = await api('/base/streets');
  L.geoJSON(S.baseStreets, { style: { color: '#ffd54f', weight: 2 }, interactive: false }).addTo(G.base); G.base.addTo(map);
  try { const b = L.geoJSON(S.baseStreets).getBounds(); if (b.isValid()) map.fitBounds(b); } catch (e) { /* ignore */ }
  showMoveBox(); renderPanel();
}

/* ---------------------------------------------------------------- network tabs (ids, names) */
function featureMid(f) {
  const g = f.geometry; const line = g.type === 'MultiLineString' ? g.coordinates[0] : g.coordinates; const c = line[Math.floor(line.length / 2)]; return [c[1], c[0]];
}
const RANK_COLOR = ['#b71c1c', '#e65100', '#f9a825', '#2e7d32', '#1565c0', '#6a1b9a'];
const RANK_NAMES = ['0 motorway / trunk', '1 primary', '2 secondary', '3 tertiary', '4 residential / service', '5 footway / path'];
const NOT_DRIVABLE = 'no car access, may continue on foot or by motorbike';
/* Todo 2.1: drivable yes / no / unknown per segment. "car" means drivable; "foot" (and an older "moto") means not drivable. */
function accessLabel(access) { return I18n.t(access === 'car' ? 'drivable' : access ? NOT_DRIVABLE : 'unknown'); }
function colourLegend() {
  const m = S.idColor;
  const ring = I18n.htmlText('<span><i class="dot" style="background:#fff;border:2px solid #d50000;box-sizing:border-box"></i>street cut here for the numbering</span>');
  const withRing = (html) => html.replace(/<\/div>$/, ring + I18n.htmlText('</div>'));            // one legend with the colours and the circle
  if (m === 'rank') return withRing(legend(RANK_NAMES.map((t, i) => [RANK_COLOR[i], t]), true));
  if (m === 'drivable' || m === 'access') return withRing(legend([['#1565c0', 'drivable'], ['#9e9e9e', I18n.t(NOT_DRIVABLE)], ['#bdbdbd', 'unknown: follows the road type (dotted)']], true));
  if (m === 'paved') return withRing(legend([['#00acc1', 'paved'], ['#ef6c00', 'unpaved'], ['#bdbdbd', 'unknown (dotted)']], true));
  return I18n.html`<div class="legend">${ring}</div>`;
}
function drawNetwork() {
  const net = S.network;
  if (!net) { return; }
  ensureColors();
  const names = S.tab === 'names';
  const maxD = Math.max(1, ...net.streets.features.map((f) => f.properties.d1 || 0));
  const perEdge = !names && (S.idColor === 'drivable' || S.idColor === 'access') && net.edges;      // drivable is shown per segment
  const source = perEdge ? net.edges : net.streets;
  const layer = L.geoJSON(source, {
    style: (f) => {
      const p = f.properties;
      if (names) return { color: statusColor(p), weight: p.status === 'planned' ? 7 : p.status === 'named' ? 5 : p.status === 'other' ? 2 : 3.5, opacity: .95 };
      if (S.idColor === 'rank') return { color: RANK_COLOR[p.rank] || '#757575', weight: 4, opacity: .95 };
      if (perEdge) return p.access === 'car' ? { color: '#1565c0', weight: 5, opacity: .95 }
        : p.access ? { color: '#9e9e9e', weight: 4, opacity: .95, dashArray: '8 6' }
          : { color: '#bdbdbd', weight: 4, opacity: .95, dashArray: '2 6' };
      if (S.idColor === 'drivable' && p.drivable === null) return { color: '#bdbdbd', weight: 3, opacity: .95, dashArray: '2 5' };
      if (S.idColor === 'paved' && p.paved === null) return { color: '#bdbdbd', weight: 3, opacity: .95, dashArray: '2 5' };
      if (S.idColor === 'drivable') return p.drivable ? { color: '#1565c0', weight: 4, opacity: .95 } : { color: '#9e9e9e', weight: 3, opacity: .95, dashArray: '6 5' };
      if (S.idColor === 'paved') return p.paved ? { color: '#00acc1', weight: 4, opacity: .95 } : { color: '#ef6c00', weight: 4, opacity: .95 };
      if (S.idColor === 'distance') { const t = ((p.d0 || 0) + (p.d1 || 0)) / 2 / maxD; return { color: `hsl(${Math.round(240 - 240 * t)},85%,45%)`, weight: 4, opacity: .95 }; }
      return { color: hue(p.id), weight: 4, opacity: .95 };
    },
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindTooltip(perEdge ? `${accessLabel(p.access)} · ${I18n.t('street')} ${p.id}${p.track ? ` · ${I18n.t('OSM track')}` : ''}` : `${esc(p.display || '(no name yet)')} · street ${p.id}${p.part ? ` (part ${p.part + 1} of ${p.original})` : ''}`, { sticky: true });
      l.on('click', (e) => { if (S.mode) return; L.DomEvent.stopPropagation(e); selectStreet(p.id, true, e.latlng); });
    },
  }).addTo(G.net);
  G.net.addTo(map);
  if (S.tab === 'ids') { L.geoJSON(net.cuts, { pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4, color: '#d50000', weight: 2, fill: false }), onEachFeature: (f, l) => l.bindTooltip('a street was cut here') }).addTo(G.cuts); G.cuts.addTo(map); }
  if (S.tab === 'ids' && net.junctions) { drawJunctions(net.junctions); }
  S.labelFeatures = net.streets.features.filter((f) => f.properties.display).map((f) => ({ f, mid: featureMid(f) }));
  updateLabels(); G.labels.addTo(map);
  if (S.sel && S.sel.type === 'street') selectStreet(S.sel.id, true, S.sel.ll);
}
function updateLabels() {
  G.labels.clearLayers();
  if (!S.labels || (S.tab !== 'ids' && S.tab !== 'names') || map.getZoom() < 16 || !S.labelFeatures) return;
  const b = map.getBounds().pad(0.1);
  S.labelFeatures.forEach(({ f, mid }) => {
    if (!b.contains(mid)) return; const p = f.properties;
    L.marker(mid, { interactive: false, icon: L.divIcon({ className: '', html: I18n.html`<div class="slabel ${p.status === 'derived' ? 'derived' : p.status === 'planned' ? 'planned' : ''}">${esc(p.display)}</div>`, iconSize: [0, 0] }) }).addTo(G.labels);
  });
}
map.on('zoomend moveend', updateLabels);

function streetById(id) { return S.network && S.network.streets.features.find((f) => f.properties.id === id); }
/* node popup: every street meeting at a node, as a coloured spoke (like the old street editor) */
function splitForNumbering() {                               // final ids whose street was cut into parts by the numbering
  const n = {}; S.network.streets.features.forEach((f) => { n[f.properties.original] = (n[f.properties.original] || 0) + 1; });
  return new Set(S.network.streets.features.filter((f) => n[f.properties.original] > 1).map((f) => f.properties.id));
}
function junctionHtml(p) {
  ensureColors();
  const size = 300, c = size / 2, r = 78;
  const compass = (b) => ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(b / 45) % 8];
  const ids = [...new Set(p.spokes.map((s) => s.id))];
  const count = {}; p.spokes.forEach((s) => { count[s.id] = (count[s.id] || 0) + 1; });
  const busy = !!S.polling;                                          // selectors are disabled only while a computation is actively running
  const cutIds = splitForNumbering();                          // ids that are parts of a street cut for the numbering: better not to join them
  let svg = I18n.html`<svg width="${size}" height="${size}" class="junction-svg">`, boxes = '';
  p.spokes.forEach((s) => {
    const a = s.bearing * Math.PI / 180, col = hue(s.id), sx = Math.sin(a), sy = -Math.cos(a);
    svg += I18n.html`<line x1="${c}" y1="${c}" x2="${c + r * sx}" y2="${c + r * sy}" stroke="${col}" stroke-width="4" stroke-linecap="round"/>`;
    const lx = c + (r + 30) * sx, ly = c + (r + 16) * sy;      // the selector sits at the end of its road, in the diagram
    const sourceRank = streetById(s.id)?.properties.rank;
    const merge = ids.filter((i) => i !== s.id && (sourceRank === undefined || streetById(i)?.properties.rank === sourceRank)).map((i) => (cutIds.has(i) ? I18n.html`<option value="merge:${i}" style="color:#d50000;font-weight:700">&#9888; id ${i} (cut for the numbering)</option>` : I18n.html`<option value="merge:${i}">id ${i}</option>`)).join('');
    const split = (s.can_split ?? count[s.id] > 1) ? I18n.htmlText('<option value="split">new id (split here)</option>') : '';      // topology checked by the server; count fallback for older cached results
    boxes += merge || split
      ? I18n.html`<select class="id-change" ${busy ? 'disabled' : ''} style="left:${lx}px;top:${ly}px;border-color:${col};color:${col}" title="${busy ? 'updating the street ids...' : 'Change the id of this road'}" data-ref="${esc(s.ref)}" data-node="${p.node}" data-id="${s.id}"><option value="">${s.id}</option>${merge}${split}</select>`
      : I18n.html`<span class="id-plain" style="left:${lx}px;top:${ly}px;color:${col}">${s.id}</span>`;
  });
  svg += I18n.html`<circle cx="${c}" cy="${c}" r="4" fill="#fff"/></svg>`;
  const rankSel = (s) => {                                          // the rank of the street, editable here
    const f = S.network && S.network.streets.features.find((g) => g.properties.id === s.id); if (!f) return '';
    const q = f.properties, parts = S.network.streets.features.filter((g) => g.properties.original === q.original).length;
    return I18n.html`<select class="attr-edit" data-attr="rank" data-orig="${q.original}" ${parts > 1 ? `data-part="${q.part}"` : ''} title="Street rank">${RANK_NAMES.map((t, i) => I18n.html`<option value="${i}" ${q.rank === i ? 'selected' : ''}>${t.split(' ').slice(0, 2).join(' ')}</option>`).join('')}</select>`;
  };
  const rows = p.spokes.map((s) => I18n.html`<tr class="click" data-street="${s.id}"><td><span class="dot" style="background:${hue(s.id)}"></span> <strong>${s.id}</strong> <span class="muted">${compass(s.bearing)}</span></td><td>${esc(s.name || '(no name yet)')}</td><td>${rankSel(s)}</td></tr>`).join('');
  return I18n.html`<div class="junction"><div class="muted">Node ${p.node}${p.d !== null ? ` &middot; ${fmt(p.d)} m from the reference` : ''}</div><div class="jbox" style="width:${size}px;height:${size}px">${svg}${boxes}</div><table>${rows}</table><div class="muted">${busy ? 'Updating the street ids... selectors are off until it ends.' : 'Change an id with the selector at its road.'}</div></div>`;
}
function drawJunctions(fc) {
  L.geoJSON(fc, {
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4, color: '#000', weight: 1, fillColor: '#fff', fillOpacity: 1 }),
    onEachFeature: (f, l) => {
      l.on('click', (e) => {
        if (S.mode) return; L.DomEvent.stopPropagation(e);
        L.popup({ maxWidth: 340 }).setLatLng(l.getLatLng()).setContent(junctionHtml(f.properties)).openOn(map);
      });
    },
  }).addTo(G.junc);
  const show = () => { if (map.getZoom() >= 16) G.junc.addTo(map); else map.removeLayer(G.junc); };
  map.off('zoomend', S.juncZoom); S.juncZoom = show; map.on('zoomend', show); show();
}
document.addEventListener('change', async (e) => {                // the rank of a reference point for the street signs
  const pr = e.target.closest && e.target.closest('select.pt-rank');
  if (pr) { try { await api('/points/rank', { id: pr.dataset.id, rank: +pr.value }); toast('Saved'); S.pointRanks = null; await afterEdit(); if (S.tab === 'addresses') loadPointRanks(); } catch (err) { toast(err.message, 5000); } }
});
async function loadPointRanks() { try { S.pointRanks = await api('/points/ranks'); if (S.tab === 'addresses') renderPanel(); } catch (e) { /* no points */ } }
document.addEventListener('change', async (e) => {                // rank / drivable / paved of a street, edited in its popup
  const at = e.target.closest && e.target.closest('.attr-edit');
  if (at) {
    const body = { original: +at.dataset.orig, ...(at.dataset.part !== undefined ? { part: +at.dataset.part } : {}), [at.dataset.attr]: at.dataset.attr === 'rank' ? +at.value : JSON.parse(at.value) };
    try {
      await api('/streets/attrs', body); toast('Saved');
      if (S.network) {                                           // show the change at once; the recomputation that follows confirms it
        const key = at.dataset.attr, val = body[key];
        S.network.streets.features.forEach((f) => { if (f.properties.original === body.original && (body.part === undefined || f.properties.part === body.part)) { f.properties[key] = val; f.properties[key + '_mixed'] = false; } });
        if (S.tab === 'ids' || S.tab === 'names') { drawNetwork(); if (S.sel) refreshSel(); }
      }
      await afterEdit();
    } catch (err) { toast(err.message, 5000); }
    return;
  }
});
document.addEventListener('change', async (e) => {
  const sel = e.target.closest && e.target.closest('select.id-change'); if (!sel || !sel.value) return;
  const [mode, target] = sel.value.split(':'); const id = +sel.dataset.id, tid = +target;
  const cut = mode === 'merge' && splitForNumbering().has(tid);
  const what = mode === 'merge' ? (cut ? `Street ${tid} was cut for the numbering, so it may be cut again. Join street ${id} to it anyway and never cut it there again?` : `Give every road of street ${id} the id ${tid}?`) : `Give the branch of street ${id} that leaves node ${sel.dataset.node} on this road a new id?`;
  if (!confirm(what)) { sel.value = ''; return; }
  try {
    const r = await api('/streets/assign', mode === 'merge' ? { ref: sel.dataset.ref, mode, target: tid, force: cut } : { ref: sel.dataset.ref, mode, node: +sel.dataset.node });
    map.closePopup(); S.mergeCheck = cut ? null : { id: r.id, mode };
    toast(`ID change saved for ${r.changed} roads: id ${r.id}${r.name ? ' and the name ' + r.name : ''}. Updating the map...`, 5000);
    await afterEdit(); recomputeIfStale();
  } catch (err) { sel.value = ''; toast(err.message, 7000); }
});
document.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('select.id-change, select.attr-edit')) return; const r = e.target.closest('.junction tr[data-street]'); if (r) { map.closePopup(); selectStreet(+r.dataset.street, true); renderPanel(); } });

function selHtml() {
  if (!S.sel) return '';
  if (S.sel.type === 'street') return streetBox(S.tab === 'names');
  if (S.sel.type === 'house') return houseBox();
  if (S.sel.type === 'node') return nodePanel(!!S.stage);
  return '';
}
function refreshSel() {                                       // open / update / close the selection popup
  if(S.openingPopup)return;
  const html = selHtml();
  if (!html || !S.sel || !S.sel.ll) { if (S.selPopup) { const p = S.selPopup; S.selPopup = null; map.closePopup(p); } return; }
  const content = I18n.html`<div class="selbox">${html}</div>`;
  if (S.selPopup && S.selPopup.isOpen()) {
    const same = S.selPopup.getLatLng().equals(S.sel.ll);
    // A refresh that ends while a name is being typed must not wipe it: keep what was typed in the same popup.
    const typed = same ? [...document.querySelectorAll('.sel-popup input[type=text][id]')].filter((i) => i.value !== i.defaultValue).map((i) => [i.id, i.value, i === document.activeElement]) : [];
    S.selPopup.setContent(content);
    typed.forEach(([id, value, focused]) => { const i = document.getElementById(id); if (i) { i.value = value; if (focused) i.focus(); } });
    if (!same) S.selPopup.setLatLng(S.sel.ll); return;
  }
  // Opening can stop an existing pan and synchronously fire moveend. Assign
  // the popup first and guard re-entry so that handler cannot open a second
  // popup and detach the one Leaflet is still positioning.
  S.openingPopup=true;
  try {
    S.selPopup=L.popup({maxWidth:400,minWidth:280,autoClose:true,closeOnClick:false,className:'sel-popup',autoPanPadding:[30,30]}).setLatLng(S.sel.ll).setContent(content);
    S.selPopup.openOn(map);
    S.selPopup.options.autoPan=false;
  } finally {S.openingPopup=false;}
}
map.on('popupclose', (e) => { if (e.popup === S.selPopup) { S.selPopup = null; S.sel = null; G.hl.clearLayers(); } });
document.addEventListener('click', async (e) => {            // buttons inside the popup
  const b = e.target.closest && e.target.closest('.sel-popup [data-act]'); if (!b) return; e.preventDefault();
  try { await ACT[b.dataset.act](b); } catch (err) { toast(err.message, 5000); }
  refreshSel();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.id === 'name-input') { const b = document.querySelector('.sel-popup [data-act=set-name]'); if (b) b.click(); } });

function nearestVertex(f, c) {                               // the point of a street line that is nearest to a place
  const g = f.geometry; const lines = g.type === 'MultiLineString' ? g.coordinates : [g.coordinates]; let best = null, bd = 1e18;
  lines.forEach((ln) => ln.forEach(([x, y]) => { const d = (x - c.lng) ** 2 + (y - c.lat) ** 2; if (d < bd) { bd = d; best = L.latLng(y, x); } }));
  return best;
}
function selectStreet(id, keepView, ll) {
  const f = streetById(id); if (!f) return;
  G.hl.clearLayers();
  const l = L.geoJSON(f, { style: { color: '#fff', weight: 10, opacity: .8 }, interactive: false }).addTo(G.hl); G.hl.addTo(map);
  if (keepView) {
    S.sel = { type: 'street', id, ll: ll || L.latLng(featureMid(f)) };
    renderPanel(); refreshSel(); return;
  }
  const target = l.getBounds().pad(0.6);                      // chosen from a list: show the street, then open the popup on it where it is in view
  S.sel = { type: 'street', id, ll: nearestVertex(f, target.getCenter()) };
  renderPanel();
  map.once('moveend', () => { if (S.sel && S.sel.id === id) refreshSel(); });
  map.fitBounds(target, { maxZoom: 18 });
  setTimeout(() => { if (S.sel && S.sel.id === id && !S.selPopup) refreshSel(); }, 900);          // the view did not need to move
}

/* ---------------------------------------------------------------- edit streets tab: add streets from a file, delete edges */
/* An edit that cannot be applied any more is never left out silently: say so, with the edit numbers (see /history). */
function warnLostEdits(roads) {
  const lost = roads?.report?.lost_edits || [], key = lost.map((l) => `${l.event}:${l.ref}`).join(',');
  if (key && key !== S.lostEdits) toast(I18n.msg`${lost.length} road edits could not be applied (edit ${[...new Set(lost.map((l) => l.event))].join(', ')}). Undo the last edit and check the map.`, 12000);
  S.lostEdits = key;
}
async function loadRoads(prepareSwap = false, expectedRevision = null) {
  if (!prepareSwap) {
    const roads = await api('/roads');
    warnLostEdits(roads);
    // A geometry replay can take long enough for another road to be saved meanwhile.  Never let that older response
    // replace the newer optimistic trace already visible on the map.
    if (expectedRevision === null || S.rev === expectedRevision) S.roads = roads;
    return roads;
  }
  const [roads, base, components] = await Promise.all([api('/roads'), api('/base/streets'), api('/base/components')]);
  S.roads = roads; S.baseStreets = base; S.components = components; warnLostEdits(roads);
}
const NEWC = (i) => `hsl(${Math.round((i * 137.5) % 360)},85%,52%)`;               // a different colour for every new street
const NODE_STYLE = {
  connected: { radius: 9, color: '#004d40', weight: 4, fillColor: '#00e5ff', fillOpacity: 1 },
  free: { radius: 6, color: '#000', weight: 1.5, fillColor: '#ff6d00', fillOpacity: 1 },
  inner: { radius: 3, color: '#000', weight: 1, fillColor: '#bdbdbd', fillOpacity: 1 },
};
function nodeKind(p) { return p.state === 'connected' ? 'connected' : (p.state === 'free' || p.state === 'pending_edge') && p.degree === 1 ? 'free' : 'inner'; }
function clearStage() { S.stage = null; S.sel = null; setMode(null); }
async function previewStage(first) {
  const st = S.stage;
  const body = { filename: st.filename, connections: st.connections, keep: st.keep };
  if (first) body.content_b64 = st.b64; else body.features = st.features;
  const r = await api('/roads/preview', body); st.features = r.features; st.pv = r; st.b64 = undefined;
  return r;
}
function drawStageLayers() {
  const pv = S.stage.pv;
  const cmap = {}; S.stage.features.forEach((f, i) => { cmap[f.id] = NEWC(i); });
  L.geoJSON(pv.replaced, { style: { color: '#d50000', weight: 7, opacity: .9, dashArray: '2 8' }, interactive: true,
    onEachFeature: (f, l) => l.bindTooltip(`existing road replaced by the new one (${fmt(f.properties.old_length, 0)} m vs ${fmt(f.properties.new_length, 0)} m)`, { sticky: true }) }).addTo(G.roadEdges);
  L.geoJSON(pv.edges, { style: (f) => ({ color: cmap[f.properties.feature] || '#e040fb', weight: 5, opacity: .95 }),
    onEachFeature: (f, l) => l.bindTooltip(`new street ${esc(f.properties.name || '')}`, { sticky: true }) }).addTo(G.roadEdges);
  G.roadEdges.addTo(map);
  const sorted = [...pv.nodes.features].sort((a, b) => (nodeKind(a.properties) === 'connected') - (nodeKind(b.properties) === 'connected'));
  L.geoJSON({ type: 'FeatureCollection', features: sorted }, {
    pointToLayer: (f, ll) => L.circleMarker(ll, NODE_STYLE[nodeKind(f.properties)]),
    onEachFeature: (f, l) => {
      const p = f.properties, k = nodeKind(p);
      l.bindTooltip(k === 'connected' ? `connection node (${p.to}${p.manual ? ', by hand' : ', automatic'}) - click to edit` : k === 'free' ? 'end not connected - click to connect it' : 'node - click to edit');
      l.on('click', (e) => { if (S.mode) return; L.DomEvent.stopPropagation(e); S.sel = { type: 'node', key: p.key, props: p, ll: e.latlng }; renderPanel(); refreshSel(); });
    },
  }).addTo(G.roadNodes); G.roadNodes.addTo(map);
  try { const b = L.geoJSON(pv.edges).getBounds(); if (b.isValid() && S.stage.fit) { map.fitBounds(b.pad(0.2)); S.stage.fit = false; } } catch (e) { /* ignore */ }
}
async function drawDeleteLayers() {
  const epoch = S.renderEpoch;
  const [e, current] = await Promise.all([api('/edges'), api('/roads/geometry')]);
  if (epoch !== S.renderEpoch || !S.del) return;
  S.edgeData = {...e,edges:current.edges}; const sel = S.del.sel;
  const style = (f) => (sel.has(f.properties.ref) ? { color: '#ff1744', weight: 7, opacity: 1 } : { color: '#ffd54f', weight: 3.5, opacity: .9 });
  const tip = (f) => `${esc(f.properties.name || 'edge')} · ${f.properties.street_id !== null && f.properties.street_id !== undefined ? 'street ' + f.properties.street_id + ' · ' : ''}${fmt(f.properties.length_m ?? f.properties.length, 0)} m · click to select`;
  const toggle = (ref) => { if (sel.has(ref)) sel.delete(ref); else sel.add(ref); drawTab(); };
  L.geoJSON(e.removed, { style: { color: '#9e9e9e', weight: 4, dashArray: '4 6', opacity: .9 },
    onEachFeature: (f, l) => { l.bindTooltip('deleted - click to bring it back', { sticky: true });
      l.on('click', async (ev) => { L.DomEvent.stopPropagation(ev); await api('/edges/restore', { edges: [f.properties.ref] }); await afterEdit(); toast('Edge restored'); drawTab(); }); } }).addTo(G.roadEdges);
  L.geoJSON(current.edges, { style, onEachFeature: (f, l) => { l.bindTooltip(tip(f), { sticky: true }); l.on('click', (ev) => { L.DomEvent.stopPropagation(ev); toggle(f.properties.ref); }); } }).addTo(G.base);
  G.base.addTo(map); G.roadEdges.addTo(map);
}
const FILE_COLOR = (i) => `hsl(${Math.round((i * 137.5 + 20) % 360)},80%,48%)`;
const fileIndex = (id) => {                                    // files with the same name (all the roads drawn by hand) share one colour
  const imps = S.project.roads.imports || [], i = imps.findIndex((x) => String(x.id) === String(id));
  return i < 0 ? i : imps.findIndex((x) => x.file === imps[i].file);
};
function roadsLegend() {
  if (S.roadColor !== 'file') return '';
  return legend([['#9e9e9e', 'downloaded network (OSM)'], ...(S.project.roads.imports || []).map((x, i) => [FILE_COLOR(fileIndex(x.id)), esc(x.file), i]).filter(([, t, i], k, a) => a.findIndex((y) => y[1] === t) === k).map(([c, t]) => [c, t])], true);
}
function drawRoads() {
  const epoch = S.renderEpoch;
  if (S.join) { drawJoinLayers(); return; }
  if (S.draw) { drawDrawLayers(); return; }
  if (S.cut) { drawCutLayers(); return; }
  if (S.reshapePick) { drawReshapeChoices(); return; }
  if (S.stage && S.stage.pv) {
    api('/base/streets').then((b) => { S.baseStreets = b; if (S.tab !== 'roads' || epoch !== S.renderEpoch) return; G.base.clearLayers(); L.geoJSON(b, { style: { color: '#ffd54f', weight: 2, opacity: .7 }, interactive: false }).addTo(G.base); G.base.addTo(map); });
    drawStageLayers(); return;
  }
  if (S.del) { drawDeleteLayers(); return; }
  const byFile = S.roadColor === 'file';
  const paintBase = (b) => {
    if (S.tab !== 'roads' || epoch !== S.renderEpoch) return;
    G.base.clearLayers();
    L.geoJSON(b, { style: (f) => (byFile ? (f.properties.file ? { color: FILE_COLOR(fileIndex(f.properties.file)), weight: 4, opacity: .95 } : { color: '#9e9e9e', weight: 2, opacity: .85 }) : { color: '#ffd54f', weight: 2, opacity: .85 }), interactive: false }).addTo(G.base);
    G.base.addTo(map);
  };
  const paintComponents = (c) => {                              // the parts cut off from the main network: red dashed
    if (S.tab !== 'roads' || epoch !== S.renderEpoch) return;
    L.geoJSON(c.edges, { style: { color: '#d50000', weight: 7, opacity: .9, dashArray: '2 9', lineCap: 'round' }, onEachFeature: (f, l) => {
      const id = f.properties.part, pt = c.parts.find((x) => x.id === id) || { edges: '?', length_m: 0 };
      l.bindTooltip(`separate part ${id}: not connected to the main network - click for options`);
      l.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        const box = document.createElement('div');
        box.innerHTML = I18n.html`<strong>Separate part ${id}</strong><br>${pt.edges} edges &middot; ${fmt(pt.length_m)} m<br><span class="muted">Not connected to the main network: draw or prolong a road to connect it, or delete it.</span><div class="row"><button class="danger">Delete this part</button></div>`;
        box.querySelector('button').addEventListener('click', async () => { map.closePopup(); await ACT['del-part']({ dataset: { part: id } }); });
        L.popup().setLatLng(e.latlng).setContent(box).openOn(map);
      });
    } }).addTo(G.roadEdges);
    G.roadEdges.addTo(map);
  };
  if (S.baseStreets) paintBase(S.baseStreets);
  else api('/base/streets').then((b) => { S.baseStreets = b; paintBase(b); }).catch(() => {});
  if (S.components) paintComponents(S.components);
  else api('/base/components').then((c) => { S.components = c; paintComponents(c); if (S.tab === 'roads') renderPanel(); }).catch(() => {});
  const r = S.roads; if (!r) return;
  (r.report?.uncertain_ends || []).forEach(p => L.marker([p.lat, p.lon], { icon: L.divIcon({ className: 'uncertain-end', html: '?', iconSize: [22, 22] }) }).bindTooltip('Path unclear beyond this endpoint — needs review').addTo(G.roadNodes));
  if (r.reviews?.features?.length) L.geoJSON(r.reviews, { style: { color: '#ff6d00', weight: 9, opacity: .9, dashArray: '4 7', lineCap: 'round' },
    onEachFeature: (f, layer) => layer.bindTooltip(`Unclear road portion · ${fmt(f.properties.selected_m, 1)} m · ${esc(f.properties.note)}`)
  }).addTo(G.roadEdges);
  if (!byFile) L.geoJSON(r.edges, { style: { color: '#e040fb', weight: 5, opacity: .95 }, onEachFeature: (f, l) => l.bindTooltip(`new road ${esc(f.properties.name || '')} · street ${f.properties.street_id}`) }).addTo(G.roadEdges);
  G.roadEdges.addTo(map);
  L.geoJSON(r.nodes, {
    pointToLayer: (f, ll) => L.circleMarker(ll, NODE_STYLE[nodeKind(f.properties)]),
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindTooltip(p.state === 'connected' ? `connected (${p.to}${p.manual ? ', by hand' : ', automatic'})` : p.degree === 1 ? 'end not connected - click to connect it' : 'node');
      l.on('click', (e) => { L.DomEvent.stopPropagation(e); if (p.degree === 1 || p.state !== 'connected') { S.sel = { type: 'node', key: p.key, props: p, ll: e.latlng }; renderPanel(); refreshSel(); } });
    },
  }).addTo(G.roadNodes); G.roadNodes.addTo(map);
  try { const b = L.geoJSON(r.edges).getBounds(); if (b.isValid() && !S.fittedRoads) { map.fitBounds(b.pad(0.2)); S.fittedRoads = true; } } catch (e) { /* ignore */ }
}

/* ---------------------------------------------------------------- addresses tab */
const HOUSE = { ok: '#2e7d32', pending_name: '#f9a825', no_name: '#d50000', no_street: '#7b1fa2' };
/* the important points of the community (reference points) are squares, buildings are circles */
/* an emoji for every kind of reference point on the Addresses tab: school, health, church, chiefdom, square, shop ... */
const EMOJI_RULES = [[/lyc[ée]e|[ée]cole|school|coll[èe]ge|universit/i, '🏫'], [/sant[ée]|health|h[ôo]pital|clinique|\bcsi\b|\bcma\b|pharmac|healthcare/i, '🏥'],
  [/[ée]glise|church|paroisse|mission|cath[ée]drale|temple|mosqu/i, '⛪'], [/lieu sacr|sacr[ée]|sacred/i, '🛕'], [/place |square|plaza|\bplace\b/i, '🌳'], [/h[ôo]tel/i, '🏨'], [/march[ée]|market|boutique|shop|alimentation|commerce|magasin/i, '🛒'], [/stade|stadium/i, '🏟️'],
  [/eau|water|puits|forage|fontaine/i, '💧'], [/carrefour|crossroad|intersection/i, '🔀'], [/village|hamlet|town|ville/i, '🏘️'],
  [/foyer|salle|mairie|sous-pr[ée]fecture|poste|police|gendarmerie|public|facility/i, '🏛️']];
function pointEmoji(name, kind) {
  if (/^(chefferie|chiefferie|palais)\b|\b(chefferie|chiefferie|chiefdom)\s+(de|du|of)\b|^chiefdom\b/i.test(name || '') && !/[ée]cole|school|lyc[ée]e|coll[èe]ge/i.test(name)) return '🪶';   // only places named as a chiefdom
  const t = `${kind || ''} ${name || ''}`; for (const [re, em] of EMOJI_RULES) if (re.test(t)) return em; return '📍'; }
function emojiMarker(ll, name, kind, border) {
  return L.marker(ll, { icon: L.divIcon({ className: '', html: I18n.html`<div class="emo" style="border-color:${border || '#555'}">${pointEmoji(name, kind)}</div>`, iconSize: [0, 0] }), keyboard: false });
}
function sqMarker(ll, color) {
  color = '#ffffff';                                          // reference points are white squares: no colour of a use or an address status
  return L.marker(ll, { icon: L.divIcon({ className: '', html: I18n.html`<div class="sqpt" style="background:${color}"></div>`, iconSize: [0, 0] }), keyboard: false });
}
/* every surveyed building is visible on the Addresses tab, also before the addresses are computed (coloured by use) */
const USE = { residential: '#43a047', commercial: '#fb8c00', industrial: '#6d4c41', office: '#1e88e5', public: '#8e24aa', unknown: '#9e9e9e' };
function pointInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (((yi > lat) !== (yj > lat)) && lon < ((xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
function pointInArea(lon, lat, geometry) {
  if (!geometry) return false;
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
  return polygons.some((polygon) => pointInRing(lon, lat, polygon[0]) && !polygon.slice(1).some((hole) => pointInRing(lon, lat, hole)));
}
function buildingQuartier(lon, lat, recorded) {
  const feature = quartierFeatures().find((q) => pointInArea(lon, lat, q.geometry));
  return feature ? { name: feature.properties.name, code: feature.properties.code || '', recorded: recorded || '' }
    : { name: recorded || '', code: '', recorded: recorded || '' };
}
function buildingTooltip(feature, latlng) {
  const p = feature.properties || {}, lon = feature.geometry?.type === 'Point' ? feature.geometry.coordinates[0] : latlng.lng;
  const lat = feature.geometry?.type === 'Point' ? feature.geometry.coordinates[1] : latlng.lat;
  const quartier = buildingQuartier(lon, lat, p.district), rows = [];
  const add = (label, value) => { if (value !== null && value !== undefined && value !== '') rows.push(`<tr><th>${esc(I18n.t(label))}</th><td>${esc(String(value))}</td></tr>`); };
  add('Country', 'Cameroon');
  add('Project', S.project?.name || '');
  add('Quartier', quartier.name);
  add('Quartier trigram', quartier.code);
  if (quartier.recorded && quartier.recorded.trim().toLowerCase() !== quartier.name.trim().toLowerCase()) add('Recorded quartier', quartier.recorded);
  add('Survey record type', p.survey_type || I18n.t('Legacy record — type not recorded'));
  add('Use', p.use);
  add('Place name', p.name);
  add('Service', p.service);
  add('Residents', p.residents);
  add('Generated address', p.address);
  add('Address ID', p.address_id);
  add('Coordinates', `${Number(lat).toFixed(6)}, ${Number(lon).toFixed(6)}`);
  add('Internal record ID', p.building_id);
  return `<div class="building-tip"><table>${rows.join('')}</table></div>`;
}
async function drawRawBuildings() {
  if (!S.project.has.buildings) return;
  if (!S.rawBuildings) S.rawBuildings = await api('/layers/buildings');
  if (S.tab !== 'addresses' || S.addresses) return;
  renderPanel(); G.houses.clearLayers();
  L.geoJSON(S.rawBuildings, {
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4, color: '#000', weight: 1, fillColor: USE[f.properties.use] || USE.unknown, fillOpacity: .95 }),
    onEachFeature: (f, l) => { const ll = f.geometry?.type === 'Point' ? L.latLng(f.geometry.coordinates[1], f.geometry.coordinates[0]) : l.getBounds().getCenter();
      l.bindTooltip(() => buildingTooltip(f, ll), { sticky: true, className: 'building-data-tooltip' }); },
  }).addTo(G.houses);
  if (S.pointsData) L.geoJSON(S.pointsData, { pointToLayer: (f, ll) => emojiMarker(ll, f.properties.name, f.properties.kind),
    onEachFeature: (f, l) => l.bindTooltip(esc(f.properties.name || f.properties.kind || 'reference point'), { sticky: true }) }).addTo(G.houses);
  G.houses.addTo(map);
}
function drawAddresses() {
  map.removeLayer(G.points);                                   // the emoji replace the squares of the reference points here
  if (!S.pointRanks && S.project.has.points) loadPointRanks();
  if (S.network) { L.geoJSON(S.network.streets, { style: { color: '#fff', weight: 2, opacity: .55 }, interactive: false }).addTo(G.base); G.base.addTo(map); }
  const a = S.addresses;
  if (!a) { drawRawBuildings(); return; }
  L.geoJSON(a.houses, {
    pointToLayer: (f, ll) => (f.properties.use === 'reference' ? emojiMarker(ll, f.properties.name, f.properties.info, HOUSE[f.properties.status] || '#999') : L.circleMarker(ll, { radius: 5, color: '#000', weight: 1, fillColor: HOUSE[f.properties.status] || '#999', fillOpacity: .95 })),
    style: (f) => ({ color: HOUSE[f.properties.status] || '#999', weight: 2, fillOpacity: .35 }),
    onEachFeature: (f, l) => { const p = f.properties, ll = f.geometry?.type === 'Point' ? L.latLng(f.geometry.coordinates[1], f.geometry.coordinates[0]) : l.getBounds().getCenter();
      l.bindTooltip(() => buildingTooltip(f, ll), { sticky: true, className: 'building-data-tooltip' });
      l.on('click', (e) => { if (S.mode) return; L.DomEvent.stopPropagation(e); S.sel = { type: 'house', props: p, ll: e.latlng }; drawAccess(p); renderPanel(); refreshSel(); }); },
  }).addTo(G.houses); G.houses.addTo(map);
  L.geoJSON(a.signs, { pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 6, color: '#fff', weight: 2, fillColor: '#1565c0', fillOpacity: 1 }),
    onEachFeature: (f, l) => l.bindPopup(() => signHtml(f.properties), { maxWidth: 360, minWidth: 260 }) }).addTo(G.signs);
  updateSigns();
}
/* the popup of a street sign: a sketch of the roads at the intersection and the sign boards: a blue square board per street, a green arrow board per reference point */
const kmText = (m) => `${Math.max(0.1, Math.round(m / 100) / 10).toFixed(1)} km`;      // always the number, then km
function signHtml(p) {
  ensureColors();
  const size = 220, c = size / 2, r = 70;
  let svg = I18n.html`<svg width="${size}" height="${size}" class="junction-svg">`;
  const letters = {};                                          // one letter per street, the same on the sketch and on its sign board
  [...(p.spokes || []).map((x) => x.id), ...(p.label_ids || [])].forEach((id) => { if (!(id in letters)) letters[id] = String.fromCharCode(65 + Object.keys(letters).length % 26); });
  const seen = new Set();
  (p.spokes || []).forEach((s) => {
    const a = s.bearing * Math.PI / 180, col = hue(s.id), x = c + r * Math.sin(a), y = c - r * Math.cos(a);
    svg += I18n.html`<line x1="${c}" y1="${c}" x2="${x}" y2="${y}" stroke="${col}" stroke-width="5" stroke-linecap="round"/>`;
    if (!seen.has(s.id + ':' + Math.round(s.bearing / 20))) { seen.add(s.id + ':' + Math.round(s.bearing / 20)); svg += I18n.html`<text x="${c + (r + 14) * Math.sin(a)}" y="${c - (r + 14) * Math.cos(a)}" fill="${col}" font-size="15" font-weight="700" text-anchor="middle" dominant-baseline="middle">${letters[s.id]}</text>`; }
  });
  svg += I18n.html`<circle cx="${c}" cy="${c}" r="4" fill="#fff"/></svg>`;
  const boards = (p.labels || []).map((t, i) => { const id = (p.label_ids || [])[i]; return id === undefined ? I18n.html`<div class="board">${esc(t)}</div>` : I18n.html`<div class="board"><span class="sid" style="background:${hue(id)}">${letters[id]}</span>${esc(t)}</div>`; }).join('');
  const arrows = (p.pois || []).map((q) => I18n.html`<div class="arrow-board" title="rank ${q.rank}"><span class="arr" style="transform:rotate(${q.bearing - 90}deg)">&#10148;</span><span>${esc(q.name)}${q.distance_m ? I18n.html` <small>${kmText(q.distance_m)}</small>` : ''}</span></div>`).join('');
  return I18n.html`<div class="junction signbox"><div class="muted">Intersection of ${p.labels.length} street sign${p.labels.length === 1 ? '' : 's'}${(p.pois || []).length ? ` and ${p.pois.length} reference point${p.pois.length === 1 ? '' : 's'}` : ''}</div><div style="text-align:center">${svg}</div><div class="boards">${boards}${arrows}</div></div>`;
}
function updateSigns() { if (S.tab !== 'addresses') return; if (map.getZoom() >= 16) G.signs.addTo(map); else map.removeLayer(G.signs); }
map.on('zoomend', updateSigns);
function drawAccess(p) {
  G.access.clearLayers();
  if (!p) { G.access.addTo(map); return; }
  const f = S.addresses && S.addresses.houses.features.find((x) => x.properties.building_id === p.building_id);
  if (f) {
    const c = L.geoJSON(f).getBounds().getCenter();
    const rl = p.access_lat ? [p.access_lat, p.access_lon] : p.road_lat ? [p.road_lat, p.road_lon] : null;
    if (rl) {                                                  // the point of the road the number is taken from
      L.polyline([[c.lat, c.lng], rl], { color: '#6a1b9a', dashArray: '5 5', weight: 3 }).addTo(G.access);
      L.circleMarker(rl, { radius: 7, color: '#6a1b9a', weight: 3, fillColor: '#ce93d8', fillOpacity: 1 }).bindTooltip('point of the road used for the number').addTo(G.access);
    }
    if (p.azimuth !== null && p.azimuth !== undefined && p.azimuth === p.azimuth) {      // arrow: the direction from the street to the door, drawn through the building
      const svg = I18n.html`<svg width="80" height="80" viewBox="-40 -40 80 80" style="overflow:visible"><g transform="rotate(${p.azimuth})">
        <line x1="0" y1="18" x2="0" y2="-16" stroke="#fff" stroke-width="8" stroke-linecap="round"/><polygon points="0,-34 -11,-14 11,-14" fill="#fff" stroke="#fff" stroke-width="6" stroke-linejoin="round"/>
        <line x1="0" y1="18" x2="0" y2="-16" stroke="#d50000" stroke-width="4" stroke-linecap="round"/><polygon points="0,-34 -11,-14 11,-14" fill="#d50000" stroke="#d50000" stroke-width="1" stroke-linejoin="round"/>
        <circle cx="0" cy="18" r="4" fill="#d50000" stroke="#fff" stroke-width="2"/></g></svg>`;
      L.marker(c, { icon: L.divIcon({ className: '', html: I18n.html`<div style="transform:translate(-50%,-50%)">${svg}</div>`, iconSize: [0, 0] }), interactive: false }).bindTooltip(`azimuth ${Math.round(p.azimuth)}\u00b0`).addTo(G.access);
    }
  }
  G.access.addTo(map);
}

/* ---------------------------------------------------------------- panels */
const stale = () => (S.polling ? I18n.htmlText('<p><span class="badge warn">updating...</span></p>') : '');
function legend(items, dots) { return I18n.html`<div class="legend">${items.map(([c, t, sq]) => I18n.html`<span><i class="${dots ? 'dot' : ''}${sq ? ' sq' : ''}" style="background:${c}"></i>${t}</span>`).join('')}</div>`; }
function bar(parts) { const tot = parts.reduce((s, p) => s + p[0], 0) || 1; return I18n.html`<div class="bar">${parts.map(([n, c, t]) => I18n.html`<span title="${t}: ${n}" style="width:${100 * n / tot}%;background:${c}"></span>`).join('')}</div>`; }

function renderPanel() {
  const P = $('#panel'), p = S.project;
  const headings = {roads:['Prepare the roads','Follow visible paths, keep junctions connected, and flag uncertain ends.'],ids:['Check street identity','Select a junction to split or group segments into a street.'],names:['Give places a name','Name priority streets so smaller streets can inherit a clear address.'],addresses:['Review house access','Select a building to check its address and choose the correct road access.']};
  const heading=headings[S.tab];
  $('#workspace-title').textContent=I18n.t(heading[0]); $('#workspace-description').textContent=I18n.t(heading[1]);
  if (!p.reference) { P.innerHTML = I18n.htmlText('<h3>Choose the reference point</h3><p>Click the map near the node the numbering starts from (for example a crossroads).</p>'); return; }
  P.innerHTML = { roads: panelRoads, ids: panelIds, names: panelNames, addresses: panelAddresses }[S.tab]();
  AuthUI.applyPermissions();
}

/* what is selected on the map (a street, a house, a node of a new road) is shown and edited in a popup on the map, not in the side panel */
function selectedStreetBox() {
  return I18n.html`<p class="muted">Click a street${S.tab === 'ids' ? ' or a white node' : ''} on the map: a popup opens.</p>`;
}
const tri = (v, mixed) => (mixed ? I18n.html`<option value="" selected disabled>${I18n.t('partly: choose to set all of it')}</option>` : '')
  + [['null', 'unknown'], ['true', 'yes'], ['false', 'no']].map(([k, t]) => I18n.html`<option value="${k}" ${!mixed && String(v === undefined ? null : v) === k ? 'selected' : ''}>${I18n.t(t)}</option>`).join('');
function streetBox(editable) {
  if (!S.sel || S.sel.type !== 'street') return '';
  const f = streetById(S.sel.id); if (!f) return '';
  const p = f.properties; const assigned = S.project.names[String(p.original)];
  const parts = S.network.streets.features.filter((g) => g.properties.original === p.original);
  let h = I18n.html`<h3>Street ${p.id} <span class="badge">${esc(p.status)}</span></h3>
    <p><strong>${esc(p.display || '(no name yet)')}</strong></p>
    <table><tr><td>original id</td><td>${p.original}${parts.length > 1 ? ` &middot; part ${p.part + 1} of ${parts.length}` : ''}</td></tr>
    <tr><td>length</td><td>${fmt(p.length)} m &middot; rank ${p.rank} (${esc(p.highway)})</td></tr>
    <tr><td>distance to reference</td><td>${fmt(p.d0)} - ${fmt(p.d1)} m</td></tr>
    ${p.parent ? I18n.html`<tr><td>derived from</td><td>street ${p.parent}${p.root && p.root !== p.parent ? ` (main street ${p.root})` : ''}</td></tr>` : ''}</table>`;
  h += I18n.html`<div class="row attrs"><select class="attr-edit" data-attr="rank" data-orig="${p.original}" ${parts.length > 1 ? `data-part="${p.part}"` : ''} title="Street rank">${RANK_NAMES.map((t, i) => I18n.html`<option value="${i}" ${p.rank === i ? 'selected' : ''}>${I18n.t(t)}</option>`).join('')}</select>
    <label>drivable <select class="attr-edit" data-attr="drivable" data-orig="${p.original}" ${parts.length > 1 ? `data-part="${p.part}"` : ''}>${tri(p.drivable, p.drivable_mixed)}</select></label>${p.drivable === false && !p.drivable_mixed ? I18n.html`<span class="muted">${I18n.t(NOT_DRIVABLE)}</span>` : ''}
    <label>paved <select class="attr-edit" data-attr="paved" data-orig="${p.original}" ${parts.length > 1 ? `data-part="${p.part}"` : ''}>${tri(p.paved, p.paved_mixed)}</select></label>
    <label>gives addresses <select class="attr-edit" data-attr="addresses" data-orig="${p.original}" ${parts.length > 1 ? `data-part="${p.part}"` : ''}>${[['true', 'yes'], ['false', 'no']].map(([k, t]) => I18n.html`<option value="${k}" ${String(p.addresses !== false) === k ? 'selected' : ''}>${I18n.t(t)}</option>`).join('')}</select></label></div>
    ${p.addresses === false ? I18n.htmlText('<p class="muted">Small path: its houses take the number where it leaves the street, with a letter (230A, 230B). Compute the addresses to apply.</p>') : ''}${parts.length > 1 ? I18n.htmlText('<p class="muted">Applies to this part only.</p>') : ''}`;
  if (parts.length > 1) h += I18n.html`<p class="muted">Cut parts: ${parts.map((g) => I18n.html`<a href="#" data-act="select" data-id="${g.properties.id}">${g.properties.id}</a>`).join(', ')}</p>`;
  if (editable) {
    const dup = assigned && S.network.streets.features.some((g) => g.properties.original !== p.original && g.properties.name && g.properties.name.toLowerCase() === assigned.toLowerCase());
    h += I18n.html`<h3>Name of street ${p.original}${parts.length > 1 ? ' (all parts)' : ''}</h3>
      <input type="text" id="name-input" placeholder="Street name (empty = no name)" value="${esc((assigned === '0' ? '' : assigned) || (assigned === '0' ? '' : p.status === 'named' ? (parts.find((g) => g.properties.part === 0) || f).properties.name : ''))}">
      <div class="row"><button class="primary" data-act="set-name" data-id="${p.original}">Set name</button>
      ${assigned ? I18n.html`<button data-act="clear-name" data-id="${p.original}">Back to the OSM name</button>` : ''}<button class="danger" data-act="delete-name" data-id="${p.original}">Delete name</button></div>
      ${dup ? I18n.htmlText('<p><span class="badge warn">this name is already used by another street</span></p>') : ''}
      <p class="muted">Saved at once; the street ids update by themselves.</p>`;
  }
  return h;
}

function panelIds() {
  if (S.project.stale) return I18n.htmlText('<h3>Street types and IDs</h3><div class="warnbox"><strong>Pending road edits</strong><p>The current road geometry is shown in orange. Old IDs and colours are hidden because they no longer match it. Continue editing in step 1, or use Recompute IDs when your batch is ready.</p></div>');
  if (!S.network) return I18n.html`<h3>Street types and IDs</h3><p>Computing the street ids...</p>`;
  const st = S.network.stats, sg = S.network.streets.features.map((f) => f.properties);
  const cut = {}; sg.filter((p) => p.part > 0 || sg.some((q) => q.original === p.original && q.part > 0)).forEach((p) => { (cut[p.original] = cut[p.original] || []).push(p); });
  const cutRows = Object.entries(cut).slice(0, 60).map(([o, ps]) => I18n.html`<tr class="click" data-act="select" data-id="${ps[0].id}"><td>${o}</td><td>${ps.map((q) => q.id).join(', ')}</td><td>${esc(ps[0].name || '')}</td></tr>`).join('');
  const s = S.project.settings;
  return I18n.html`<h3>Street types and IDs</h3>${stale()}
  <h3>Colour by</h3><div class="row"><select id="color-mode">${[['id', 'street id'], ['distance', 'distance to the reference'], ['rank', 'street rank'], ['drivable', 'drivable'], ['paved', 'paved']].map(([v, t]) => I18n.html`<option value="${v}" ${S.idColor === v || (v === 'drivable' && S.idColor === 'access') ? 'selected' : ''}>${I18n.t(t)}</option>`).join('')}</select></div>${colourLegend()}
    <table><tr><td>streets</td><td><strong>${st.streets}</strong></td></tr><tr><td>original ids</td><td>${st.original_ids}</td></tr>
    <tr><td>new ids from cutting</td><td>${st.new_ids_from_cutting} (${st.cut_points} cut points)</td></tr></table>
    ${selectedStreetBox(false)}
    <details class="sec"><summary>Streets that were cut (${Object.keys(cut).length})</summary><table><tr><th>orig</th><th>ids</th><th>name</th></tr>${cutRows || I18n.htmlText('<tr><td colspan="3" class="muted">none</td></tr>')}</table></details>
    <details class="sec"><summary>Settings</summary>
      <p class="muted">Naming rules: highways, primary and secondary roads always need their own name; other roads may take one derived name (Voie 3 du xyz), never two levels (Voie 3/3 du xyz).</p>
      <p class="muted">Approved address rule: a house number represents metres from the street start; a branch prefix represents tens of metres.</p>
      <p>Metres per house number <input type="number" min="0.1" step="0.1" id="set-house" value="${s.house_step_m}"></p>
      <p>Metres per branch prefix <input type="number" min="0.1" step="0.1" id="set-branch" value="${s.branch_step_m}"></p>
      <p>Houses farther than (m) from a road get no address <input type="number" id="set-dist" value="${s.max_house_distance_m}"></p>
      <p><label><input type="checkbox" id="set-conn" ${s.connect_backbone ? 'checked' : ''}> named streets must connect to the reference through named streets</label></p>
      <button data-act="apply-settings">Apply settings</button></details>`;
}

function panelNames() {
  if (S.project.stale) return I18n.htmlText('<h3>Street names</h3><div class="warnbox"><strong>Pending road edits</strong><p>The current road geometry is shown in orange. Old street names and IDs are hidden because they may refer to roads that were moved, added or undone. Recompute IDs when your geometry batch is ready.</p></div>');
  if (!S.network) return I18n.html`<h3>Street names</h3><p>Computing the street ids...</p>`;
  const st = S.network.stats, sg = S.network.streets.features.map((f) => f.properties);
  const c = (k) => sg.filter((p) => p.status === k).length; const d1 = sg.filter((p) => p.status === 'derived' && p.level === 1).length, d2 = sg.filter((p) => p.status === 'derived' && p.level === 2).length;
  const proof = st.plan_optimal ? 'minimum proven on the final cut network' : 'feasible final plan; minimum not proven';
  const reduction = st.plan_reduced_by ? ` · ${st.plan_reduced_by} ${I18n.t(st.plan_reduced_by === 1 ? 'task removed by final optimisation' : 'tasks removed by final optimisation')}` : '';
  const rows = S.network.plan.slice(0, S.planAll ? 1e6 : 25).map((r) => I18n.html`<tr class="click" data-act="goto-plan" data-id="${r.street_ids.split(';')[0]}"><td>${r.order}</td><td>${r.street_id_original}</td><td>${fmt(r.length_m)}</td><td>${r.covers}</td><td>${esc(r.reason)}</td></tr>`).join('');
  return I18n.html`<h3>Street names</h3>${stale()}
        ${bar([[c('named'), STATUS.named, 'named'], [d1, STATUS.derived, 'derived 1'], [d2, STATUS.derived2, 'derived 2'], [c('planned'), STATUS.planned, 'to name'], [c('uncovered'), STATUS.uncovered, 'uncovered']])}
    ${legend([[STATUS.named, `named ${c('named')}`], [STATUS.derived, `x-name ${d1}`], [STATUS.derived2, `x-y-name ${d2}`], [STATUS.planned, `still to name ${st.to_be_named}`], ...(c('uncovered') ? [[STATUS.uncovered, `cannot be named ${c('uncovered')}`]] : []), ...(c('other') ? [[STATUS.other, `not a road ${c('other')}`]] : [])])}
    <p class="muted">${st.to_be_named} ${I18n.t(st.to_be_named === 1 ? 'street needs' : 'streets need')} a name (red). Naming them lets the others derive theirs.</p>
    <p class="muted">${I18n.t('Planner')}: ${esc(st.plan_method || 'unknown')} · ${I18n.t(proof)} · ${st.rounds} ${I18n.t('routing rounds')}${reduction}</p>
    ${selectedStreetBox(true)}
    <h3>Streets to name, in priority order</h3>
    <table><tr><th>#</th><th>street</th><th>m</th><th>covers</th><th>why</th></tr>${rows || I18n.htmlText('<tr><td colspan="5" class="muted">nothing left to name</td></tr>')}</table>
    ${S.network.plan.length > 25 ? I18n.html`<p><a href="#" data-act="plan-all">${S.planAll ? 'show fewer' : `show all ${S.network.plan.length}`}</a></p>` : ''}`;
}

function panelAddresses() {
  const a = S.addresses; const hasB = S.project.has.buildings;
  if (!hasB) return I18n.htmlText('<h3>Addresses</h3><p>This project has no houses to address (input/buildings.gpkg).</p>');
  const needsUpdate = !S.project.addresses_ready || S.project.addresses_stale;
  const update = needsUpdate ? (S.project.stale
    ? I18n.htmlText('<p><span class="badge warn">Road edits not applied</span> Recompute IDs first; switching tabs will not do it automatically.</p>')
    : I18n.htmlText('<p><button class="primary" data-act="compute-addresses">Compute addresses</button></p>')) : '';
  let h = I18n.html`<h3>House numbers, addresses and street signs</h3>${update}`;
  if (!a) {
    const fs = S.rawBuildings ? S.rawBuildings.features : [], n = {}; fs.forEach((f) => { const u = f.properties.use || 'unknown'; n[u] = (n[u] || 0) + 1; });
    return h + I18n.html`<p>Addresses have not been computed for the current data. All ${fs.length || ''} surveyed buildings are shown, coloured by use.</p>` + legend([...Object.keys(USE).filter((u) => n[u]).map((u) => [USE[u], `${u} ${n[u]}`]), ...(S.pointsCount ? [['#ffffff', `reference points ${S.pointsCount} (emoji by type)`, true]] : [])], true);
  }
  const s = a.stats;
  h += bar([[s.addressed, HOUSE.ok, 'addressed'], [s.pending_name, HOUSE.pending_name, 'street still to be named'], [s.no_name, HOUSE.no_name, 'no name'], [s.no_street, HOUSE.no_street, 'no road']]);
  h += legend([[HOUSE.ok, `address ${s.addressed}`], [HOUSE.pending_name, `street to be named ${s.pending_name}`], [HOUSE.no_name, `no name ${s.no_name}`], [HOUSE.no_street, `too far from a road ${s.no_street}`], ['#ffffff', `reference points ${a.houses.features.filter((f) => f.properties.use === 'reference').length} (emoji by type)`, true]], true);
  h += I18n.html`<p class="muted">${s.houses} houses &middot; ${s.signs} street signs (blue) &middot; ${s.manual_road_points} road points chosen by hand</p>
    <label for="addr-search"><b>Search</b></label><input type="text" id="addr-search" placeholder="Address, family name or survey id (e.g. TCK 0575, HIE-I022)"><div id="addr-results"></div>
    <details class="sec"><summary>Reference points on the street signs${S.pointRanks ? ` (${S.pointRanks.length})` : ''}</summary>
      <p class="muted">Rank = how important a point is for the signs.</p>
      <table>${(S.pointRanks || []).map((q) => I18n.html`<tr><td class="click" data-act="goto-point" data-lat="${q.lat}" data-lon="${q.lon}">${esc(q.name || q.info)}</td><td>${ptRankSelect(q.id, q.rank)}</td></tr>`).join('') || I18n.htmlText('<tr><td class="muted">loading...</td></tr>')}</table></details>`;
  const rg = a.register || { approved: 0, retired: 0, changed: 0 }, area = S.activeArea;
  h += I18n.html`<details class="sec" open><summary>Register: validated addresses and their changes</summary>
    <p>${rg.approved} validated &middot; ${rg.retired} retired${rg.changed ? I18n.html` &middot; <span class="badge warn">${rg.changed} changes to validate</span>` : ''}</p>
    <p class="muted">A validated address is the one on the plaque. When a road edit would change it, the change waits here; once validated, the family is on the list to inform (before / after, name, phone, position).</p>
    <div class="row">${area ? I18n.html`<button data-act="approve-area" data-id="${esc(area)}">Validate all addresses in ${esc(area)}</button>` : I18n.htmlText('<span class="muted">Choose a work area to validate its addresses together.</span>')}
      ${rg.changed ? I18n.html`<button data-act="validate-changes">Validate the ${rg.changed} changes</button>` : ''}</div>
    <div class="row"><a class="btn" href="api/register.csv">Download the register (CSV)</a>${!window.AuthUI || AuthUI.can('admin') ? I18n.htmlText('<a class="btn" href="api/register/changes.csv">Families to inform (CSV)</a>') : ''}</div></details>`;
  h += I18n.htmlText('<p class="muted">Click a building to see its address, side of the road and road point.</p>');
  return h;
}

const QUARTIER_NAMES = ['Babong', 'Badenla', 'Balafi', 'Balatchie', 'Bamendjo', 'Bandja', 'Bankwop', 'Bano', 'Djeugne', 'Fangam', 'Fotouni', 'Hiela',
  'Kouotchack', 'Lassié', 'Mbeum', 'Mving', 'Ngonfet', "Nguaka'am", 'Song', 'Tcham', 'Tchikong', 'Tchisso', 'Tchouno', 'Toukong', 'Demkwouo'];   // Overview Abbreviations
const PT_RANKS = ['0 not on the signs', '1 landmark', '2 important', '3 local'];
const ptRankSelect = (id, v) => I18n.html`<select class="pt-rank" data-id="${esc(id)}">${PT_RANKS.map((t, i) => I18n.html`<option value="${i}" ${v === i ? 'selected' : ''}>${I18n.t(t)}</option>`).join('')}</select>`;
function houseBox() {
  if (!S.sel || S.sel.type !== 'house') return '';
  const p = S.sel.props, row = (k, v) => (v === null || v === undefined || v === '' ? '' : I18n.html`<tr><td>${esc(I18n.t(k))}</td><td>${esc(I18n.t(String(v)))}</td></tr>`);
  const az = p.azimuth !== null && p.azimuth !== undefined && p.azimuth === p.azimuth ? `${Math.round(p.azimuth)}\u00b0` : null;
  const admin = !window.AuthUI || AuthUI.can('admin');
  S.households = S.households || {};
  const hh = S.households[p.building_id];
  if (admin && hh === undefined && p.use !== 'reference') {                 // private survey details: fetched for administrators only
    S.households[p.building_id] = null;
    api(`/households/${encodeURIComponent(p.building_id)}`).then((r) => { S.households[p.building_id] = r; renderPanel(); }).catch(() => { S.households[p.building_id] = false; renderPanel(); });
  }
  return I18n.html`<h3 class="plate">${esc(p.plate || p.address || 'no address')}</h3>
    <details class="sec" open><summary>For the plaque and the address card</summary><table>
      ${row('quartier', p.quartier_code ? `${p.district || ''} (${p.quartier_code})` : p.district ? `${p.district}: not in the catalogue` : null)}
      ${row('name on the plaque', p.plaque_name || (p.use === 'reference' ? null : 'missing (no family name in the survey)'))}
      ${row('address', p.plate || (p.number ? 'incomplete (quartier without trigram)' : null))}
      ${row('street part', p.street_code)}${row('house part', p.number)}
      ${row('written address', p.address)}${row('survey address id', p.address_id)}
      ${hh ? I18n.html`${row('contact (private)', hh.contact_name)}${row('phone (private)', hh.contact_phone || hh.commerce_phone || hh.public_phone)}${row('persons', hh.persons_count)}` : ''}
    </table>${admin && hh === false && p.use !== 'reference' ? I18n.htmlText('<p class="muted">No survey record imported for this building.</p>') : ''}
    ${p.use !== 'reference' ? I18n.html`<div class="row"><select id="house-quartier">${['', ...QUARTIER_NAMES].map((q) => I18n.html`<option value="${esc(q)}" ${q === (p.quartier_code ? p.district : '') ? 'selected' : ''}>${esc(q || I18n.t('as in the survey'))}</option>`).join('')}</select>
      <button data-act="set-quartier" data-id="${esc(p.building_id)}">Correct the quartier</button></div>${p.survey_district && p.survey_district !== p.district ? I18n.html`<p class="muted">Survey wrote: ${esc(p.survey_district)}</p>` : ''}` : ''}</details>
    <table>${row('street', p.street ? `${p.street} (id ${p.street_id})` : p.street_id !== null && p.street_id !== undefined ? `id ${p.street_id}, no name yet` : null)}
      ${row('side', p.side ? `${p.side}${p.side_source === 'azimuth' ? ' (from the azimuth)' : p.side_source === 'path' ? ' (where its path leaves the street)' : ' (from the position)'}` : null)}${row('azimuth', az)}
      ${p.via_path !== null && p.via_path !== undefined ? row('reached by', `path ${p.via_path} (gives no addresses)`) : ''}
      ${row('register', p.register_status === 'approved' ? `validated${p.approved_at ? ' ' + String(p.approved_at).slice(0, 10) : ''}` : p.register_status === 'retired' ? 'retired' : 'draft (not validated)')}${row('internal id', p.code)}
      ${p.use === 'reference' ? I18n.html`<tr><td>sign rank</td><td>${ptRankSelect(p.building_id, p.sign_rank)}</td></tr>` : ''}${row('use', p.use)}${row('name', p.name)}${row('residents', p.residents)}${row('road point', p.source === 'manual' ? 'chosen by hand' : p.road_lat ? 'nearest road (purple)' : null)}${row('status', p.status)}</table>
    ${p.changed ? I18n.html`<p><span class="badge warn">Change to validate</span> The map now gives ${esc(p.computed_plate || p.computed_address || 'no address')}. The validated address stays until you validate the change; the family is then on the list to inform.</p>` : ''}
    <div class="row"><button data-act="pick-access" data-id="${esc(p.building_id)}">Choose the road point</button>
    ${p.source === 'manual' ? I18n.html`<button class="danger" data-act="clear-access" data-id="${esc(p.building_id)}">Nearest road</button>` : ''}</div>
    ${p.number ? I18n.html`<div class="row">${p.register_status !== 'approved' && p.plate && p.use !== 'reference' ? I18n.html`<button class="primary" data-act="approve-house" data-id="${esc(p.building_id)}">Validate this address</button>` : ''}
      ${p.register_status === 'approved' && p.changed ? I18n.html`<button data-act="correct-house" data-id="${esc(p.building_id)}">Validate the change</button>` : ''}
      <a class="btn" href="api/plaque/${encodeURIComponent(p.building_id)}.svg" target="_blank" rel="noopener">${p.register_status === 'approved' ? 'Plaque' : 'Draft plaque'}</a>
      <a class="btn" href="api/card/${encodeURIComponent(p.building_id)}.svg" target="_blank" rel="noopener">${p.register_status === 'approved' ? 'Address card' : 'Draft address card'}</a>
      ${p.register_status === 'approved' ? I18n.html`<button class="danger" data-act="retire-house" data-id="${esc(p.building_id)}">Retire (house gone)</button>` : ''}</div>` : ''}`;
}

function nodePanel(staged) {
  if (!S.sel || S.sel.type !== 'node') return '';
  if (S.sel.props.effective) return I18n.htmlText('<h3>Current road endpoint</h3><p>Right-click its road and choose Connect an endpoint to a road. This works on the current cut and corrected sections.</p>');
  const p = S.sel.props, s = p.suggestion, k = nodeKind(p);
  const what = p.state === 'connected' ? `Connected to ${p.to === 'edge' ? 'a point of an existing road' : 'node ' + p.node} (${p.manual ? 'by hand' : 'automatic'})` : 'Not connected';
  return I18n.html`<h3>Selected node</h3><p>${what}${s ? ` &middot; suggestion: ${s.type === 'node' ? 'node' : 'a point of the road'} ${fmt(s.distance_m, 1)} m away` : ''}</p>
    <div class="row"><button class="primary" data-act="connect-click" data-key="${esc(p.key)}">${k === 'connected' ? 'Connect somewhere else' : 'Connect'}: click a road or node</button>
    ${s ? I18n.html`<button data-act="connect-sug" data-key="${esc(p.key)}">Use the suggestion</button>` : ''}
    <button data-act="leave-node" data-key="${esc(p.key)}">${k === 'connected' ? 'Disconnect' : 'Leave unconnected'}</button><button data-act="reset-node" data-key="${esc(p.key)}">Automatic</button></div>`;
}
function panelStage() {
  const st = S.stage, pv = st.pv, sm = pv.summary;
  const rep = pv.replaced.features.map((f, i) => { const q = f.properties, kept = q.kept.length > 0 && q.removed.length === 0;
    return I18n.html`<tr><td>${f.properties.refs.length} road${f.properties.refs.length > 1 ? 's' : ''}, ${fmt(q.old_length, 0)} m</td><td>${fmt(q.new_length, 0)} m</td><td><label><input type="checkbox" data-keep="${i}" ${kept ? 'checked' : ''}> keep the existing</label></td></tr>`; }).join('');
  return I18n.html`<h3>New streets from ${esc(st.filename)}</h3>
    <table><tr><td>lines in the file</td><td><strong>${sm.lines}</strong></td></tr><tr><td>connection nodes</td><td><strong>${sm.connected}</strong> (${sm.auto} automatic)</td></tr>
    <tr><td>ends not connected</td><td><strong>${sm.not_connected}</strong></td></tr><tr><td>roads not reaching the network</td><td>${sm.isolated}</td></tr>
    <tr><td>existing roads replaced</td><td><strong>${sm.replaced}</strong></td></tr></table>
    ${legend([['#00e5ff', 'connection node (thick)'], ['#ff6d00', 'end not connected'], ['#bdbdbd', 'inner node'], ['#d50000', 'existing road replaced']], true)}
    <p class="muted">Click a node to connect or disconnect it. Nothing is saved until you accept.</p>
    ${rep ? I18n.html`<h3>Replaced roads</h3><p class="muted">Same end nodes and a length within 10 %: the new street wins. Tick the ones that must stay.</p><table><tr><th>existing</th><th>new</th><th></th></tr>${rep}</table>` : ''}
    <div class="row sticky"><button class="primary" data-act="stage-accept">Accept and add ${sm.lines} streets</button><button data-act="stage-connect-suggested">Connect ends with a suggestion</button><button class="danger" data-act="stage-cancel">Cancel</button></div>`;
}
/* ---- basic road editing: draw a new road, or prolong a dead end (the new part joins that street); the ends snap to nodes and roads */
function startDraw(mode) {
  S.reshapePick = null;
  S.stage = null; S.del = null; S.sel = null;
  S.draw = { mode, tool: 'points', snap: true, pending: new Set(), pts: [], snaps: [], start: null, join: null, name: '', rank: 4, drivable: null, paved: null, ends: null };
  S.draw.phase = mode === 'route' ? 'start' : 'trace'; S.draw.strokeHistory = [];
  setMode('draw'); map.doubleClickZoom.disable();
  if (mode === 'prolong') api('/base/ends').then((e) => { if (S.draw) { S.draw.ends = e; drawTab(); } });
  drawTab();
}
function isReshapeMode(draw) { return !!draw && (draw.mode === 'reshape' || draw.mode === 'reshape-partial'); }
function isPlannedRoute(draw) { return !!draw && (draw.mode === 'route' || draw.mode === 'reshape-partial'); }
function stopDraw() { if (S.draw && S.draw.preview) map.removeLayer(S.draw.preview); S.draw = null; map.dragging.enable(); setMode(null); map.doubleClickZoom.enable(); drawTab(); }
async function pickRoadToReshape(action = 'reshape') {
  S.stage = null; S.del = null; S.sel = null;
  S.reshapePick = await api('/roads/geometry');
  S.reshapePick.action = action;
  drawTab();
}
function drawReshapeChoices() {
  L.geoJSON({ type: 'FeatureCollection', features: S.reshapePick.edges.features.filter(inWorkArea) }, { style: { color: '#00bcd4', weight: 6 }, onEachFeature: (f, layer) => {
    const action = S.reshapePick.action;
    layer.bindTooltip(action === 'review' ? `Street ${f.properties.street_id ?? '?'}: click to mark an unclear portion` : `Street ${f.properties.street_id ?? '?'}: click to ${action === 'cut' ? 'remove part of' : 'reshape'} this section`);
    layer.on('click', (e) => {
      L.DomEvent.stopPropagation(e);
      const revision = S.reshapePick.revision;
      if (['cut', 'partial', 'review'].includes(S.reshapePick.action)) {
        S.cut = { feature: f, revision, points: [], reshape: S.reshapePick.action === 'partial', review: S.reshapePick.action === 'review' }; S.reshapePick = null;
        setMode('cut'); drawTab(); return;
      }
      startDraw('reshape');
      const d = S.draw;
      d.ref = f.properties.ref; d.revision = revision; d.snap = false;
      d.pts = f.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
      d.snaps = d.pts.map(() => null);
      d.original = d.pts.map(p => [...p]);
      drawTab();
    });
  } }).addTo(G.roadEdges); G.roadEdges.addTo(map);
}
async function addCutPoint(ll) {
  const c = S.cut; if (!c || c.busy || c.points.length >= 2) return;
  c.points.push([ll.lng, ll.lat]); c.preview = null;
  if (c.points.length === 2) {
    c.busy = true;
    try { c.preview = await api(c.reshape ? '/roads/geometry/partial/preview' : '/roads/cut/preview', { ref: c.feature.properties.ref, points: c.points }); }
    catch (e) { c.points.pop(); toast(e.message, 6000); }
    finally { c.busy = false; }
  }
  if (S.cut === c) drawTab();
}
function drawCutLayers() {
  const c = S.cut;
  drawCurrentRoadContext(S.renderEpoch);
  if (c.reshape) {
    banner(c.preview ? 'Orange portion selected. Continue to trace its replacement.' : 'Click anchor A before the incorrect portion, then anchor B after it, also further along the road.', true);
    if (c.preview) {
      const next = document.createElement('button'); next.id = 'banner-next'; next.textContent = I18n.t('Trace replacement');
      next.className = 'primary'; next.onclick = () => ACT['partial-start']();
      const cancel = $('#banner-cancel'); cancel.parentNode.insertBefore(next, cancel);
    }
  } else if (c.review) {
    banner(c.preview ? 'Orange portion selected. Save it as unclear or reset the points.' : 'Click where the unclear portion starts, then where it ends.', true);
  }
  L.geoJSON(c.feature, { style: { color: '#f9a825', weight: 7 }, onEachFeature: (f, layer) => layer.on('click', e => { L.DomEvent.stopPropagation(e); addCutPoint(e.latlng); }) }).addTo(G.roadEdges);
  c.points.forEach(([lon, lat], i) => L.circleMarker([lat, lon], { radius: 7, color: '#d50000', fillOpacity: 1 }).bindTooltip(`Cut point ${i+1}`).addTo(G.roadNodes));
  if (c.preview) L.geoJSON(c.preview, { style: { color: c.reshape || c.review ? '#ff6d00' : '#d50000', weight: 9 }, interactive: false }).addTo(G.roadEdges);
  G.roadEdges.addTo(map); G.roadNodes.addTo(map);
}
function drawCurrentRoadContext(epoch) {
  api('/roads/geometry').then((current) => {
    if (S.tab !== 'roads' || epoch !== S.renderEpoch || (!S.cut && !S.draw)) return;
    G.base.clearLayers();
    const context = L.geoJSON(current.edges, {
      style: { color: '#ffd54f', weight: 2.5, opacity: .72 },
      interactive: false,
    }).addTo(G.base);
    G.base.addTo(map);
    context.eachLayer((layer) => { if (layer.bringToBack) layer.bringToBack(); });
  }).catch(() => {});
}
function snapMetres(ll) { const mpp = 156543.03 * Math.cos(ll.lat * Math.PI / 180) / Math.pow(2, map.getZoom()); return Math.max(1.5, Math.min(8, 9 * mpp)); }   // about 9 screen pixels, never more than 8 m
/* Always resolve context actions against the effective graph, including cut fragments. */
function nearbyRoads(fc, ll) {
  const p = map.latLngToContainerPoint(ll);
  return fc.features.map(f => {
    let distance = Infinity; const points = f.geometry.coordinates.map(c => map.latLngToContainerPoint([c[1], c[0]]));
    for (let i = 1; i < points.length; i++) {
      const a = points[i-1], b = points[i], dx = b.x-a.x, dy = b.y-a.y;
      const t = Math.max(0, Math.min(1, ((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy || 1)));
      distance = Math.min(distance, Math.hypot(p.x-a.x-t*dx, p.y-a.y-t*dy));
    }
    return { f, distance };
  }).filter(x => x.distance <= 12).sort((a,b) => a.distance-b.distance).map(x => x.f);
}
function cancelJoin() { S.join = null; setMode(null); drawTab(); }
map.on('contextmenu', async e => {
  if (S.locked || S.draw || S.stage) return;
  try {
    const current = await api('/roads/geometry'), choices = nearbyRoads(current.edges, e.latlng);
    if (!choices.length) { toast('No current road section here. Zoom in and right-click closer to the line.'); return; }
    const box = document.createElement('div'); box.className = 'road-context';
    box.innerHTML = I18n.html`<strong>Road editing</strong><select aria-label="Road section">${choices.map((f,i)=>I18n.html`<option value="${i}">${esc(f.properties.ref)} · street ${esc(f.properties.street_id ?? '?')}</option>`).join('')}</select><p class="road-end-info"></p><div>${[['route','Draw a road from two points'],['access','Set drivable from here (A → B)'],['review','Mark an unclear portion'],['partial','Reshape between two points'],['reshape','Reshape this whole section'],['cut','Delete a portion (two points)'],['whole','Delete this whole section'],['join','Connect an endpoint to a road'],['extend','Extend from a free endpoint'],['ids','Street IDs / group segments'],['names','Street names']].map(([a,t])=>I18n.html`<button data-road-action="${a}" style="display:block;margin:4px 0">${I18n.t(t)}</button>`).join('')}</div>`;
    const selected = () => choices[+box.querySelector('select').value];
    const info = () => { const f=selected(),p=f.properties; box.querySelector('.road-end-info').textContent = `${fmt(p.length_m,1)} m · A: ${I18n.t(p.degree_u === 1 ? 'free end' : 'junction')} · B: ${I18n.t(p.degree_v === 1 ? 'free end' : 'junction')}`; G.hl.clearLayers(); L.geoJSON(f,{style:{color:'#00e5ff',weight:8,opacity:.65},interactive:false}).addTo(G.hl); G.hl.addTo(map); };
    box.querySelector('select').onchange = info; info();
    box.addEventListener('click', async ev => {
      const action = ev.target.dataset.roadAction; if (!action) return;
      try {
        const f=selected(), revision=current.revision;
        map.closePopup(); await switchTab('roads');
        S.cut=null; S.join=null; S.reshapePick=null; S.del=null;
        if (action === 'ids' || action === 'names') { await switchTab(action); return; }
        if (action === 'route') {
          startDraw('route');
          const d=S.draw; d.picking=true;
          const target=await snapAt(e.latlng);
          if (S.draw !== d) return;
          const point=target ? [target.lat,target.lon] : [e.latlng.lat,e.latlng.lng];
          d.pts=[point]; d.snaps=[target]; d.start=target; d.phase='end'; d.picking=false;
          drawTab(); return;
        }
        if (action === 'access') {                                      // the right-clicked place is A; the next click is B
          S.edgeAccess = { a: { lat: e.latlng.lat, lon: e.latlng.lng }, result: null, route: 0 }; setMode('edge-access', { a: true }); drawTab(); return;
        }
        if (action === 'reshape') {
          startDraw('reshape'); Object.assign(S.draw,{ref:f.properties.ref, revision, snap:false, pts:f.geometry.coordinates.map(([x,y])=>[y,x])});
          S.draw.snaps=S.draw.pts.map(()=>null); S.draw.original=S.draw.pts.map(p=>[...p]); drawTab(); return;
        }
        if (action === 'review' || action === 'partial' || action === 'cut' || action === 'whole') {
          S.cut={feature:f,revision,points:[],whole:action==='whole',reshape:action==='partial',review:action==='review'};
          if (S.cut.whole) { const c=f.geometry.coordinates; S.cut.points=[c[0],c[c.length-1]]; S.cut.preview=await api('/roads/cut/preview',{ref:f.properties.ref,points:S.cut.points,whole:true}); }
          setMode('cut'); drawTab(); return;
        }
        S.join={feature:f,revision,current,extend:action==='extend'}; setMode('join'); drawTab();
      } catch (err) { toast(err.message,6000); }
    });
    L.popup({maxWidth:350}).setLatLng(e.latlng).setContent(box).openOn(map);
  } catch (err) { toast(err.message,6000); }
});
function drawJoinLayers() {
  const j=S.join, f=j.feature, p=f.properties, coords=f.geometry.coordinates;
  banner(j.source ? 'Click the target road at the junction to connect this endpoint.' : 'Choose endpoint A or B. Orange endpoints are free; a junction already connects roads.',true);
  const cancel=$('#banner-cancel'); if (cancel) cancel.onclick=cancelJoin;
  L.geoJSON(j.current.edges,{style:{color:'#ffd54f',weight:4},onEachFeature:(target,layer)=>layer.on('click',async e=>{
    L.DomEvent.stopPropagation(e); if (!j.source) return;
    const body={ref:p.ref,source_node:j.source.node,target_ref:target.properties.ref,lon:e.latlng.lng,lat:e.latlng.lat,revision:j.revision};
    try {
      const preview=await api('/roads/join/preview',body);
      if (preview.already_connected) { toast('These roads already share a junction. No connection change is needed.'); return; }
      const box=document.createElement('div');
      box.innerHTML=I18n.html`<p>${I18n.msg`Move this endpoint ${fmt(preview.gap_m,1)} m to the target road and create a shared junction? Street IDs are preserved.`}</p><button>Connect here</button>`;
      box.querySelector('button').onclick=async()=>{
        try { await api('/roads/join',body); map.closePopup(); S.join=null; setMode(null); await afterEdit(); await loadRoads(); drawTab(); toast('Roads connected at a shared junction.'); }
        catch(err) { toast(err.message,6000); }
      };
      const c=preview.point.coordinates; L.popup().setLatLng([c[1],c[0]]).setContent(box).openOn(map);
    } catch(err) { toast(err.message,6000); }
  })}).addTo(G.roadEdges); G.roadEdges.addTo(map);
  [[p.u,p.degree_u,coords[0],'A'],[p.v,p.degree_v,coords[coords.length-1],'B']].forEach(([node,degree,c,label])=>{
    L.marker([c[1],c[0]],{icon:L.divIcon({className:'',html:I18n.html`<strong style="background:${degree===1?'#ff9800':'#aaa'};padding:5px;border:2px solid white">${label}</strong>`})}).bindTooltip(degree===1?'Choose this free endpoint':'Already a junction').on('click',e=>{
      L.DomEvent.stopPropagation(e);
      if (degree!==1) { toast('This endpoint already belongs to a junction. Choose a free endpoint.'); return; }
      if (j.extend) {
        startDraw('prolong'); const d=S.draw; S.join=null; d.start={type:'node',node,lon:c[0],lat:c[1]}; d.join=p.street_id; d.pts=[[c[1],c[0]]]; d.snaps=[d.start]; drawTab(); return;
      }
      j.source={node}; drawTab();
    }).addTo(G.roadNodes);
  }); G.roadNodes.addTo(map);
}
async function snapAt(ll) { try { const m = snapMetres(ll); return (await api('/roads/snap', { lat: ll.lat, lon: ll.lng, max_m: m, node_m: m })).target; } catch (e) { return null; } }
async function addDrawPoint(ll) {                            // every point snaps to a node or a road under the mouse (about 9 pixels, at most 8 m), so the new road gets connected there
  const d = S.draw; if (!d || d.saving) return;
  if (isPlannedRoute(d)) {
    if (d.picking || d.reached) return;
    if (d.phase !== 'trace') {
      d.picking = true;
      const t = d.snap ? await snapAt(ll) : null;
      if (S.draw !== d) return;
      const p = t ? [t.lat, t.lon] : [ll.lat, ll.lng];
      if (d.phase === 'start') { d.pts = [p]; d.snaps = [t]; d.start = t; d.phase = 'end'; }
      else { d.target = p; d.endTarget = t; d.phase = 'trace'; }
      d.picking = false; drawTab(); return;
    }
    const reaches = map.latLngToContainerPoint(ll).distanceTo(map.latLngToContainerPoint(d.target)) <= 12;
    d.pts.push(reaches ? [...d.target] : [ll.lat, ll.lng]); d.snaps.push(reaches ? d.endTarget : null); d.reached = reaches;
    drawTab(); return;
  }
  if (d.mode === 'prolong' && !d.start) { toast('Click a dead end (orange dot) first'); return; }
  // Reserve the vertex before the request: rapid clicks must keep their order
  // even if snap responses arrive out of order.
  const point = [ll.lat, ll.lng];
  d.pts.push(point); d.snaps.push(null);
  drawTab();
  if (!d.snap) return;
  const request = snapAt(ll); d.pending.add(request);
  try {
    const t = await request; const i = d.pts.indexOf(point);
    if (S.draw !== d || !d.snap || i < 0) return;
    if (t) { d.pts[i] = [t.lat, t.lon]; d.snaps[i] = t; }
    if (i === 0) d.start = t;
    drawTab();
  } finally { d.pending.delete(request); }
}
let snapTimer = null;
map.on('mousemove', (e) => {                                  // the snap target under the mouse is shown before clicking
  if (!S.draw || !S.draw.snap || S.draw.stroke) return; clearTimeout(snapTimer);
  const d = S.draw;
  snapTimer = setTimeout(async () => {
    if (S.draw !== d || !d.snap) return;
    const t = await snapAt(e.latlng); if (S.draw !== d || !d.snap) return; G.hl.clearLayers(); if (!t) return;
    L.circleMarker([t.lat, t.lon], { radius: t.type === 'node' ? 10 : 7, color: '#00e676', weight: 3, fill: false, interactive: false }).addTo(G.hl); G.hl.addTo(map);
  }, 90);
});
// Freehand strokes remain a draft until Finish. Simplify in screen pixels so
// a long drag does not create thousands of almost identical vertices.
function beginDrawStroke(e) {
  const d = S.draw;
  if (!d || d.tool !== 'freehand' || d.saving || d.reached || d.phase !== 'trace' || e.originalEvent.button !== 0) return;
  if (d.mode === 'prolong' && !d.start) return;
  d.stroke = [e.latlng];
  d.preview = L.polyline([e.latlng], { color: '#00e5ff', weight: 5, interactive: false }).addTo(map);
}
map.on('mousedown', beginDrawStroke);
map.on('mousemove', (e) => {
  const d = S.draw; if (!d || !d.stroke) return;
  const last = map.latLngToContainerPoint(d.stroke[d.stroke.length - 1]);
  if (last.distanceTo(e.containerPoint) < 3) return;
  d.stroke.push(e.latlng); d.preview.setLatLngs(d.stroke);
});
function endDrawStroke() {
  const d = S.draw; if (!d || !d.stroke) return;
  const pts = L.LineUtil.simplify(d.stroke.map((ll) => map.latLngToContainerPoint(ll)), 2);
  map.removeLayer(d.preview); d.stroke = null; d.preview = null;
  if (pts.length < 2) return;
  const stroke = pts.map(p => { const ll = map.containerPointToLatLng(p); return [ll.lat, ll.lng]; });
  if (d.mode !== 'reshape' && d.pts.length) {
    const last = d.pts[d.pts.length-1];
    if (map.latLngToContainerPoint(last).distanceTo(map.latLngToContainerPoint(stroke[0])) > 12) {
      toast('Start the next stroke at the last point; no gap has been joined.', 6000); return;
    }
    stroke[0] = [...last];
  }
  d.strokeHistory.push({ pts: d.pts.map(p => [...p]), snaps: [...d.snaps], reached: d.reached });
  if (d.mode === 'reshape') {
    // Retain both network junctions while replacing the interior trace.
    const first = L.latLng(d.original[0]), last = L.latLng(d.original[d.original.length - 1]);
    if (first.distanceTo(stroke[0]) + last.distanceTo(stroke[stroke.length - 1]) > first.distanceTo(stroke[stroke.length - 1]) + last.distanceTo(stroke[0])) stroke.reverse();
    d.pts = [d.original[0], ...stroke, d.original[d.original.length - 1]];
    d.snaps = d.pts.map(() => null);
  } else {
    const hadPoints = d.pts.length > 0;
    stroke.slice(hadPoints ? 1 : 0).forEach(p => { d.pts.push(p); d.snaps.push(null); });
    if (isPlannedRoute(d) && map.latLngToContainerPoint(d.pts[d.pts.length-1]).distanceTo(map.latLngToContainerPoint(d.target)) <= 12) {
      d.pts[d.pts.length-1] = [...d.target]; d.snaps[d.snaps.length-1] = d.endTarget; d.reached = true;
    }
  }
  drawTab();
}
document.addEventListener('mouseup', endDrawStroke);
window.addEventListener('blur', endDrawStroke);
async function finishDraw(recompute) {
  endDrawStroke();
  const d = S.draw; if (!d || d.pts.length < 2 || d.saving) return;
  if (isPlannedRoute(d) && !d.reached && !(d.mode === 'route' && d.uncertain)) { toast('Continue tracing until you reach the planned end.'); return; }
  d.saving = true;
  try {
    await Promise.all([...d.pending]);
    if (S.draw !== d) return;
    if (isReshapeMode(d)) {
      const endpoint = d.mode === 'reshape-partial' ? '/roads/geometry/partial' : '/roads/geometry';
      const payload = { ref: d.ref, revision: d.revision, coords: d.pts.map(([lat, lon]) => [lon, lat]) };
      if (d.mode === 'reshape-partial') { payload.points = d.anchors; if (d.uncertain) payload.end_review = 'uncertain'; }
      await api(endpoint, payload);
      stopDraw(); await afterEdit(); await loadRoads(); drawTab();
      toast(d.mode === 'reshape-partial' ? 'Selected road portion reshaped; the rest was preserved.' : 'Road reshaped. Junctions and street identity retained; recompute to update addresses.');
      if (recompute) recomputeIfStale();
      return;
    }
    const last = d.pts.length - 1;
    if (d.uncertain) d.snaps[last] = null;
    if (d.snap) {
      for (const i of [0, last]) {
      if (i === last && d.uncertain) { d.snaps[i] = null; continue; }
      if (!d.snaps[i]) d.snaps[i] = await snapAt(L.latLng(d.pts[i][0], d.pts[i][1]));
        if (d.snaps[i] && Number.isFinite(d.snaps[i].lat) && Number.isFinite(d.snaps[i].lon)) d.pts[i] = [d.snaps[i].lat, d.snaps[i].lon];
      }
    }
    if (S.draw !== d) return;
    if (d.snaps[last]) d.pts[last] = [d.snaps[last].lat, d.snaps[last].lon];
    const cuts = [0]; for (let i = 1; i < last; i++) if (d.snaps[i]) cuts.push(i); cuts.push(last);          // a snapped point in the middle splits the line there
    const pieces = cuts.slice(1).map((c, k) => { const a = cuts[k]; return { coords: d.pts.slice(a, c + 1).map(([la, lo]) => [lo, la]), start: d.snaps[a] || (d.snap ? null : { type: 'none' }), end: d.snaps[c] || (d.snap ? null : { type: 'none' }) }; });
    const name = ($('#draw-name') && $('#draw-name').value.trim()) || d.name || null;
    const saved = await api('/roads/draw', Object.assign({ pieces, name, join: d.join, end_review: d.uncertain ? 'uncertain' : undefined }, d.mode !== 'prolong' ? { rank: d.rank, drivable: d.drivable, paved: d.paved } : {}));
    const mode = d.mode; stopDraw(); await afterEdit();
    if (saved.edges?.features?.length) {
      if (!S.roads) S.roads = { edges: { type:'FeatureCollection', features:[] }, nodes: { type:'FeatureCollection', features:[] }, reviews: { type:'FeatureCollection', features:[] }, report:{} };
      const added = new Set(saved.edges.features.map((f) => f.properties.feature));
      S.roads.edges.features = [...(S.roads.edges?.features || []).filter((f) => !added.has(f.properties.feature)), ...saved.edges.features];
    }
    toast(`Road added (${d.snaps.filter(Boolean).length} connections)`); drawTab();
    // Refresh snapping, nodes and warnings in the background.  The saved trace above stays visible while the expensive
    // replay runs, so geometry work can continue without forcing a street-id recomputation after every road.
    const savedRevision = S.rev;
    loadRoads(false, savedRevision).then(() => { if (S.rev === savedRevision && S.tab === 'roads' && !S.draw) drawTab(); }).catch((error) => toast(error.message, 4500));
    if (recompute) recomputeIfStale();
  } finally { d.saving = false; }
}
function drawDrawLayers() {
  const epoch = S.renderEpoch;
  const d = S.draw;
  if (d.target) L.marker(d.target, { icon: L.divIcon({ className: 'road-target', html: 'End', iconSize: [30, 22] }) }).bindTooltip('Planned endpoint — no line is added until you trace to it').on('click', e => { L.DomEvent.stopPropagation(e); if (d.tool === 'points') addDrawPoint(L.latLng(d.target)); }).addTo(G.roadNodes);
  G.roadNodes.addTo(map);
  drawCurrentRoadContext(epoch);
  if (d.mode === 'prolong' && !d.start && d.ends) {
    d.ends.forEach(([node, lon, lat, sid]) => L.circleMarker([lat, lon], { radius: 7, color: '#000', weight: 1.5, fillColor: '#ff6d00', fillOpacity: 1 })
      .bindTooltip(`dead end of street ${sid === null ? '?' : sid} - click to prolong it`)
      .on('click', (e) => { L.DomEvent.stopPropagation(e); d.start = { type: 'node', node }; d.join = sid; d.pts = [[lat, lon]]; d.snaps = [d.start]; drawTab(); }).addTo(G.roadNodes));
    G.roadNodes.addTo(map);
  }
  if (d.pts.length) {
    if (d.original) L.polyline(d.original, { color: '#f57c00', weight: 4, dashArray: '3 6', interactive: false }).addTo(G.roadEdges);
    const line = L.polyline(d.pts, { color: '#00e5ff', weight: 5, dashArray: '8 6', interactive: false }).addTo(G.roadEdges);
    d.pts.forEach((p, i) => {
      // The fixed start of a prolongation must stay on its original node.
      const fixed = ((d.mode === 'prolong' || isPlannedRoute(d)) && i === 0) || (isPlannedRoute(d) && d.reached && i === d.pts.length-1) || (d.mode === 'reshape' && (i === 0 || i === d.pts.length - 1));
      const marker = L.marker(p, { draggable: !fixed && !d.saving && d.tool !== 'freehand', icon: L.divIcon({ className: `road-vertex${fixed ? i === 0 ? ' road-start' : ' road-end' : ''}`, iconSize: [12, 12], iconAnchor: [6, 6] }) }).addTo(G.roadEdges);
      marker.bindTooltip(fixed ? i === 0 ? 'Fixed start junction (green)' : 'Fixed end junction (red)' : 'Drag to reshape; right-click to remove');
      marker.on('drag', () => { const ll = marker.getLatLng(); d.pts[i] = [ll.lat, ll.lng]; d.snaps[i] = null; line.setLatLngs(d.pts); });
      marker.on('dragend', async () => {
        if (S.draw !== d) return;
        const t = d.snap ? await snapAt(marker.getLatLng()) : null;
        if (S.draw !== d) return;
        if (t) { d.pts[i] = [t.lat, t.lon]; d.snaps[i] = t; }
        drawTab();
      });
      marker.on('contextmenu', (e) => { L.DomEvent.stop(e.originalEvent); if (fixed) return; d.pts.splice(i, 1); d.snaps.splice(i, 1); drawTab(); });
      marker.on('mousedown click dblclick', (e) => L.DomEvent.stopPropagation(e));
      marker.on('mousedown', e => { if (d.tool === 'freehand' && i === d.pts.length-1) beginDrawStroke({ latlng: marker.getLatLng(), originalEvent: e.originalEvent }); });
      if (i > 0) {
        const a = d.pts[i - 1];
        L.circleMarker([(a[0] + p[0]) / 2, (a[1] + p[1]) / 2], { radius: 4, color: '#004d40', fillColor: '#fff', fillOpacity: .7 })
          .bindTooltip('Click to insert a bend').on('click', (e) => { L.DomEvent.stopPropagation(e); d.pts.splice(i, 0, [e.latlng.lat, e.latlng.lng]); d.snaps.splice(i, 0, null); drawTab(); }).addTo(G.roadEdges);
      }
    });
    G.roadEdges.addTo(map);
  }
}
function panelDraw() {
  const d = S.draw, n = d.pts.length;
  const msg = d.mode === 'prolong' && !d.start ? 'Click a dead end (orange dot) of the road to prolong.' : d.tool === 'freehand' ? 'Hold the left mouse button and trace the road. Release to adjust the points; Finish saves it.' : isReshapeMode(d) ? 'Drag the white points to follow the visible road. Click a small midpoint to insert a bend; right-click a white point to remove it.' : 'Click along the road to add bends. Drag a point to reshape; click a small midpoint to insert a bend; right-click a point to remove it.';
  const sel = (id, opts, cur) => I18n.html`<select id="${id}">${opts.map(([v, t]) => I18n.html`<option value="${v}" ${String(cur) === String(v) ? 'selected' : ''}>${I18n.t(t)}</option>`).join('')}</select>`;
  const triOpts = [['null', 'unknown'], ['true', 'yes'], ['false', 'no']];
  return I18n.html`<h3>${I18n.t(d.mode === 'route' ? 'Trace a connected route' : isReshapeMode(d) ? d.mode === 'reshape-partial' ? 'Reshape selected road portion' : 'Reshape existing road' : d.mode === 'new' ? 'Draw a new road' : 'Prolong a road end')}</h3><p>${d.mode === 'route' && d.phase !== 'trace' ? d.phase === 'start' ? I18n.t('Click the starting point.') : I18n.t('Click the planned ending point. This does not draw a connecting line.') : I18n.t(msg)}</p>
    ${d.mode === 'route' && d.phase === 'trace' ? I18n.htmlText('<p>Each stroke must start at the last point. The planned end remains separate until reached. Stop and flag uncertainty where the visible path disappears.</p>') : ''}
    ${d.mode === 'reshape' ? I18n.htmlText('<p>Move the white points or insert bends between the fixed junctions. Orange shows the previous shape. Freehand replaces the interior while keeping both junctions.</p>') : ''}
    ${d.mode === 'reshape-partial' ? I18n.htmlText('<p>Orange is the old portion. Trace a completely new cyan route from the green A anchor to the planned B endpoint. Saving replaces the orange portion; it does not add a road.</p><button data-act="partial-change-anchors">Change anchors A and B</button>') : ''}
    <p><label>Drawing <select id="draw-tool" ${d.phase !== 'trace' ? 'disabled' : ''}><option value="points" ${d.tool === 'points' ? 'selected' : ''}>Click points</option><option value="freehand" ${d.tool === 'freehand' ? 'selected' : ''}>Freehand trace</option></select></label></p>
    ${isReshapeMode(d) ? '' : I18n.html`<p><label><input type="checkbox" id="draw-snap" ${d.snap ? 'checked' : ''}> Snap to existing roads</label></p>`}
    <p class="muted">${n} points. Freehand mode uses dragging to draw; switch to Click points to pan the map.${isReshapeMode(d) ? ' Use Change anchors if A or B is misplaced.' : ' With snapping off, new ends stay unconnected.'}</p>
    ${d.mode === 'prolong' && d.join !== null ? I18n.html`<p class="muted">The new part becomes part of street ${d.join}.</p>` : ''}
    ${isReshapeMode(d) ? '' : I18n.html`<p><input type="text" id="draw-name" placeholder="Name (optional)" value="${esc(d.name)}"></p>`}
    ${d.mode === 'new' || d.mode === 'route' ? I18n.html`<table class="form"><tr><td>Rank</td><td>${sel('draw-rank', RANK_NAMES.map((t, i) => [i, t]), d.rank)}</td></tr>
      <tr><td>Drivable</td><td>${sel('draw-drv', triOpts, d.drivable)}</td></tr><tr><td>Paved</td><td>${sel('draw-paved', triOpts, d.paved)}</td></tr></table>` : ''}
    ${!isReshapeMode(d) || d.mode === 'reshape-partial' ? I18n.html`<p><label><input type="checkbox" id="draw-uncertain" ${d.uncertain ? 'checked' : ''}> ${d.mode === 'reshape-partial' ? 'Path beyond anchor B is unclear' : 'Stop here: path beyond this point is unclear'}</label></p>` : ''}
    <div class="row"><button class="primary" data-act="draw-finish" ${n < 2 ? 'disabled' : ''}>Finish</button><button data-act="draw-again" ${n < 2 ? 'disabled' : ''}>Finish and recompute ids</button><button class="danger" data-act="draw-cancel">Cancel</button></div>
    ${d.strokeHistory.length ? I18n.htmlText('<button data-act="draw-undo-stroke">Undo last stroke</button>') : ''}
    <div class="row">${d.mode === 'reshape' ? '' : I18n.html`<button data-act="draw-undo" ${n < 1 || ((d.mode === 'prolong' || isPlannedRoute(d)) && n < 2) ? 'disabled' : ''}>Remove last point</button>`}${isReshapeMode(d) ? I18n.htmlText('<button data-act="reshape-reset">Reset trace</button>') : ''}<span class="muted">Enter finishes &middot; Esc cancels</span></div>`;
}
function panelDelete() {
  const d = S.del, n = d.sel.size, gone = S.edgeData ? S.edgeData.removed.features.length : 0;
  return I18n.html`<h3>Delete street edges</h3><p>Click edges to select them (red). Click a grey dashed edge to restore it.</p>
    <p><strong>${n}</strong> selected &middot; ${gone} deleted so far</p>
    <div class="row"><button class="danger" data-act="del-apply" ${n ? '' : 'disabled'}>Delete the ${n} selected</button><button data-act="del-clear" ${n ? '' : 'disabled'}>Clear selection</button><button data-act="del-done">Done</button></div>
    <p class="muted">One undo step; the ids update by themselves.</p>`;
}
function drawEdgeAccessDraft() {
  const d = S.edgeAccess; if (!d) return;
  G.hl.clearLayers();
  if (d.result) {
    const route = d.result.routes[d.route || 0];
    L.geoJSON(route.geometry, { style: { color: '#00b8d4', weight: 8, opacity: .9 }, interactive: false }).addTo(G.hl);
    [['A', d.result.a], ['B', d.result.b]].forEach(([label, p]) => L.circleMarker([p.lat, p.lon], { radius: 7, color: '#fff', weight: 2, fillColor: label === 'A' ? '#2e7d32' : '#d84315', fillOpacity: 1 }).bindTooltip(`${label} · node ${p.node}`, { permanent: true }).addTo(G.hl));
  } else if (d.a) {
    L.circleMarker([d.a.lat, d.a.lon], { radius: 7, color: '#fff', weight: 2, fillColor: '#2e7d32', fillOpacity: 1 }).bindTooltip('A', { permanent: true }).addTo(G.hl);
  }
  G.hl.addTo(map);
}
function panelEdgeAccess() {
  const d = S.edgeAccess, result = d.result, route = result && result.routes[d.route || 0];
  return I18n.html`<h3>Drivable from A to B</h3>
    ${!d.a ? I18n.htmlText('<p>Click A on or near a road. It will snap to the nearest network node.</p>') : !result ? I18n.htmlText('<p>Now click B. The shortest existing route will be calculated without moving or splitting roads.</p>') : I18n.html`<p><strong>${fmt(route.length_m, 1)} m</strong> · ${route.refs.length} edges · node ${result.a.node} → ${result.b.node}</p>
      ${result.routes.length > 1 ? I18n.html`<button data-act="edge-access-other">${d.route ? 'Use shortest route' : 'Other route'} · ${fmt(result.routes[d.route ? 0 : 1].length_m, 1)} m</button>` : I18n.htmlText('<p class="muted">No other node-distinct route exists between A and B.</p>')}
      <label>Drivable<select id="edge-access-value"><option value="car">Yes</option><option value="foot">No (foot or motorbike)</option><option value="unknown">Unknown</option></select></label>
      <div class="row"><button class="primary" data-act="edge-access-save">Save classification</button><button data-act="edge-access-restart">Choose A and B again</button><button data-act="edge-access-cancel">Cancel</button></div>
      <p class="muted">This changes drivable only; roads do not move. Street IDs are recalculated at the next Compute.</p>`}
    ${d.a && !result ? I18n.htmlText('<button data-act="edge-access-restart">Choose A again</button> <button data-act="edge-access-cancel">Cancel</button>') : !d.a ? I18n.htmlText('<button data-act="edge-access-cancel">Cancel</button>') : ''}`;
}
function panelRoads() {
  if (S.edgeAccess) return panelEdgeAccess();
  if (S.join) return I18n.htmlText('<h3>Connect roads</h3><p>Choose a free endpoint A or B, then click the target road. A shared junction connects routing; street ID grouping is separate.</p><button data-act=join-cancel>Cancel connection</button>');
  if (S.reshapePick) return I18n.html`<h3>${S.reshapePick.action === 'review' ? 'Mark an unclear road portion' : S.reshapePick.action === 'cut' ? 'Remove part of a road' : 'Reshape an existing road'}</h3><p>Click a cyan road section${S.reshapePick.action === 'review' ? ', then choose where the unclear interval starts and ends.' : S.reshapePick.action === 'cut' ? ', then choose two cut points.' : ' to adjust its bends. Junction endpoints stay fixed.'}</p><button data-act="reshape-cancel">Cancel</button>`;
  if (S.cut) return S.cut.review
    ? I18n.html`<h3>Mark an unclear road portion</h3><p>Click the start and end of the interval that cannot be confirmed from the imagery. This records a review mark and does not change the road.</p>
      ${S.cut.preview ? I18n.html`<p><strong>${fmt(S.cut.preview.properties.removed_m, 1)} m</strong> selected in orange.</p><textarea id="review-note" maxlength="500" placeholder="Why is this unclear?">Road hidden or unclear in imagery</textarea>` : I18n.html`<p>${S.cut.points.length} of 2 points chosen.</p>`}
      <button class="primary" data-act="review-save" ${!S.cut.preview || S.cut.busy ? 'disabled' : ''}>Save unclear portion</button><button data-act="cut-reset">Reset points</button><button data-act="cut-cancel">Cancel</button>`
    : S.cut.reshape ? I18n.html`<h3>Choose the portion to reshape</h3><p>Click point A before the inaccurate bend and point B after it. The orange portion will be replaced; everything outside it stays unchanged.</p>
      ${S.cut.preview ? I18n.html`<p><strong>${fmt(S.cut.preview.properties.selected_m, 1)} m</strong> selected between two fixed anchors.</p>` : I18n.html`<p>${S.cut.points.length} of 2 anchor points chosen.</p>`}
      <button class="primary" data-act="partial-start" ${!S.cut.preview || S.cut.busy ? 'disabled' : ''}>Trace replacement</button><button data-act="cut-reset">Reset anchors</button><button data-act="cut-cancel">Cancel</button>`
    : I18n.html`<h3>Remove part of a road</h3><p>Choose two positions along this section. The portion between them appears in red; the rest stays.</p>
      ${S.cut.preview ? I18n.html`<p><strong>${fmt(S.cut.preview.properties.removed_m, 1)} m</strong> to remove; ${S.cut.preview.properties.retained_parts} outside parts retained. A gap can disconnect the network.</p>` : I18n.html`<p>${S.cut.points.length} of 2 cut points chosen.</p>`}
      <button class="danger" data-act="cut-save" ${!S.cut.preview || S.cut.busy ? 'disabled' : ''}>Delete red portion</button><button data-act="cut-reset">Reset cut points</button><button data-act="cut-cancel">Cancel</button>`;
  if (S.draw) return panelDraw();
  if (S.stage && S.stage.pv) return panelStage();
  if (S.del) return panelDelete();
  const r = S.roads || { imports: [], report: {} }, rep = r.report || {};
  const reviewRows = (r.reviews?.features || []).map((feature, index) => I18n.html`<tr><td>${index + 1}</td><td>${fmt(feature.properties.selected_m, 1)} m</td><td>${esc(feature.properties.note)}</td><td><button data-act="review-remove" data-id="${esc(feature.properties.id)}">Mark clear</button></td></tr>`).join('');
  const grouped = []; (r.imports || []).forEach((i) => { const g = grouped.find((x) => x.file === i.file); if (g) { g.lines += i.lines; g.ids.push(i.id); } else grouped.push({ file: i.file, lines: i.lines, ids: [i.id] }); });   // files with one name (all the roads drawn by hand) are one file
  const imports = grouped.map((i) => I18n.html`<tr><td>${esc(i.file)}</td><td>${i.lines} lines</td><td><button data-act="conn-open">Edit connections</button> <button class="danger" data-act="remove-roads" data-id="${i.ids.join(',')}">Remove</button></td></tr>`).join('');
  const dangling = (r.nodes ? r.nodes.features : []).filter((f) => rep.dangling && rep.dangling.includes(f.properties.key));
  const rows = dangling.map((f, i) => { const s = f.properties.suggestion; return I18n.html`<tr class="click" data-act="select-node" data-key="${esc(f.properties.key)}"><td>${i + 1}</td><td>${s ? `${s.type === 'node' ? 'node' : 'road'} ${fmt(s.distance_m, 1)} m away` : 'nothing near'}</td></tr>`; }).join('');
  const comp = S.components && S.components.parts.length ? I18n.html`<div class="warnbox"><strong>The network is not connected</strong>: ${S.components.parts.length} part${S.components.parts.length > 1 ? 's are' : ' is'} cut off from the main network (red dashed on the map). Connect ${S.components.parts.length > 1 ? 'them' : 'it'} by drawing or prolonging a road.<table>${S.components.parts.map((p) => I18n.html`<tr><td>part ${p.id}</td><td>${p.edges} edges &middot; ${fmt(p.length_m)} m</td><td>street${p.streets.length > 1 ? 's' : ''} ${p.streets.join(', ')}</td><td><a href="#" data-act="zoom-part" data-part="${p.id}">show</a></td></tr>`).join('')}</table></div>` : '';
  const sec = (key, title, body, open) => I18n.html`<details class="sec" data-sec="${key}" ${(S.openSec ? S.openSec[key] : open) ? 'open' : ''}><summary>${I18n.t(title)}</summary>${body}</details>`;
  if (S.connView && rep.features) {
    return I18n.html`<div class="row"><button data-act="conn-back">&larr; Back to edit streets</button></div><h3>Connection of the added streets</h3><table><tr><td>streets</td><td>${rep.features}</td></tr><tr><td>ends connected automatically</td><td>${rep.auto_connected}</td></tr>
      <tr><td>roads split to connect</td><td>${rep.split_edges}</td></tr><tr><td>ends not connected</td><td><strong>${(rep.dangling || []).length}</strong></td></tr>
      <tr><td>roads not reaching the network</td><td>${(rep.isolated || []).length}</td></tr></table>
      ${legend([['#00e5ff', 'connection node'], ['#ff6d00', 'end not connected'], ['#bdbdbd', 'inner node']], true)}
      ${r.nodes?.features.some(f=>f.properties.effective) ? I18n.htmlText('<p>Right-click a current road to connect its endpoint.</p>') : I18n.htmlText('<div class="row"><button data-act="connect-suggested">Connect the ends with a suggestion (&le; 25 m)</button></div>')}
      <p class="muted">The street ids update by themselves. Click a node of a new road to edit its connection.</p>
      <h3>Ends not connected</h3><table><tr><th>#</th><th>nearest existing road</th></tr>${rows || I18n.htmlText('<tr><td colspan="2" class="muted">all ends are connected</td></tr>')}</table>`;
  }
  let h = I18n.html`<div class="workspace-hint"><div><strong>Right-click a road to edit</strong><small>Your edits are saved automatically. Use checkpoints before a larger change.</small></div></div>${comp}<div class="row"><label>Colour by <select id="roads-color"><option value="plain" ${S.roadColor !== 'file' ? 'selected' : ''}>one colour</option><option value="file" ${S.roadColor === 'file' ? 'selected' : ''}>file</option></select></label></div>${roadsLegend()}`;
  h += sec('check', 'Road check', panelCheck(), true);
  h += sec('access', 'Drivable', I18n.htmlText('<div class="row"><button data-act="edge-access-start">Set drivable from A to B</button></div><p class="muted">Choose A and B; the tool follows existing roads and never moves them. Colour by drivable in the Street types and IDs tab to check; OSM tracks are named in the tooltip.</p>'), false);
  h += sec('review', 'Unclear road portions', I18n.html`<div class="row"><button data-act="review-pick">Mark an unclear portion</button></div>${reviewRows ? I18n.html`<table><tr><th>#</th><th>Length</th><th>Reason</th><th></th></tr>${reviewRows}</table>` : I18n.htmlText('<p class="muted">No road portions are currently marked unclear.</p>')}`, false);
  h += sec('draw', 'Draw, prolong or reshape a road', I18n.htmlText('<div class="row"><button data-act="draw-route">Trace route: start → end</button><button data-act="draw-new">Draw a new road</button><button data-act="draw-prolong">Prolong a road end</button><button data-act="partial-pick">Reshape between two points</button><button data-act="reshape-pick">Reshape a whole section</button></div>'), false);
  h += sec('add', 'Add streets from a file', I18n.htmlText('<p class="muted">KML, GeoJSON, GeoPackage or zipped shapefile</p><div class="row"><input type="file" id="roads-file" accept=".kml,.geojson,.json,.gpkg,.zip,.shp"></div>'), true);
  h += sec('del', 'Delete edges', I18n.htmlText('<div class="row"><button data-act="cut-pick">Remove part of a road...</button><button data-act="del-start">Select whole edges to delete...</button></div>'), false);
  h += sec('data', 'Street data and Google Earth', I18n.htmlText('<div class="row"><a class="btn" href="api/export/streets.csv" download="streets.csv">&#11015; Street data CSV</a><a class="btn" href="api/export/edges.kml" download>&#11015; Streets KML</a></div><p class="muted">Upload an edited street data CSV (rank, drivable, paved):</p><div class="row"><input type="file" id="attrs-file" accept=".csv"></div>'), false);
  if (imports) h += I18n.html`<h3>Files already added</h3><table>${imports}</table>`;
  return h;
}

/* ---------------------------------------------------------------- panel actions (event delegation) */
async function reloadAddresses() {                                 // after an approval: the register changes the addresses shown, not the computation
  await refreshProject(); S.addresses = await api('/addresses');
  if (S.sel && S.sel.type === 'house') { const f = S.addresses.houses.features.find((x) => x.properties.building_id === S.sel.props.building_id); if (f) S.sel.props = f.properties; }
  drawTab(); renderPanel();
}
const ACT = {
  compute: () => startCompute('network'),
  'compute-addresses': () => startCompute('addresses'),
  select: (b) => selectStreet(+b.dataset.id),
  'goto-plan': (b) => selectStreet(+b.dataset.id),
  'check-run': async () => { toast('Checking the roads...'); await runCheck(); },
  'check-zoom': (b) => zoomCheck(+b.dataset.n),
  'check-ok': async (b) => { await api('/roads/check/ok', { ids: [b.dataset.id], ok: b.dataset.ok === '1' }); await refreshProject(); await runCheck(); },
  'check-close': () => { S.check = null; S.checkFocus = null; G.check.clearLayers(); G.hl.clearLayers(); renderPanel(); },
  'plan-all': () => { S.planAll = !S.planAll; renderPanel(); },
  'set-name': async (b) => { const typed = $('#name-input').value.trim(), name = typed || '0'; /* an empty box deletes the name */ const old = (S.project.names || {})[b.dataset.id] || null; try { await api('/names', { street_id: +b.dataset.id, name, expected: old, user: user() }); } catch (err) { if (err.status !== 409) throw err; const cur = err.detail.current; if (!confirm(`Someone just changed this street to "${cur || '(no name)'}". Replace it with "${name}"?`)) { await refreshProject(); renderPanel(); return; } await api('/names', { street_id: +b.dataset.id, name, expected: cur, user: user() }); } await afterEdit(); toast('Name saved.'); renderPanel(); },
  'delete-name': async (b) => { await api('/names', { street_id: +b.dataset.id, name: '0', user: user() }); await afterEdit(); toast('Name deleted'); renderPanel(); },
  'clear-name': async (b) => { await api('/names', { street_id: +b.dataset.id, name: '', user: user() }); await afterEdit(); toast('Name removed'); renderPanel(); },
  'apply-settings': async () => { await api('/settings', { house_step_m: +$('#set-house').value, branch_step_m: +$('#set-branch').value, max_house_distance_m: +$('#set-dist').value, connect_backbone: $('#set-conn').checked, user: user() }); await afterEdit(); toast('Settings changed. Compute to apply.'); renderPanel(); },
  'pick-access': (b) => setMode('access', { id: b.dataset.id }),
  'approve-house': async (b) => { const r = await api('/register/approve', { ids: [b.dataset.id] }); toast(r.approved ? 'Address validated: it changes only when you validate a change.' : 'Not validated: the address is not complete.', 4000); await reloadAddresses(); },
  'approve-area': async (b) => { if (!confirm(I18n.msg`Validate every complete address in ${b.dataset.id}?`)) return; const r = await api('/register/approve', { area: b.dataset.id }); toast(I18n.msg`${r.approved} validated, ${r.unchanged} already validated, ${r.skipped} not complete.`, 6000); await reloadAddresses(); },
  'correct-house': async (b) => { const reason = prompt(I18n.t('Why does the address change? (kept in its history and in the list of families to inform)')); if (!reason || !reason.trim()) return; await api('/register/approve', { ids: [b.dataset.id], correct: true, reason }); toast('Change validated. The family is on the list to inform.', 4000); await reloadAddresses(); },
  'set-quartier': async (b) => { const q = $('#house-quartier').value; await api('/houses/quartier', { ids: [b.dataset.id], quartier: q }); toast(q ? I18n.msg`Quartier set to ${q}. Compute the addresses to apply.` : 'Quartier back to the survey. Compute the addresses to apply.', 5000); await refreshProject(); renderPanel(); },
  'validate-changes': async () => { const reason = prompt(I18n.t('Why do these addresses change? (kept in their history and in the list of families to inform)')); if (!reason || !reason.trim()) return; const r = await api('/register/approve', { changed: true, correct: true, reason }); toast(I18n.msg`${r.corrected} changes validated. Download the list of families to inform.`, 6000); await reloadAddresses(); },
  'retire-house': async (b) => { const reason = prompt(I18n.t('Why is this address retired? (e.g. house demolished)')); if (!reason || !reason.trim()) return; await api('/register/retire', { ids: [b.dataset.id], reason }); toast('Address retired. Its number and code will never be given again.', 5000); await reloadAddresses(); },
  'clear-access': async (b) => { await api('/access', { building_id: b.dataset.id, clear: true, user: user() }); await afterEdit(); toast('Back to the nearest road.'); renderPanel(); },
  'remove-roads': async (b) => { const ids = b.dataset.id.split(','); if (ids.length > 1 && !confirm(`Remove all ${ids.length} parts of this file?`)) return; for (const id of ids) await api('/roads/remove', { id: +id, user: user() }); await afterEdit(); await loadRoads(); drawTab(); },
  'zoom-part': (b) => { const fs = S.components.edges.features.filter((f) => f.properties.part === +b.dataset.part); if (fs.length) map.fitBounds(L.geoJSON(fs).getBounds().pad(0.3)); },
  'del-part': async (b) => { if (!confirm(`Delete the separate part ${b.dataset.part} completely? You can undo this.`)) return; await api('/base/components/delete', { part: +b.dataset.part, user: user() }); S.components = null; await afterEdit(); await loadRoads(); toast('Part deleted.', 4000); drawTab(); },
  'conn-open': () => { S.connView = true; renderPanel(); },
  'conn-back': () => { S.connView = false; renderPanel(); },
  'connect-suggested': async () => { const r = await api('/roads/connect-suggested', { max_m: 25, user: user() }); toast(`${r.connected} ends connected`); await afterEdit(); await loadRoads(); drawTab(); },
  'select-node': (b) => { const f = S.roads.nodes.features.find((x) => x.properties.key === b.dataset.key); if (f) { S.sel = { type: 'node', key: f.properties.key, props: f.properties, ll: L.latLng(f.geometry.coordinates[1], f.geometry.coordinates[0]) }; map.setView(S.sel.ll, Math.max(map.getZoom(), 18)); renderPanel(); refreshSel(); } },
  'connect-click': (b) => setMode('connect', { key: b.dataset.key }),
  'stage-cancel': () => { clearStage(); drawTab(); },
  'stage-accept': async () => {
    const st = S.stage, sm = st.pv.summary;
    if (!confirm(`Add ${sm.lines} new streets to the project?\n${sm.connected} connection nodes, ${sm.not_connected} ends not connected, ${sm.replaced} existing roads replaced by the new ones.`)) return;
    const r = await api('/roads/import', { filename: st.filename, features: st.features, connections: st.connections, keep: st.keep, user: user() });
    clearStage(); S.fittedRoads = false; await afterEdit(); await loadRoads(); S.connView = true; toast(`${r.lines} streets added.`, 5000); drawTab();
  },
  'stage-connect-suggested': async () => {
    const st = S.stage; let n = 0;
    st.pv.nodes.features.forEach((f) => { const p = f.properties; if (p.suggestion && st.pv.dangling.includes(p.key) && p.suggestion.distance_m <= 25) { st.connections[p.key] = p.suggestion; n += 1; } });
    await previewStage(false); toast(`${n} ends connected`); drawTab();
  },
  'draw-new': () => startDraw('new'),
  'draw-route': () => startDraw('route'),
  'draw-undo-stroke': () => { const d = S.draw, previous = d.strokeHistory.pop(); if (previous) { d.pts = previous.pts; d.snaps = previous.snaps; d.reached = previous.reached; drawTab(); } },
  'reshape-pick': () => pickRoadToReshape(),
  'partial-pick': () => pickRoadToReshape('partial'),
  'review-pick': () => pickRoadToReshape('review'),
  'cut-pick': () => pickRoadToReshape('cut'),
  'join-cancel': cancelJoin,
  'cut-cancel': () => { S.cut = null; setMode(null); drawTab(); },
  'cut-reset': () => { if (S.cut && !S.cut.busy) { S.cut.points = []; S.cut.preview = null; S.cut.whole = false; drawTab(); } },
  'review-save': async () => {
    const c = S.cut; if (!c?.review || !c.preview || c.busy) return;
    c.busy = true;
    try {
      await api('/roads/review', { ref: c.feature.properties.ref, points: c.points, note: $('#review-note').value.trim(), revision: c.revision });
      S.cut = null; setMode(null); await afterEdit(); await loadRoads(); drawTab(); toast('Unclear road portion saved.');
    } finally { c.busy = false; }
  },
  'review-remove': async (b) => {
    await api('/roads/review/remove', { ids: [b.dataset.id], revision: S.rev });
    await afterEdit(); await loadRoads(); drawTab(); toast('Road portion marked clear.');
  },
  'edge-access-start': () => { S.edgeAccess = { a: null, result: null, route: 0 }; setMode('edge-access', {}); drawTab(); },
  'edge-access-restart': () => { S.edgeAccess = { a: null, result: null, route: 0 }; setMode('edge-access', {}); drawTab(); },
  'edge-access-other': () => { S.edgeAccess.route = S.edgeAccess.route ? 0 : 1; drawTab(); },
  'edge-access-cancel': () => { S.edgeAccess = null; setMode(null); G.hl.clearLayers(); drawTab(); },
  'edge-access-save': async () => {
    const d = S.edgeAccess, route = d && d.result && d.result.routes[d.route || 0]; if (!route) return;
    const picked = $('#edge-access-value').value, value = picked === 'unknown' ? null : picked;
    await api('/edges/access', { refs: route.refs, access: value, revision: d.result.revision });
    S.edgeAccess = null; setMode(null); await afterEdit(); await loadRoads(); drawTab(); toast('Drivable saved.');
  },
  'partial-start': () => {
    const selection = S.cut; if (!selection?.reshape || !selection.preview) return;
    const old = selection.preview.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
    const anchors = selection.preview.properties.anchors;
    S.cut = null;
    startDraw('reshape-partial');
    Object.assign(S.draw, { ref: selection.feature.properties.ref, revision: selection.revision, snap: false,
      anchors, original: old.map(point => [...point]), pts: [[anchors[0][1], anchors[0][0]]],
      target: [anchors[1][1], anchors[1][0]], reached: false,
      partialSelection: { feature: selection.feature, revision: selection.revision } });
    S.draw.snaps = S.draw.pts.map(() => null); drawTab();
  },
  'partial-change-anchors': () => {
    const d = S.draw; if (!d || d.mode !== 'reshape-partial') return;
    const selection = d.partialSelection;
    stopDraw();
    S.cut = { feature: selection.feature, revision: selection.revision, points: [], reshape: true };
    setMode('cut'); drawTab();
  },
  'cut-save': async () => {
    const c = S.cut; if (!c || !c.preview || c.busy) return;
    if (!confirm(I18n.msg`Delete only the red ${fmt(c.preview.properties.removed_m, 1)} m? This may create a network gap. You can Undo.`)) return;
    c.busy = true;
    try { await api('/roads/cut', { ref: c.feature.properties.ref, points: c.points, whole: !!c.whole, revision: c.revision }); S.cut = null; setMode(null); await afterEdit(); await loadRoads(); drawTab(); toast(c.whole ? 'Selected section removed.' : 'Selected portion removed; outside pieces retained.'); }
    finally { c.busy = false; }
  },
  'reshape-cancel': () => { S.reshapePick = null; drawTab(); },
  'reshape-reset': () => {
    const d = S.draw;
    d.pts = d.mode === 'reshape-partial' ? [[d.anchors[0][1], d.anchors[0][0]]] : d.original.map(p => [...p]);
    d.snaps = d.pts.map(() => null); d.reached = false; d.strokeHistory = []; drawTab();
  },
  'draw-prolong': () => startDraw('prolong'),
  'draw-finish': () => finishDraw(),
  'draw-again': () => finishDraw(true),
  'draw-undo': () => { if (S.draw && S.draw.pts.length && !(isPlannedRoute(S.draw) && S.draw.pts.length === 1)) { /* the start of a route and anchor A of a partial reshape stay */ S.draw.pts.pop(); S.draw.snaps.pop(); S.draw.reached = false; if (!S.draw.pts.length && S.draw.mode === 'prolong') { S.draw.start = null; S.draw.join = null; } drawTab(); } },
  'draw-cancel': () => stopDraw(),
  'del-start': () => { S.del = { sel: new Set() }; drawTab(); },
  'del-clear': () => { S.del.sel.clear(); drawTab(); },
  'del-done': () => { S.del = null; drawTab(); },
  'del-apply': async () => {
    const sel = [...S.del.sel]; if (!sel.length) return;
    if (!confirm(`Delete ${sel.length} street edge${sel.length > 1 ? 's' : ''}? You can undo this.`)) return;
    await api('/edges/remove', { edges: sel.filter((x) => !x.startsWith('f:')), features: sel.filter((x) => x.startsWith('f:')).map((x) => x.slice(2)), user: user() });
    S.del.sel.clear(); await afterEdit(); await loadRoads(); toast(`${sel.length} edge${sel.length > 1 ? 's' : ''} deleted.`, 5000); drawTab();
  },
  'connect-sug': async (b) => { if (S.stage) { S.stage.connections[b.dataset.key] = S.sel.props.suggestion; await previewStage(false); S.sel = null; drawTab(); return; } const s = S.sel.props.suggestion; await api('/roads/connect', { node: b.dataset.key, target: s, user: user() }); await afterEdit(); await loadRoads(); S.sel = null; drawTab(); },
  'leave-node': async (b) => { if (S.stage) { S.stage.connections[b.dataset.key] = { type: 'none' }; await previewStage(false); S.sel = null; drawTab(); return; } await api('/roads/connect', { node: b.dataset.key, none: true, user: user() }); await afterEdit(); await loadRoads(); S.sel = null; drawTab(); },
  'reset-node': async (b) => { if (S.stage) { delete S.stage.connections[b.dataset.key]; await previewStage(false); S.sel = null; drawTab(); return; } await api('/roads/connect', { node: b.dataset.key, clear: true, user: user() }); await afterEdit(); await loadRoads(); S.sel = null; drawTab(); },
};
$('#panel').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-act]'); if (!b) return; e.preventDefault();
  try { await ACT[b.dataset.act](b); } catch (err) { toast(err.message, 5000); }
});
$('#panel').addEventListener('change', (e) => {
  if (S.draw && e.target.id === 'draw-uncertain') S.draw.uncertain = e.target.checked;
  if (S.draw && e.target.id === 'draw-tool') { endDrawStroke(); S.draw.tool = e.target.value; if (S.draw.tool === 'freehand') map.dragging.disable(); else map.dragging.enable(); drawTab(); }
  if (S.draw && e.target.id === 'draw-snap') { S.draw.snap = e.target.checked; if (!S.draw.snap) S.draw.snaps = S.draw.snaps.map((t, i) => S.draw.mode === 'prolong' && i === 0 ? t : null); G.hl.clearLayers(); drawTab(); }
  if (S.draw && ['draw-rank', 'draw-drv', 'draw-paved'].includes(e.target.id)) { const v = e.target.value; if (e.target.id === 'draw-rank') S.draw.rank = +v; else S.draw[e.target.id === 'draw-drv' ? 'drivable' : 'paved'] = JSON.parse(v); }
  if (e.target.id === 'roads-color') { S.roadColor = e.target.value; drawTab(); }
  if (e.target.id === 'color-mode') { S.idColor = e.target.value; drawTab(); }
  if (e.target.dataset && e.target.dataset.keep !== undefined && S.stage) {
    const f = S.stage.pv.replaced.features[+e.target.dataset.keep].properties, all = f.refs;
    S.stage.keep = e.target.checked ? [...new Set([...S.stage.keep, ...all])] : S.stage.keep.filter((r) => !all.includes(r));
    previewStage(false).then(() => drawTab()).catch((err) => toast(err.message, 5000));
  }
  if (e.target.id === 'attrs-file' && e.target.files[0]) {
    const rd = new FileReader();
    rd.onload = async () => { try { const r = await api('/streets/attrs/import', { content_b64: rd.result.split(',')[1] }); toast(`${r.changed} street${r.changed === 1 ? '' : 's'} changed`, 4000); await afterEdit(); } catch (err) { toast(err.message, 6000); } e.target.value = ''; };
    rd.readAsDataURL(e.target.files[0]); return;
  }
  if (e.target.id === 'roads-file' && e.target.files[0]) {
    const file = e.target.files[0]; const rd = new FileReader();
    rd.onload = async () => { try { const b64 = rd.result.split(',')[1]; S.del = null; S.stage = { filename: file.name, b64, features: null, connections: {}, keep: [], pv: null, fit: true }; await previewStage(true); S.sel = null; drawTab(); toast(`${S.stage.pv.summary.lines} lines read: check the merge, then accept or cancel`, 5000); } catch (err) { S.stage = null; toast(err.message, 6000); } };
    rd.readAsDataURL(file);
  }
});
$('#panel').addEventListener('toggle', (e) => { const d = e.target; if (d.dataset && d.dataset.sec) { S.openSec = S.openSec || {}; S.openSec[d.dataset.sec] = d.open; } }, true);
$('#panel').addEventListener('input', (e) => {
  if (e.target.id === 'draw-name' && S.draw) { S.draw.name = e.target.value; return; }
  if (e.target.id !== 'addr-search' || !S.addresses) return;
  const q = e.target.value.trim().toLowerCase(); const out = $('#addr-results');
  if (q.length < 2) { out.innerHTML = ''; return; }
  const p_ = (f) => f.properties;                                  // address (TCK 0575 0230 or written), name on the plaque, survey id
  const hits = S.addresses.houses.features.filter((f) => [p_(f).plate, p_(f).address, p_(f).plaque_name, p_(f).address_id, p_(f).building_id].join(' ').toLowerCase().includes(q)).slice(0, 15);
  out.innerHTML = hits.length ? I18n.html`<table>${hits.map((f) => I18n.html`<tr class="click" data-act="goto-house" data-id="${esc(p_(f).building_id)}"><td>${esc(p_(f).plate || p_(f).address || p_(f).address_id || p_(f).building_id)}</td><td class="muted">${esc(p_(f).plaque_name || p_(f).address_id || '')}${p_(f).plate ? '' : I18n.html` <span class="badge warn">${p_(f).quartier_code ? 'no plate yet' : 'no plate: quartier unknown'}</span>`}</td></tr>`).join('')}</table>` : I18n.htmlText('<p class="muted">Nothing found.</p>');
});
ACT['goto-point'] = (b) => { map.setView([+b.dataset.lat, +b.dataset.lon], 18); };
ACT['goto-house'] = (b) => { const f = S.addresses.houses.features.find((x) => x.properties.building_id === b.dataset.id); if (!f) return; const c = L.geoJSON(f).getBounds().getCenter(); map.setView(c, 19); S.sel = { type: 'house', props: f.properties, ll: c }; drawAccess(f.properties); renderPanel(); refreshSel(); };

/* ---------------------------------------------------------------- downloads (clear message when something has to be computed first) */
document.querySelector('.menu-body').addEventListener('click', async (e) => {
  const a = e.target.closest('a[data-dl]'); if (!a) return; e.preventDefault();
  try {
    const r = await fetch(a.getAttribute('href'));
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (x) { /* not json */ } toast(m, 6000); return; }
    const url = URL.createObjectURL(await r.blob()); const l = document.createElement('a'); l.href = url; l.download = a.dataset.dl; document.body.appendChild(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
    const st = r.headers.get('X-Osm-Stats'); if (st) { const s = JSON.parse(st); toast(`OSM file: ${s.new_ways} new ways, ${s.modified_ways} modified ways (${s.renamed_ways} renamed), ${s.new_nodes} new nodes. Open it in JOSM and check before uploading.`, 9000); }
  } catch (err) { toast(err.message, 6000); }
});

/* ---------------------------------------------------------------- header buttons */
$('#btn-undo').onclick = async () => { await api('/undo', {}); await afterEdit(); if (S.tab === 'roads') await loadRoads(); drawTab(); };
$('#btn-redo').onclick = async () => { await api('/redo', {}); await afterEdit(); if (S.tab === 'roads') await loadRoads(); drawTab(); };
async function computeAndWait() {
  S.computeStartedAt = Date.now(); showComputeStatus('Updating the map');
  await api('/compute', {}).catch(() => null);
  try {
    for (;;) {
      const j = await api('/job'); $('#job').textContent = `computing: ${j.step || ''}...`;
      if (j.state !== 'running') { if (j.state === 'error') throw new Error(j.error); showComputeStatus('Loading the completed map'); return; }
      showComputeStatus(j.step); await new Promise((r) => setTimeout(r, 700));
    }
  } finally { hideComputeStatus(); }
}
$('#btn-save').onclick = async () => {
  const label = prompt('Describe this checkpoint (optional):', ''); if (label === null) return;
  try {
    if (S.project.reference && (S.project.stale || !S.project.network_ready)) { toast('Computing before saving, so the street ids are stored too...', 6000); await computeAndWait(); S.network = await api('/network'); }
  } catch (e) { toast(`Could not compute: ${e.message}`, 6000); }
  const r = await api('/save', { label, user: user() }); await refreshProject(); drawTab();
  toast(r.ids_saved ? 'Saved: names and street ids are in the project database' : 'Saved (compute first to store the street ids too)');
};
const toggleWarnings = () => { const box=$('#warnings-box'); if(matchMedia('(max-width:900px)').matches) { box.classList.remove('collapsed'); box.classList.toggle('mobile-expanded'); } else box.classList.toggle('collapsed'); };
$('#btn-warnings').onclick = toggleWarnings; $('#warn-close').onclick = toggleWarnings;
$('#warn-list').addEventListener('click', (e) => { const w = e.target.closest('[data-warn]'); if (w) focusWarning(allWarnings()[+w.dataset.warn]); });
$('#btn-checkpoints').onclick = async () => {
  const cps = await api('/checkpoints'); const box = $('#modal'); $('#modal-title').textContent = 'Checkpoints (newest first)';
  $('#modal-content').innerHTML = I18n.html`<p class="muted">Edits are saved at once. Restoring adds a checkpoint (undoable).</p><table>${cps.map((c) => I18n.html`<tr><td>#${c.id}</td><td>${esc(c.ts.replace('T', ' ').slice(0, 16))}</td><td>${esc(c.label)}${c.user ? ' · ' + esc(c.user) : ''}</td><td>${c.named_streets} names${c.has_ids ? ' + ids' : ''}</td><td><button data-restore="${c.id}">Restore</button></td></tr>`).join('')}</table>`;
  box.hidden = false;
};
$('#modal-close').onclick = () => { $('#modal').hidden = true; };
$('#modal-content').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-restore]'); if (!b) return;
  if (!confirm(`Go back to checkpoint #${b.dataset.restore}? This changes the project for all editors.`)) return;
  const reason=AuthUI.state.enabled?prompt(AuthUI.t('Restore reason (required, at least 5 characters):')):'';
  if(AuthUI.state.enabled&&(!reason||reason.trim().length<5))return;
  await api('/restore', { id: +b.dataset.restore, revision:S.rev, reason, user: user() }); $('#modal').hidden = true; S.network = null; S.addresses = null;
  await refreshProject(); await loadStaticLayers(); drawTab(); if (S.project.reference) startCompute('network');
});

/* ---------------------------------------------------------------- other editors: poll the revision */
setInterval(async () => {
  if (!S.project || document.hidden) return;
  try {
    const r = await api('/revision');
    if (r.status.revision !== S.rev) {
      await refreshProject(); if (S.tab === 'roads') await loadRoads();
      toast('The project was changed by another editor'); drawTab();
    }
    if (r.fresh && r.network_hash && r.network_hash !== S.netHash && r.job.state !== 'running') { S.network = await api('/network'); S.addresses = null; await refreshProject(); drawTab(); toast('The network was recomputed'); }
  } catch (e) { /* offline or login expired: try again later */ }
}, 4000);

/* ---------------------------------------------------------------- start */
/* the reference point is confirmed (or moved) by every editor who did not set it: the default point, or one set by somebody else */
const refBox = () => $('#refbox');
function showRefOnly(r) {                              // only the node itself is drawn, never the point that was clicked or the previous one
  G.ref.clearLayers(); refMarkers(r, true).forEach((m) => m.addTo(G.ref)); G.ref.addTo(map);
}
function showMoveBox() {                               // choosing: no old point on the map, the nearest node follows the mouse
  S.referenceView={kind:'move'};
  const has = S.project && S.project.reference;
  G.ref.clearLayers();
  refBox().hidden = false;
  refBox().innerHTML = I18n.html`<img class="reference-logo" src="static/brand/community-addressing-cameroon.png" alt="Community Addressing Cameroon"><div class="refbox-title">Choose the reference point</div><p>Move over the map: the highlighted node is the one you get. Click to select it.</p>${has ? I18n.htmlText('<div class="row"><button id="ref-back">Keep the current point</button></div>') : ''}`;
  setMode('reference');
  if (has) $('#ref-back').onclick = () => { setMode(null); askReference(true); };
}
function tentativeReference(pick) {                    // a node was clicked: show it and ask before anything is saved
  S.referenceView={kind:'tentative',pick};
  const r = { lat: pick[2], lon: pick[1], node: pick[0] };
  setMode(null); hideRefNodes(); showRefOnly(r); map.panTo([r.lat, r.lon]);
  refBox().hidden = false;
  refBox().innerHTML = I18n.html`<img class="reference-logo" src="static/brand/community-addressing-cameroon.png" alt="Community Addressing Cameroon"><div class="refbox-title">Reference point</div><p>${I18n.msg`Use this node (${r.node}) as the reference point? The numbering of every street and house starts here.`}</p>
    <div class="row"><button class="primary" id="ref-yes">Yes, use it</button><button id="ref-other">No, choose another</button></div>`;
  $('#ref-yes').onclick = async () => {
    await api('/reference', { lat: r.lat, lon: r.lon, client: CLIENT, user: user() }); S.refConfirmed = true; refBox().hidden = true;
    toast(`Reference point set on node ${r.node}`); await afterEdit(); startCompute('network'); switchTab('ids');
  };
  $('#ref-other').onclick = () => { showMoveBox(); };
}
function askReference(force) {
  const r = S.project.reference; if (!r || (S.refConfirmed && !force)) return;
  S.referenceView={kind:'ask'};
  const what = r.name ? I18n.html`<strong>${esc(r.name)}</strong> (node ${r.node})` : `node ${r.node}`;
  showRefOnly(r);
  map.setView([r.lat, r.lon], 17, { animate: false });     // no animation: a view restored right after must not be undone when it ends
  refBox().hidden = false;
  refBox().innerHTML = I18n.html`<img class="reference-logo" src="static/brand/community-addressing-cameroon.png" alt="Community Addressing Cameroon"><div class="refbox-title">Reference point</div><p>${I18n.msg`The numbering of every street and house starts at the star on the map: ${what}, ${I18n.t(r.default ? 'the default point of this project' : 'set by another editor')}.`}</p>
    <p><strong>Is this the right place?</strong></p><div class="row"><button class="primary" id="ref-confirm">Yes, confirm it</button><button id="ref-move">No, I will move it</button></div>`;
  $('#ref-confirm').onclick = async () => {
    await api('/reference/confirm', { client: CLIENT }); S.refConfirmed = true; refBox().hidden = true; await refreshProject(); drawTab(); toast('Reference point confirmed');
  };
  $('#ref-move').onclick = () => showMoveBox();
}

window.addEventListener('languagechange', () => {
  if (!S.project) return;
  const controls=[...document.querySelectorAll('input[id]:not([type=file]),select[id],textarea[id]')]
    .filter(el=>el.id!=='language-select').map(el=>({id:el.id,value:el.value,checked:el.checked}));
  const center=map.getCenter(), zoom=map.getZoom(), view=S.referenceView;
  if (S.mode) setMode(S.mode.kind,S.mode.data);
  drawTab(); renderWorkAreas(); updateStaleBar(); renderWarnings();
  renderSaveState();
  if (!refBox().hidden) {
    if (view?.kind==='tentative') tentativeReference(view.pick);
    else if (view?.kind==='move') showMoveBox();
    else askReference(true);
  }
  if (S.sel) refreshSel();
  // A language change is a local preference, not a project edit or a reset.
  controls.forEach(({id,value,checked})=>{const el=document.getElementById(id);if(el){el.value=value;if(el.type==='checkbox')el.checked=checked;}});
  map.setView(center,zoom,{animate:false});
});

async function initApp() {
  if(S.initializing||S.ready)return;S.initializing=true;
  await refreshProject();
  await loadStaticLayers();
  askReference();
  if (!S.project.reference) { S.tab = 'ids'; $('#tabs').querySelectorAll('button').forEach((b) => b.classList.toggle('active', false)); drawTab(); S.ready = true; return; }
  const j = await api('/job');
  try { S.network = await api('/network'); } catch (e) { /* computing or not yet */ }
  let issues = false;                                        // graph problems (cut-off parts, roads not connected): start on the street editor
  try { issues = (await api('/base/components')).parts.length > 0 || ((S.network && S.network.warnings) || []).some((w) => ['disconnected', 'roads_isolated'].includes(w.code)); } catch (e) { /* no network yet */ }
  const saved = savedView();                                 // where this browser was before the refresh
  if (saved) { S.idColor = saved.idColor || S.idColor; S.fittedRoads = true; }
  await switchTab(saved && ['roads', 'ids', 'names', 'addresses'].includes(saved.tab) ? saved.tab : issues ? 'roads' : 'ids');
  if (saved && saved.quartier && quartierFeatures().some(f => f.properties.id === saved.quartier)) chooseQuartier(saved.quartier);
  else if (saved && saved.area && (S.project.work_areas?.features || []).some(f => f.properties.id === saved.area)) chooseWorkArea(saved.area);
  S.fitted = true;                                           // the view is set once at the start; later recomputations never move it
  if (saved) map.setView([saved.lat, saved.lon], saved.zoom, { animate: false });
  else if (S.network) map.setView([S.project.reference.lat, S.project.reference.lon], 16);
  if (!S.network) { if (j.state === 'running') pollJob('network'); else startCompute('network'); }
  if (j.state === 'running') pollJob(j.kind || 'network');
  S.ready = true;
}
AuthUI.ready.then(()=>{if(AuthUI.canView())initApp();});
window.addEventListener('authchange',async()=>{
  if(!S.ready) {await initApp();return;}
  await refreshProject();drawTab();
});
