'use strict';

function toPixel(map, lngLat) {
  if (!map || typeof map.project !== 'function') return null;
  const pt = map.project(lngLat);
  return { x: Math.round(pt.x), y: Math.round(pt.y) };
}
function reproject(map, overlayEl) {
  // Reproject labels
  overlayEl.querySelectorAll('[data-lng][data-lat]').forEach(el => {
    const lng = parseFloat(el.dataset.lng);
    const lat = parseFloat(el.dataset.lat);
    const pt = toPixel(map, [lng, lat]);
    if (!pt) return;
    el.style.left = `${pt.x}px`;
    el.style.top  = `${pt.y}px`;
  });

  // Reproject SVG arrow paths — redraw path d attribute
  overlayEl.querySelectorAll('svg[data-from-lng]').forEach(svgEl => {
    const fromLng = parseFloat(svgEl.dataset.fromLng);
    const fromLat = parseFloat(svgEl.dataset.fromLat);
    const toLng   = parseFloat(svgEl.dataset.toLng);
    const toLat   = parseFloat(svgEl.dataset.toLat);
    const arc     = parseFloat(svgEl.dataset.arc ?? 80);
    const curved  = svgEl.dataset.curved !== 'false';

    const from = toPixel(map, [fromLng, fromLat]);
    const to   = toPixel(map, [toLng,   toLat]);
    if (!from || !to) return;

    // Resize SVG to full overlay size
    const w = overlayEl.clientWidth;
    const h = overlayEl.clientHeight;
    svgEl.setAttribute('width', w);
    svgEl.setAttribute('height', h);
    svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`);

    const pathEl = svgEl.querySelector('path.arrow-path');
    if (pathEl) {
      const d = curved ? curvedPath(from, to, arc) : straightPath(from, to);
      pathEl.setAttribute('d', d);
      pathEl.style.setProperty('--path-length', pathEl.getTotalLength());
    }
  });

  // Reproject SVG fill overlays
  overlayEl.querySelectorAll('svg.effect-fill-svg[data-fill-lines]').forEach(svgEl => {
    let lines;
    try { lines = JSON.parse(svgEl.dataset.fillLines); } catch (_) { return; }
    const w = overlayEl.clientWidth;
    const h = overlayEl.clientHeight;
    svgEl.setAttribute('width', w);
    svgEl.setAttribute('height', h);
    svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`);
    const pathEl = svgEl.querySelector('path');
    if (!pathEl) return;
    const d = lines.map(ring => {
      const pts = ring.map(([lng, lat]) => toPixel(map, [lng, lat])).filter(Boolean);
      if (pts.length < 3) return '';
      return `M${pts[0].x},${pts[0].y} ${pts.slice(1).map(p => `L${p.x},${p.y}`).join(' ')} Z`;
    }).filter(Boolean).join(' ');
    if (d.trim()) pathEl.setAttribute('d', d);
  });

  // Reproject SVG pulse rings
  overlayEl.querySelectorAll('svg[data-center-lng]').forEach(svgEl => {
    const lng    = parseFloat(svgEl.dataset.centerLng);
    const lat    = parseFloat(svgEl.dataset.centerLat);
    const pt     = toPixel(map, [lng, lat]);
    if (!pt) return;
    const w = overlayEl.clientWidth;
    const h = overlayEl.clientHeight;
    svgEl.setAttribute('width', w);
    svgEl.setAttribute('height', h);
    svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svgEl.querySelectorAll('circle').forEach(circle => {
      circle.setAttribute('cx', pt.x);
      circle.setAttribute('cy', pt.y);
    });
  });

  // Reproject SVG border paths
  overlayEl.querySelectorAll('svg[data-border-lines]').forEach(svgEl => {
    const raw = svgEl.dataset.borderLines;
    if (!raw) return;
    let lines;
    try {
      lines = JSON.parse(raw);
    } catch (_err) {
      return;
    }
    svgEl.querySelectorAll('path.border-path').forEach((pathEl, i) => {
      const line = lines[i];
      if (!Array.isArray(line) || line.length < 2) return;
      const projected = line
        .map(([lng, lat]) => toPixel(map, [lng, lat]))
        .filter(Boolean);
      if (projected.length < 2) return;
      pathEl.setAttribute('d', polylinePath(projected));
      pathEl.style.setProperty('--path-length', pathEl.getTotalLength());
    });
  });

  // W13.T6 — sample overlay box occupancy into the layout sidecar.
  _maybeSnapshotLayout(overlayEl);

  // W26.T2 — keep screen-fixed text out of any active reserved media band.
  _enforceReservedBands(overlayEl);
}

/**
 * W26.T2 — active safe-area enforcement.
 *
 * Runs every reproject (deterministic stepTo + realtime camera moves). For each
 * screen-fixed text overlay (.effect-label that is not geo-pinned), shift its
 * inline `top` so it clears any active reserved band, eased by the band ramp;
 * restore the authored top once no band is active. Only `top` is touched —
 * scenes animate entrances via transform/translate, never top — so this never
 * fights label/title-card animations. Geo-pinned overlays (data-lng) are handled
 * by reprojection above and skipped here.
 */
