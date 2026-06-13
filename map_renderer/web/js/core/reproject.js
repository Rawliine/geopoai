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