function _enforceReservedBands(overlayEl) {
  var M = window.MapEffects;
  if (!M || !M.layoutHints || !M.layoutHints.activeBands) return;
  var t = Math.max(0, Number(M._currentT || 0));
  var bands = M.layoutHints.activeBands(t);
  var els = overlayEl.querySelectorAll('.effect-label:not([data-lng])');
  if (!els.length) return;
  var orect = overlayEl.getBoundingClientRect();
  var MARGIN = 18;

  els.forEach(function (el) {
    // Remember the authored top once (scenes never animate top).
    var baseTop = el.dataset.reserveBaseTop;
    if (baseTop === undefined) {
      var parsed = parseFloat(el.style.top);
      baseTop = isFinite(parsed) ? parsed : el.offsetTop;
      el.dataset.reserveBaseTop = String(baseTop);
    } else {
      baseTop = parseFloat(baseTop);
    }

    if (!bands.length) {
      if (el.dataset.reserveShifted === '1') {
        el.style.top = baseTop + 'px';
        el.dataset.reserveShifted = '0';
      }
      return;
    }

    // Measure the natural box at the authored position.
    el.style.top = baseTop + 'px';
    var r = el.getBoundingClientRect();
    var top = r.top - orect.top;
    var bottom = r.bottom - orect.top;

    var down = 0; // push toward +y to clear a top band
    var up = 0;   // push toward -y to clear a bottom band
    bands.forEach(function (bd) {
      var depth = bd.rectPx.h * bd.ramp;
      if (depth <= 0) return;
      if (bd.edge === 'top') {
        var need = (bd.rectPx.y + depth + MARGIN) - top;
        if (need > down) down = need;
      } else {
        var room = bottom - (bd.rectPx.y + bd.rectPx.h - depth - MARGIN);
        if (room > up) up = room;
      }
    });

    var shift = down > 0 ? down : (up > 0 ? -up : 0);
    if (shift !== 0) {
      el.style.top = (baseTop + shift) + 'px';
      el.dataset.reserveShifted = '1';
    } else if (el.dataset.reserveShifted === '1') {
      el.dataset.reserveShifted = '0';
    }
  });
}

/**
 * Snapshot normalized bounding boxes of overlay elements at 2 Hz of the
 * runtime clock (MapEffects._currentT). Captures own text overlays
 * (.map-label), elements explicitly tagged with data-kind (W11/W12 via
 * createOverlayEl), and any #labels-layer children. Geo SVG paths (arrows/
 * fills/borders) are intentionally excluded — their boxes span the frame and
 * are irrelevant to caption occupancy.
 */
function _maybeSnapshotLayout(overlayEl) {
  if (!window.MapEffects || !MapEffects._layoutFrames) return;
  const t = Math.max(0, Number(MapEffects._currentT || 0));
  const hz = MapEffects.LAYOUT_SAMPLE_HZ || 2;
  const minDelta = 1 / hz;
  const last = MapEffects._lastLayoutT;
  if (last !== -Infinity && t >= last && t < last + minDelta) return;
  MapEffects._lastLayoutT = t;

  const rect = overlayEl.getBoundingClientRect();
  const W = rect.width || overlayEl.clientWidth || 1;
  const H = rect.height || overlayEl.clientHeight || 1;

  const candidates = [];
  overlayEl.querySelectorAll('.map-label, [data-kind]').forEach(el => candidates.push(el));
  const labelsLayer = document.getElementById('labels-layer');
  if (labelsLayer) Array.prototype.forEach.call(labelsLayer.children, el => candidates.push(el));

  const seen = Object.create(null);
  const boxes = [];
  candidates.forEach(el => {
    if (!el || el.nodeType !== 1) return;
    const id = el.id || el.getAttribute('data-id') || `el-${boxes.length}`;
    if (seen[id]) return;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    let x = (r.left - rect.left) / W;
    let y = (r.top - rect.top) / H;
    let w = r.width / W;
    let h = r.height / H;
    x = Math.max(0, Math.min(1, x));
    y = Math.max(0, Math.min(1, y));
    if (x + w > 1) w = 1 - x;
    if (y + h > 1) h = 1 - y;
    w = Math.min(1, w);
    h = Math.min(1, h);
    if (w <= 0 || h <= 0) return;
    seen[id] = true;
    boxes.push({ id: String(id), kind: MapEffects._kindFromEl(el), x, y, w, h });
  });

  MapEffects._layoutFrames.push({ t, boxes });
}
function bindReproject(map, overlayEl) {
  const handler = () => reproject(map, overlayEl);
  map.on('move',    handler);
  map.on('moveend', handler);
  map.on('zoom',    handler);
  // Return unbind function for cleanup
  return () => {
    map.off('move',    handler);
    map.off('moveend', handler);
    map.off('zoom',    handler);
  };
}
