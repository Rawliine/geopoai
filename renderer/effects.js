/**
 * effects.js — Map Animation Effects Engine
 * Pure JS timing engine. No Mapbox dependency in this file.
 * map object is passed in at call time — works with any map
 * library that exposes .project(), .on(), .addSource(),
 * .addLayer(), .setPaintProperty() (Mapbox GL JS API).
 *
 * Exports (attach to window for browser, or use ES modules):
 *   applyFill(map, fillSpec)       → country/region fill with CSS effect
 *   drawArrow(map, overlayEl, arrowSpec) → animated SVG arrow
 *   showLabel(map, overlayEl, labelSpec) → geo-pinned or screen-fixed label
 *   runTimeline(map, overlayEl, scene)   → master sequencer → Promise
 *
 * Also exports internal utils for testing:
 *   reproject(map, overlayEl)      → re-pin all overlay elements
 *   clearOverlay(overlayEl)        → remove all arrows + labels
 */

'use strict';

/* ============================================================
   INTERNAL UTILS
   ============================================================ */

/**
 * Restart a CSS animation on an element.
 * Removes classes, forces reflow, re-adds classes.
 * @param {Element} el
 * @param {string[]} classes
 */
function restartAnimation(el, classes) {
  classes.forEach(c => el.classList.remove(c));
  void el.offsetWidth; // force reflow — critical trick
  classes.forEach(c => el.classList.add(c));
}

/**
 * Convert [lng, lat] → {x, y} pixel coords using map.project().
 * Returns null if map is not ready.
 * @param {object} map  - Mapbox GL JS map instance
 * @param {[number,number]} lngLat
 * @returns {{x:number, y:number}|null}
 */
function toPixel(map, lngLat) {
  if (!map || typeof map.project !== 'function') return null;
  const pt = map.project(lngLat);
  return { x: Math.round(pt.x), y: Math.round(pt.y) };
}

/**
 * Create a curved SVG cubic bezier path string between two pixel points.
 * arc controls how far the control point bows (positive = above line).
 * @param {{x,y}} from
 * @param {{x,y}} to
 * @param {number} arc  - control point offset in px (default: 80)
 * @returns {string}    - SVG path d attribute
 */
function curvedPath(from, to, arc = 80) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2 - arc;
  return `M${from.x},${from.y} Q${mx},${my} ${to.x},${to.y}`;
}

function polylinePath(points) {
  if (!points || points.length < 2) return '';
  const [first, ...rest] = points;
  return `M${first.x},${first.y} ${rest.map(p => `L${p.x},${p.y}`).join(' ')}`;
}

/**
 * Straight SVG path string between two pixel points.
 */
function straightPath(from, to) {
  return `M${from.x},${from.y} L${to.x},${to.y}`;
}

/**
 * Animate a dot traveling along an SVG path element.
 * @param {SVGPathElement} pathEl
 * @param {SVGCircleElement} dotEl
 * @param {number} durationMs
 * @param {number} delayMs
 */
function animateTravelDot(pathEl, dotEl, durationMs = 2000, delayMs = 0) {
  const len = pathEl.getTotalLength();
  let startTs = null;

  function step(ts) {
    if (!startTs) startTs = ts;
    const elapsed = ts - startTs;
    if (elapsed < delayMs) { requestAnimationFrame(step); return; }
    const progress = Math.min((elapsed - delayMs) / durationMs, 1);
    // Ease in-out cubic
    const t = progress < 0.5
      ? 4 * progress ** 3
      : 1 - (-2 * progress + 2) ** 3 / 2;
    const pt = pathEl.getPointAtLength(t * len);
    dotEl.setAttribute('cx', pt.x);
    dotEl.setAttribute('cy', pt.y);
    dotEl.style.opacity = progress < 0.05 ? progress / 0.05 : // fade in
                          progress > 0.9  ? (1 - progress) / 0.1 : 1; // fade out
    if (progress < 1) requestAnimationFrame(step);
  }

  requestAnimationFrame(step);
}

/**
 * Typewriter effect — splits text into spans, reveals per-character.
 * @param {HTMLElement} el
 * @param {string} text
 * @param {number} charIntervalMs
 * @param {number} delayMs
 * @returns {Promise} resolves when typing completes
 */
function typewriterReveal(el, text, charIntervalMs = 70, delayMs = 0) {
  return new Promise(resolve => {
    el.innerHTML = '';
    el.classList.remove('done');

    [...text].forEach(ch => {
      const span = document.createElement('span');
      span.className = 'char';
      span.textContent = ch === ' ' ? '\u00A0' : ch;
      el.appendChild(span);
    });

    const chars = el.querySelectorAll('.char');
    chars.forEach((char, i) => {
      setTimeout(() => {
        char.classList.add('visible');
        if (i === chars.length - 1) {
          el.classList.add('done');
          resolve();
        }
      }, delayMs + i * charIntervalMs);
    });
  });
}

/**
 * Animate a number counter from → to.
 * @param {HTMLElement} el
 * @param {number} from
 * @param {number} to
 * @param {number} durationMs
 * @param {string} [suffix='']   - e.g. 'K', '%', ' DIV'
 * @returns {Promise}
 */
function animateCounter(el, from, to, durationMs = 1500, suffix = '') {
  return new Promise(resolve => {
    let start = null;
    function step(ts) {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / durationMs, 1);
      const eased = 1 - (1 - progress) ** 3;
      el.textContent = Math.round(from + (to - from) * eased) + suffix;
      el.classList.add('tick');
      setTimeout(() => el.classList.remove('tick'), 80);
      if (progress < 1) requestAnimationFrame(step);
      else resolve();
    }
    requestAnimationFrame(step);
  });
}


/* ============================================================
   REPROJECT — Re-pin overlay elements after camera move
   Must be called on map 'move' and 'moveend' events.
   Elements that need reprojecting must have data-lng / data-lat.
   ============================================================ */

/**
 * Reproject all geo-pinned elements in the overlay.
 * JS sets data-lng and data-lat when creating each element.
 * @param {object} map
 * @param {HTMLElement} overlayEl
 */
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

/**
 * Remove all dynamically-created arrows and labels from overlay.
 * Leaves the SVG defs (arrowhead markers) intact.
 */
function clearOverlay(overlayEl) {
  overlayEl.querySelectorAll('.effect-arrow, .effect-label, .effect-pulse-ring, .effect-fill-svg').forEach(el => el.remove());
}


/* ============================================================
   applyFill(map, fillSpec)
   Adds a GeoJSON polygon fill layer to Mapbox with CSS effect.

   fillSpec shape:
   {
     id:        string,          // unique layer id (e.g. "ukraine-fill")
     geojson:   GeoJSON object,  // the polygon geometry
     color:     string,          // hex color
     opacity:   number,          // 0–1 (default 0.6)
     effect:    string,          // CSS class name from effects.css
     duration:  number,          // animation duration in seconds
     delay:     number,          // animation delay in seconds
     // For contested effect:
     colorB:    string,          // second color
   }
   ============================================================ */

/* ── Fill SVG helpers ──────────────────────────────────────── */

function _elasticOut(t) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI / 3)) + 1;
}

function _createFillSVG(map, overlayEl, geojson, id, color, opacity) {
  const lines = _geojsonToBorderLines(geojson);
  if (!lines.length) return null;
  const w = overlayEl.clientWidth || 1920;
  const h = overlayEl.clientHeight || 1080;
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.id = `${id}-fill-svg`;
  svg.classList.add('effect-fill-svg');
  svg.dataset.fillLines = JSON.stringify(lines);
  svg.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;overflow:visible;';
  const d = lines.map(ring => {
    const pts = ring.map(([lng, lat]) => toPixel(map, [lng, lat])).filter(Boolean);
    if (pts.length < 3) return '';
    return `M${pts[0].x},${pts[0].y} ${pts.slice(1).map(p => `L${p.x},${p.y}`).join(' ')} Z`;
  }).filter(Boolean).join(' ');
  if (!d.trim()) return null;
  const path = document.createElementNS(svgNS, 'path');
  path.setAttribute('d', d);
  path.setAttribute('fill', color);
  path.setAttribute('fill-opacity', opacity);
  path.setAttribute('fill-rule', 'evenodd');
  path.setAttribute('stroke', 'none');
  svg.appendChild(path);
  overlayEl.appendChild(svg);
  return svg;
}

function _applyWipeProgress(svgEl, progress, direction) {
  const r = ((1 - progress) * 100).toFixed(2);
  switch (direction) {
    case 'rtl': svgEl.style.clipPath = `inset(0 0 0 ${r}%)`; break;
    case 'ttb': svgEl.style.clipPath = `inset(0 0 ${r}% 0)`; break;
    case 'btt': svgEl.style.clipPath = `inset(${r}% 0 0 0)`; break;
    default:    svgEl.style.clipPath = `inset(0 ${r}% 0 0)`; break;
  }
}

function applyFill(map, fillSpec, overlayEl) {
  const {
    id,
    geojson,
    color      = '#e74c3c',
    opacity    = 0.6,
    effect     = 'fill-fade',
    duration   = 1.2,
    delay      = 0,
    colorB,
    origin,
    deterministic = false,
  } = fillSpec;
  if (!geojson) {
    console.warn('[effects.js] applyFill: missing geojson (or unresolved country reference)');
    return null;
  }

  const sourceId = `${id}-source`;
  const layerId  = `${id}-layer`;

  if (map.getSource(sourceId)) {
    map.getSource(sourceId).setData(geojson);
  } else {
    map.addSource(sourceId, { type: 'geojson', data: geojson });
  }
  if (!map.getLayer(layerId)) {
    map.addLayer({ id: layerId, type: 'fill', source: sourceId,
                   paint: { 'fill-color': color, 'fill-opacity': 0 } });
  } else {
    map.setPaintProperty(layerId, 'fill-color', color);
    map.setPaintProperty(layerId, 'fill-opacity', 0);
  }

  // ── Wipe effects — visible SVG filled path + clip-path animation ──
  const wipeDir = effect === 'fill-wipe'     ? 'ltr'
                : effect === 'fill-wipe-rtl' ? 'rtl'
                : effect === 'fill-wipe-ttb' ? 'ttb'
                : effect === 'fill-wipe-btt' ? 'btt'
                : null;

  if (wipeDir !== null) {
    const svgEl = overlayEl && _createFillSVG(map, overlayEl, geojson, id, color, opacity);
    if (svgEl) {
      _applyWipeProgress(svgEl, 0, wipeDir);
      if (!deterministic) {
        const startMs = performance.now() + delay * 1000;
        (function step() {
          if (performance.now() < startMs) { requestAnimationFrame(step); return; }
          const p = Math.min(1, (performance.now() - startMs) / (duration * 1000));
          _applyWipeProgress(svgEl, p, wipeDir);
          if (p < 1) { requestAnimationFrame(step); }
          else { svgEl.remove(); map.setPaintProperty(layerId, 'fill-opacity', opacity); }
        })();
      }
    } else {
      map.setPaintProperty(layerId, 'fill-opacity', opacity);
    }
    return { layerId, sourceId };
  }

  // ── fill-ripple — visible SVG + scale-from-origin animation ──
  if (effect === 'fill-ripple') {
    const svgEl = overlayEl && _createFillSVG(map, overlayEl, geojson, id, color, opacity);
    if (svgEl) {
      let ox = 50, oy = 50;
      if (origin && Array.isArray(origin) && origin.length >= 2) {
        const pt = toPixel(map, origin);
        if (pt) {
          ox = (pt.x / (overlayEl.clientWidth  || 1920)) * 100;
          oy = (pt.y / (overlayEl.clientHeight || 1080)) * 100;
        }
      }
      svgEl.style.transformOrigin = `${ox}% ${oy}%`;
      svgEl.style.transform = 'scale(0)';
      if (!deterministic) {
        const startMs = performance.now() + delay * 1000;
        (function step() {
          if (performance.now() < startMs) { requestAnimationFrame(step); return; }
          const p = Math.min(1, (performance.now() - startMs) / (duration * 1000));
          svgEl.style.transform = `scale(${_elasticOut(p)})`;
          if (p < 1) { requestAnimationFrame(step); }
          else { svgEl.remove(); map.setPaintProperty(layerId, 'fill-opacity', opacity); }
        })();
      }
    } else {
      map.setPaintProperty(layerId, 'fill-opacity', opacity);
    }
    return { layerId, sourceId };
  }

  // ── fill-fade — animate Mapbox fill-opacity directly ─────────
  if (effect === 'fill-fade') {
    if (!deterministic) {
      const startMs = performance.now() + delay * 1000;
      (function step() {
        if (performance.now() < startMs) { requestAnimationFrame(step); return; }
        const p = Math.min(1, (performance.now() - startMs) / (duration * 1000));
        map.setPaintProperty(layerId, 'fill-opacity', opacity * (1 - (1 - p) ** 3));
        if (p < 1) requestAnimationFrame(step);
      })();
    }
    // deterministic: stepTo drives fill-opacity each frame
    return { layerId, sourceId };
  }

  // ── fill-contested / fill-contested-smooth — SVG path with CSS color animation ──
  if (effect === 'fill-contested' || effect === 'fill-contested-smooth') {
    const svgEl = overlayEl && _createFillSVG(map, overlayEl, geojson, id, color, opacity);
    if (svgEl) {
      const path = svgEl.querySelector('path');
      path.style.setProperty('--effect-color-a', color);
      path.style.setProperty('--effect-color-b', colorB ?? '#3498db');
      path.style.setProperty('--effect-duration', `${duration}s`);
      path.style.setProperty('--effect-delay', `${delay}s`);
      path.style.setProperty('--fill-opacity', opacity);
      if (!deterministic) {
        void path.getBoundingClientRect();
        path.classList.add(effect);
      }
      // deterministic mode: color stepped per-frame in _updateFillDeterministic
    } else {
      map.setPaintProperty(layerId, 'fill-opacity', opacity);
    }
    return { layerId, sourceId };
  }

  // Unknown effect — fall back to Mapbox layer opacity
  map.setPaintProperty(layerId, 'fill-opacity', opacity);
  return { layerId, sourceId };
}

function _geojsonToBorderLines(geojson) {
  if (!geojson) return [];
  const source = geojson.type === 'Feature' ? geojson.geometry : geojson;
  if (!source) return [];
  if (source.type === 'LineString') return [source.coordinates];
  if (source.type === 'MultiLineString') return source.coordinates;
  if (source.type === 'Polygon') return source.coordinates;
  if (source.type === 'MultiPolygon') return source.coordinates.flat();
  return [];
}

function applyBorder(map, overlayEl, borderSpec) {
  const {
    id = `border-${Date.now()}`,
    geojson,
    color = '#f0c040',
    width = 2.5,
    effect = 'border-trim',
    duration = 1.2,
    delay = 0,
    glowColor,
    dashPattern,
  } = borderSpec;

  const lines = _geojsonToBorderLines(geojson);
  if (!lines.length) {
    console.warn('[effects.js] applyBorder: unsupported or empty geojson');
    return null;
  }

  const w = overlayEl.clientWidth;
  const h = overlayEl.clientHeight;
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.classList.add('effect-border');
  svg.id = id;
  svg.dataset.borderLines = JSON.stringify(lines);
  svg.style.cssText = `
    position: absolute; top: 0; left: 0; pointer-events: none;
    overflow: visible;
    --effect-duration: ${duration}s;
    --effect-delay: ${delay}s;
    --glow-color: ${glowColor ?? color};
  `;

  lines.forEach(line => {
    const projected = line
      .map(([lng, lat]) => toPixel(map, [lng, lat]))
      .filter(Boolean);
    if (projected.length < 2) return;
    const path = document.createElementNS(svgNS, 'path');
    path.classList.add('border-path');
    path.setAttribute('d', polylinePath(projected));
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', color);
    path.setAttribute('stroke-width', width);
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    if (dashPattern) {
      path.setAttribute(
        'stroke-dasharray',
        Array.isArray(dashPattern) ? dashPattern.join(' ') : String(dashPattern)
      );
    }
    svg.appendChild(path);
    path.style.setProperty('--path-length', path.getTotalLength());
    void path.getBoundingClientRect();
    if (effect) path.classList.add(effect);
  });

  overlayEl.appendChild(svg);
  return svg;
}

function removeBorder(overlayEl, id, exitDuration = 0.6) {
  if (!id) return;
  const el = document.getElementById(id);
  if (!el || !el.classList.contains('effect-border')) return;
  el.style.setProperty('--exit-duration', `${exitDuration}s`);
  el.classList.add('border-exit');
  setTimeout(() => { if (el.parentNode) el.remove(); }, exitDuration * 1000 + 50);
}

function _triggerArrowExit(el, exitDuration = 0.6) {
  const pathEl = el.querySelector('path.arrow-path');
  const dotEl  = el.querySelector('.travel-dot');
  if (pathEl) {
    const pathLen = parseFloat(pathEl.style.getPropertyValue('--path-length'))
                    || el.style.getPropertyValue('--path-length')
                    || 1000;
    el.style.setProperty('--exit-duration', `${exitDuration}s`);
    pathEl.style.strokeDasharray  = `${pathLen}`;
    pathEl.style.strokeDashoffset = '0';
    pathEl.classList.remove('arrow-draw', 'arrow-draw-headed', 'arrow-glow', 'arrow-entrance', 'arrow-exit');
    void pathEl.getBoundingClientRect();
    pathEl.classList.add('arrow-exit');
  }
  if (dotEl) {
    dotEl.classList.remove('travel-dot');
    dotEl.style.transition = `opacity ${exitDuration}s ease-out`;
    dotEl.style.opacity = '0';
  }
}

function removeArrow(overlayEl, id, exitDuration = 0.6) {
  if (!id) return;
  const el = document.getElementById(id);
  if (!el || !el.classList.contains('effect-arrow')) return;
  _triggerArrowExit(el, exitDuration);
  setTimeout(() => { if (el.parentNode) el.remove(); }, exitDuration * 1000 + 50);
}

/**
 * pulseRing(map, overlayEl, spec)
 * Emits N expanding SVG ring circles from a geographic point.
 *
 * spec shape:
 * {
 *   id:       string,
 *   center:   [lng, lat],    // geographic epicenter
 *   color:    string,        // stroke color (default '#ffffff')
 *   count:    number,        // rings to emit (default 1)
 *   radius:   number,        // max ring radius in px (default 80)
 *   width:    number,        // stroke width px (default 2)
 *   duration: number,        // seconds per ring (default 1.4)
 *   stagger:  number,        // seconds between rings (default 0.4)
 *   delay:    number,        // seconds before first ring (default 0)
 * }
 */
function pulseRing(map, overlayEl, spec) {
  const {
    id           = `pulse-${Date.now()}`,
    center,
    color        = '#ffffff',
    dotColor,
    dotRadius    = 5,
    count        = 3,
    radius       = 80,
    width        = 2,
    duration     = 4.0,  // total effect lifetime (seconds)
    ringDuration = 1.8,  // per-ring expansion time (seconds)
    delay        = 0,
    stagger,             // legacy: if set, uses old stagger-based spacing
  } = spec;

  if (!center) {
    console.warn('[effects.js] pulseRing: missing center');
    return null;
  }

  const pt = toPixel(map, center);
  if (!pt) return null;

  const w = overlayEl.clientWidth;
  const h = overlayEl.clientHeight;
  const svgNS = 'http://www.w3.org/2000/svg';

  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.classList.add('effect-pulse-ring');
  svg.id = id;
  svg.dataset.centerLng  = center[0];
  svg.dataset.centerLat  = center[1];
  svg.dataset.ringRadius = radius;
  svg.style.cssText = `position: absolute; top: 0; left: 0; pointer-events: none; overflow: visible;`;

  // Static center dot — no animation, tracks the geo point
  if (dotRadius > 0) {
    const dot = document.createElementNS(svgNS, 'circle');
    dot.setAttribute('cx', pt.x);
    dot.setAttribute('cy', pt.y);
    dot.setAttribute('r', dotRadius);
    dot.setAttribute('fill', dotColor ?? color);
    dot.setAttribute('opacity', '0.9');
    svg.appendChild(dot);
  }

  // Legacy stagger mode: duration = per-ring expansion time (original semantics)
  // Radar mode (default): duration = total effect lifetime, ringDuration = per-ring expansion
  const isLegacy = stagger !== undefined;
  const effectiveRingDuration = isLegacy ? duration : ringDuration;
  const spacing = isLegacy ? stagger : (count > 0 ? duration / count : duration);

  for (let i = 0; i < count; i++) {
    const ringDelay = isLegacy
      ? delay + i * stagger                      // legacy: first ring at t=delay
      : delay + spacing * 0.5 + i * spacing;    // radar: distribute with leading margin

    const circle = document.createElementNS(svgNS, 'circle');
    circle.setAttribute('cx', pt.x);
    circle.setAttribute('cy', pt.y);
    circle.setAttribute('r', radius);
    circle.setAttribute('fill', 'none');
    circle.setAttribute('stroke', color);
    circle.setAttribute('stroke-width', width);
    circle.style.setProperty('--ring-duration', `${effectiveRingDuration}s`);
    circle.style.setProperty('--ring-delay', `${ringDelay}s`);
    circle.classList.add('fill-ripple-ring');
    svg.appendChild(circle);
  }

  overlayEl.appendChild(svg);

  // Legacy cleanup: last ring ends at delay + (count-1)*stagger + duration
  // Radar cleanup: total lifetime is duration, plus time for last ring to finish
  const totalMs = isLegacy
    ? (delay + duration + (count - 1) * stagger + 0.2) * 1000
    : (delay + duration + ringDuration + 0.2) * 1000;
  setTimeout(() => { if (svg.parentNode) svg.remove(); }, totalMs);

  return svg;
}

function executeTimelineAction(map, overlayEl, entry, ctx = {}) {
  const params = entry.params ?? {};
  switch (entry.action) {
    case 'applyFill':
      applyFill(map, Object.assign({}, params, { deterministic: Boolean(ctx.deterministic) }), overlayEl);
      if (ctx.runtime && params.id) ctx.runtime.createdFillIds.add(params.id);
      break;
    case 'applyBorder': {
      const border = applyBorder(map, overlayEl, params);
      if (ctx.runtime && border?.id) ctx.runtime.createdBorderIds.add(border.id);
      break;
    }
    case 'removeBorder': {
      const exitDur = params.exitDuration ?? 0.6;
      if (ctx.deterministic && ctx.runtime) {
        const el = document.getElementById(params.id);
        if (el && el.classList.contains('effect-border')) {
          // Track per-frame opacity via scene time (CSS time != scene time in deterministic mode)
          ctx.runtime.pendingBorderExits.push({
            id: params.id, startT: entry.at ?? 0, exitDuration: exitDur,
          });
        }
      } else {
        removeBorder(overlayEl, params.id, exitDur);
      }
      break;
    }
    case 'drawArrow': {
      const arrow = drawArrow(map, overlayEl, params);
      if (ctx.runtime && arrow?.id) ctx.runtime.createdArrowIds.add(arrow.id);
      break;
    }
    case 'removeArrow': {
      const exitDur = params.exitDuration ?? 0.6;
      if (ctx.deterministic && ctx.runtime) {
        const el = document.getElementById(params.id);
        if (el && el.classList.contains('effect-arrow')) {
          _triggerArrowExit(el, exitDur);
          ctx.runtime.pendingRemovals.push({ id: params.id, removeAt: (entry.at ?? 0) + exitDur });
        }
      } else {
        removeArrow(overlayEl, params.id, exitDur);
      }
      break;
    }
    case 'pulseRing': {
      const ring = pulseRing(map, overlayEl, params);
      if (ctx.runtime && ring?.id) ctx.runtime.createdPulseRingIds.add(ring.id);
      break;
    }
    case 'showLabel':
      showLabel(map, overlayEl, params);
      break;
    case 'clearOverlay':
      clearOverlay(overlayEl);
      break;
    case 'removeLabel': {
      if (ctx.deterministic && ctx.runtime) {
        ctx.runtime.removedLabelIds.add(params.id);
      }
      const el = document.getElementById(params.id);
      if (el) {
        if (ctx.deterministic && ctx.runtime) {
          ctx.runtime.pendingRemovals.push({ id: params.id, removeAt: (entry.at ?? 0) + 0.6 });
          el.classList.add('label-fade-out');
        } else {
          el.classList.add('label-fade-out');
          setTimeout(() => el.remove(), 600);
        }
      }
      break;
    }
    case 'removeLayer': {
      const { id } = params;
      const exitDur   = params.exitDuration ?? 0.6;
      const layerId2  = `${id}-layer`;
      const sourceId2 = `${id}-source`;

      if (ctx.deterministic && ctx.runtime) {
        const startOpacity = map.getLayer(layerId2)
          ? (map.getPaintProperty(layerId2, 'fill-opacity') ?? 0.6)
          : 0;
        if (!ctx.runtime.pendingFillExits) ctx.runtime.pendingFillExits = [];
        ctx.runtime.pendingFillExits.push({
          layerId: layerId2, sourceId: sourceId2,
          startT: entry.at ?? 0, startOpacity, exitDuration: exitDur,
          overlayId: `${id}-overlay`,
        });
        // Remove SVG fill overlay immediately (it was only used during entrance animation)
        const fillSvg2 = document.getElementById(`${id}-fill-svg`);
        if (fillSvg2) fillSvg2.remove();
      } else {
        if (map.getLayer(layerId2)) {
          const startOpacity = map.getPaintProperty(layerId2, 'fill-opacity') ?? 0.6;
          const startMs = performance.now();
          (function step() {
            const p = Math.min(1, (performance.now() - startMs) / (exitDur * 1000));
            map.setPaintProperty(layerId2, 'fill-opacity', startOpacity * (1 - p));
            if (p < 1) { requestAnimationFrame(step); }
            else {
              if (map.getLayer(layerId2))  map.removeLayer(layerId2);
              if (map.getSource(sourceId2)) map.removeSource(sourceId2);
            }
          })();
        } else if (map.getSource(sourceId2)) {
          map.removeSource(sourceId2);
        }
        const overlayFill = document.getElementById(`${id}-overlay`);
        if (overlayFill) overlayFill.remove();
        const fillSvg3 = document.getElementById(`${id}-fill-svg`);
        if (fillSvg3) fillSvg3.remove();
      }
      break;
    }
    case 'cameraShake': {
      if (ctx.deterministic && ctx.runtime) {
        const { intensity = 'medium', durationMs = 400 } = params;
        ctx.runtime.cameraShakeActive = {
          start: Number(entry.at ?? 0),
          duration: Math.max(0, Number(durationMs) / 1000),
          intensity: String(intensity),
        };
      } else {
        const { intensity = 'medium', durationMs = 400 } = params;
        const container = map.getContainer();
        const amplitudes = { light: 3, medium: 6, heavy: 12 };
        const amp = amplitudes[intensity] ?? 6;
        container.style.transition = 'none';
        let elapsed = 0;
        const interval = 30;
        const shakeTimer = setInterval(() => {
          elapsed += interval;
          const dx = (Math.random() - 0.5) * amp;
          const dy = (Math.random() - 0.5) * amp;
          container.style.transform = `translate(${dx}px, ${dy}px)`;
          if (elapsed >= durationMs) {
            clearInterval(shakeTimer);
            container.style.transform = '';
          }
        }, interval);
      }
      break;
    }
    case 'flyTo':
      if (!ctx.deterministic) {
        map.flyTo({
          center:   params.center,
          zoom:     params.zoom,
          pitch:    params.pitch ?? 0,
          bearing:  params.bearing ?? 0,
          duration: (params.duration ?? 2) * 1000,
          essential: true,
        });
      }
      break;
    default:
      console.warn(`[effects.js] unknown action "${entry.action}"`);
  }
}


/* ============================================================
   drawArrow(map, overlayEl, arrowSpec)
   Creates animated SVG arrow between two geographic points.

   arrowSpec shape:
   {
     id:       string,           // unique id
     from:     [lng, lat],
     to:       [lng, lat],
     color:    string,           // stroke color
     width:    number,           // stroke width px (default 2.5)
     effect:   string,           // 'arrow-draw' | 'arrow-travel' | 'arrow-glow'
     curved:   boolean,          // true = bezier arc (default true)
     arc:      number,           // arc height in px (default 80)
     headed:   boolean,          // show arrowhead marker (default true)
     glowColor: string,          // for arrow-glow effect
     duration: number,           // seconds
     delay:    number,           // seconds
   }
   ============================================================ */

function drawArrow(map, overlayEl, arrowSpec) {
  const {
    id       = `arrow-${Date.now()}`,
    from,
    to,
    color    = '#e74c3c',
    width    = 2.5,
    effect   = 'arrow-draw',
    curved   = true,
    arc      = 80,
    headed   = true,
    glowColor,
    duration = 1.8,
    delay    = 0,
  } = arrowSpec;

  const fromPx = toPixel(map, from);
  const toPx   = toPixel(map, to);
  if (!fromPx || !toPx) {
    console.warn('[effects.js] drawArrow: could not project coordinates', from, to);
    return null;
  }

  const w = overlayEl.clientWidth;
  const h = overlayEl.clientHeight;

  // --- Build SVG ---
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.classList.add('effect-arrow');
  svg.id = id;

  // Store geo coords for reprojection on camera move
  svg.dataset.fromLng = from[0];
  svg.dataset.fromLat = from[1];
  svg.dataset.toLng   = to[0];
  svg.dataset.toLat   = to[1];
  svg.dataset.arc     = arc;
  svg.dataset.curved  = curved;

  svg.style.cssText = `
    position: absolute; top: 0; left: 0; pointer-events: none;
    overflow: visible;
    --path-length: 0;
    --effect-duration: ${duration}s;
    --effect-delay: ${delay}s;
    --glow-color: ${glowColor ?? color};
  `;

  // --- Arrowhead marker (defined in defs) ---
  if (headed) {
    const defs = document.createElementNS(svgNS, 'defs');
    const markerId = `arrowhead-${id}`;
    defs.innerHTML = `
      <marker id="${markerId}" markerWidth="8" markerHeight="6"
              refX="7" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="${color}"/>
      </marker>`;
    svg.appendChild(defs);
  }

  // --- Main path ---
  const pathD = curved
    ? curvedPath(fromPx, toPx, arc)
    : straightPath(fromPx, toPx);

  const path = document.createElementNS(svgNS, 'path');
  path.classList.add('arrow-path');
  path.setAttribute('d', pathD);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', color);
  path.setAttribute('stroke-width', width);
  path.setAttribute('stroke-linecap', 'round');
  if (headed) path.setAttribute('marker-end', `url(#arrowhead-${id})`);

  svg.appendChild(path);

  // Set path length BEFORE adding animation class
  const pathLen = path.getTotalLength();
  svg.style.setProperty('--path-length', pathLen);

  // --- Apply effect ---
  if (effect === 'arrow-travel') {
    // Faint base path draws on first, then dot travels
    path.setAttribute('stroke', `${color}44`);
    path.setAttribute('stroke-width', width * 0.7);

    const dot = document.createElementNS(svgNS, 'circle');
    dot.classList.add('travel-dot');
    dot.setAttribute('cx', fromPx.x);
    dot.setAttribute('cy', fromPx.y);
    dot.style.setProperty('--glow-color', glowColor ?? color);
    dot.style.setProperty('--dot-radius', '5px');
    dot.style.opacity = '0'; // hidden while path draws on
    svg.appendChild(dot);

    // Phase 1: draw faint path on from origin → destination
    const entranceDur = Math.min(0.9, duration * 0.25);
    svg.style.setProperty('--entrance-duration', `${entranceDur}s`);
    void path.getBoundingClientRect();
    path.classList.add('arrow-entrance');

    overlayEl.appendChild(svg);

    // Phase 2: after entrance, start dot travel
    setTimeout(() => {
      if (!path.parentNode) return;
      path.classList.remove('arrow-entrance');
      path.style.removeProperty('stroke-dasharray');
      path.style.removeProperty('stroke-dashoffset');
      dot.style.opacity = '';
      animateTravelDot(path, dot, duration * 1000, 0);
    }, (delay + entranceDur) * 1000 + 50);

  } else if (effect === 'arrow-draw') {
    void path.getBoundingClientRect();
    path.classList.add('arrow-draw');
    if (headed) path.classList.add('arrow-draw-headed');
    overlayEl.appendChild(svg);

  } else {
    // arrow-glow: draw on first, then switch to glow pulse
    const entranceDur = Math.min(0.9, duration * 0.35);
    svg.style.setProperty('--entrance-duration', `${entranceDur}s`);
    void path.getBoundingClientRect();
    path.classList.add('arrow-entrance');
    overlayEl.appendChild(svg);

    setTimeout(() => {
      if (!path.parentNode) return;
      path.classList.remove('arrow-entrance');
      path.style.removeProperty('stroke-dasharray');
      path.style.removeProperty('stroke-dashoffset');
      void path.getBoundingClientRect();
      path.classList.add('arrow-glow');
    }, (delay + entranceDur) * 1000 + 50);
  }

  return svg;
}


/* ============================================================
   showLabel(map, overlayEl, labelSpec)
   Creates a positioned HTML label in the overlay.

   labelSpec shape:
   {
     id:       string,
     text:     string,
     position: [lng, lat] | { x: number, y: number },
                           // [lng,lat] = geo-pinned (reprojected on move)
                           // {x,y}    = screen-fixed px from top-left
     anchor:   string,     // CSS transform-origin: 'center' | 'top-left' etc.
     effect:   string,     // 'label-slam' | 'label-typewriter' | 'label-fade'
     fontSize: string,     // CSS font-size (default '1rem')
     color:    string,     // CSS color (default '#f0c040')
     duration: number,     // seconds
     delay:    number,     // seconds
     charInterval: number, // ms per char for typewriter (default 70)
     // For counter:
     isCounter: boolean,
     counterFrom: number,
     counterTo: number,
     counterSuffix: string,
   }
   ============================================================ */

function showLabel(map, overlayEl, labelSpec) {
  const {
    id            = `label-${Date.now()}`,
    text          = '',
    position,
    anchor        = 'center',
    effect        = 'label-fade',
    fontSize      = '1rem',
    color         = '#f0c040',
    duration      = 0.8,
    delay         = 0,
    charInterval  = 70,
    isCounter     = false,
    counterFrom   = 0,
    counterTo     = 100,
    counterSuffix = '',
  } = labelSpec;

  // --- Compute pixel position ---
  let px;
  let isGeoPinned = false;

  if (Array.isArray(position)) {
    // [lng, lat] — geo-pinned
    px = toPixel(map, position);
    isGeoPinned = true;
  } else if (position && typeof position === 'object') {
    // {x, y} — screen-fixed
    px = position;
  } else {
    console.warn('[effects.js] showLabel: no valid position provided');
    return null;
  }

  if (!px) return null;

  // --- Create element ---
  const el = document.createElement('div');
  el.id = id;
  el.classList.add('map-label', 'effect-label');
  el.textContent = text;

  el.style.cssText = `
    position: absolute;
    left: ${px.x}px;
    top:  ${px.y}px;
    color: ${color};
    font-size: ${fontSize};
    translate: -50% -50%;
    transform-origin: ${anchor};
    --effect-duration: ${duration}s;
    --effect-delay: ${delay}s;
  `;

  // Store geo coords for reprojection
  if (isGeoPinned) {
    el.dataset.lng = position[0];
    el.dataset.lat = position[1];
  }

  overlayEl.appendChild(el);

  // --- Apply effect (after append so layout is available) ---
  setTimeout(() => {
    if (effect === 'label-typewriter') {
      el.classList.add('label-typewriter');
      typewriterReveal(el, text, charInterval, delay * 1000);
    } else if (isCounter) {
      el.classList.add('label-fade'); // fade in first
      void el.offsetWidth;
      setTimeout(() => {
        animateCounter(el, counterFrom, counterTo, duration * 1000, counterSuffix);
      }, delay * 1000);
    } else {
      void el.offsetWidth;
      el.classList.add(effect);
    }
  }, 0);

  return el;
}


/* ============================================================
   runTimeline(map, overlayEl, scene)
   Master sequencer. Fires actions at their scheduled times.

   scene shape:
   {
     duration: number,           // total scene duration in seconds
     map_style: string,          // Mapbox style URL (applied by map.html)
     camera: { ... },            // applied by map.html before timeline runs
     timeline: [
       {
         at:     number,         // seconds from scene start
         action: string,         // 'applyFill' | 'drawArrow' | 'showLabel'
                                 // | 'clearOverlay' | 'cameraShake'
                                 // | 'removeLayer' | 'removeLabel'
         params: { ... },        // passed directly to the action function
       }
     ]
   }

   Returns: Promise that resolves when scene.duration elapses.
   ============================================================ */

function runTimeline(map, overlayEl, scene) {
  const { duration = 10, timeline = [] } = scene;
  const timers = [];

  // Register all timeline events
  timeline.forEach(entry => {
    const ms = (entry.at ?? 0) * 1000;

    const timer = setTimeout(() => {
      try {
        executeTimelineAction(map, overlayEl, entry, { deterministic: false });
      } catch (err) {
        console.error(`[effects.js] runTimeline error at t=${entry.at}s:`, err);
      }
    }, ms);

    timers.push(timer);
  });

  // Return promise that resolves when scene ends
  return new Promise(resolve => {
    setTimeout(() => {
      timers.forEach(clearTimeout); // safety cleanup
      resolve();
    }, duration * 1000);
  });
}


/* ============================================================
   REPROJECT LISTENER SETUP
   Call this once after the Mapbox map loads.
   Ensures all geo-pinned overlays stay accurate during pans/zooms.
   ============================================================ */

/**
 * Bind reproject to map movement events.
 * @param {object} map
 * @param {HTMLElement} overlayEl
 */
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

/* ============================================================
   DETERMINISTIC RUNTIME
   Evaluate scene as a pure function of time t (seconds).
   ============================================================ */

function _hashString(input) {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function _seededNoise(seed, x) {
  const s = Math.sin((x + 1) * 12.9898 + seed * 78.233) * 43758.5453;
  return s - Math.floor(s);
}

function createDeterministicRuntime(map, overlayEl, scene, options = {}) {
  const timeline = Array.isArray(scene.timeline) ? [...scene.timeline] : [];
  timeline.sort((a, b) => (a.at ?? 0) - (b.at ?? 0));

  const runtime = {
    map,
    overlayEl,
    scene,
    timeline,
    seed: Number(options.seed ?? 1),
    fired: new Set(),
    createdFillIds: new Set(),
    createdBorderIds: new Set(),
    createdArrowIds: new Set(),
    createdPulseRingIds: new Set(),
    createdLabelIds: new Set(),
    removedLabelIds: new Set(),
    currentTime: 0,
    cameraShakeActive: null,
    pendingRemovals: [],
    pendingFillExits: [],
    pendingBorderExits: [],
  };

  function _entryId(entry, idx) {
    const p = JSON.stringify(entry.params ?? {});
    return `${idx}:${entry.action}:${entry.at ?? 0}:${_hashString(p)}`;
  }

  function _ensureLabel(entry, idx) {
    const params = entry.params ?? {};
    const id = params.id || `det-label-${idx}`;
    if (runtime.removedLabelIds.has(id)) return null;
    const existing = document.getElementById(id);
    if (existing) return existing;
    const spec = Object.assign({}, params, {
      id,
      delay: params.delay ?? 0,
      duration: params.duration ?? 0.8,
    });
    const label = showLabel(map, overlayEl, spec);
    if (!label) return null;
    label.classList.add('visible');
    runtime.createdLabelIds.add(id);
    return label;
  }

  function _updateLabelDeterministic(entry, idx, t) {
    const params = entry.params ?? {};
    const start = Number(entry.at ?? 0);
    const localT = Math.max(0, t - start);
    const label = _ensureLabel(entry, idx);
    if (!label) return;

    if (params.effect === 'label-typewriter') {
      const text = String(params.text ?? '');
      const charIntervalMs = Number(params.charInterval ?? 70);
      const charsVisible = Math.max(
        0,
        Math.min(text.length, Math.floor((localT * 1000) / charIntervalMs))
      );
      label.textContent = text.slice(0, charsVisible);
    } else if (params.isCounter) {
      const from = Number(params.counterFrom ?? 0);
      const to = Number(params.counterTo ?? 100);
      const duration = Math.max(0.001, Number(params.duration ?? 1));
      const suffix = String(params.counterSuffix ?? '');
      const p = Math.max(0, Math.min(1, localT / duration));
      const eased = 1 - (1 - p) ** 3;
      label.textContent = `${Math.round(from + (to - from) * eased)}${suffix}`;
    } else {
      label.textContent = String(params.text ?? '');
    }
  }

  function _updateFillDeterministic(entry, t) {
    const params = entry.params ?? {};
    const id      = params.id;
    if (!id) return;
    const effect   = params.effect ?? 'fill-fade';
    const dur      = Math.max(0.001, Number(params.duration ?? 1));
    const del      = Number(params.delay ?? 0);
    const opacity  = Number(params.opacity ?? 0.6);
    const localT   = Math.max(0, t - Number(entry.at ?? 0) - del);
    const progress = Math.min(1, localT / dur);
    const layerId  = `${id}-layer`;

    if (effect === 'fill-fade') {
      if (map.getLayer(layerId))
        map.setPaintProperty(layerId, 'fill-opacity', opacity * (1 - (1 - progress) ** 3));
      return;
    }

    const wipeDir = effect === 'fill-wipe'     ? 'ltr'
                  : effect === 'fill-wipe-rtl' ? 'rtl'
                  : effect === 'fill-wipe-ttb' ? 'ttb'
                  : effect === 'fill-wipe-btt' ? 'btt'
                  : null;
    if (wipeDir !== null) {
      const svgEl = document.getElementById(`${id}-fill-svg`);
      if (svgEl) {
        _applyWipeProgress(svgEl, progress, wipeDir);
        if (progress >= 1) {
          svgEl.remove();
          if (map.getLayer(layerId)) map.setPaintProperty(layerId, 'fill-opacity', opacity);
        }
      } else if (progress >= 1 && map.getLayer(layerId)) {
        map.setPaintProperty(layerId, 'fill-opacity', opacity);
      }
      return;
    }

    if (effect === 'fill-ripple') {
      const svgEl = document.getElementById(`${id}-fill-svg`);
      if (svgEl) {
        svgEl.style.transform = `scale(${_elasticOut(progress)})`;
        if (progress >= 1) {
          svgEl.remove();
          if (map.getLayer(layerId)) map.setPaintProperty(layerId, 'fill-opacity', opacity);
        }
      } else if (progress >= 1 && map.getLayer(layerId)) {
        map.setPaintProperty(layerId, 'fill-opacity', opacity);
      }
      return;
    }

    if (effect === 'fill-contested' || effect === 'fill-contested-smooth') {
      const svgEl = document.getElementById(`${id}-fill-svg`);
      if (!svgEl) return;
      const path = svgEl.querySelector('path');
      if (!path) return;
      const period   = Math.max(0.05, dur);
      const localTime = Math.max(0, t - Number(entry.at ?? 0) - del);
      const phase    = (localTime / period) % 1;
      const colorA   = params.color ?? '#e74c3c';
      const colorB2  = params.colorB ?? '#3498db';
      path.setAttribute('fill', phase < 0.5 ? colorA : colorB2);
      path.setAttribute('fill-opacity', opacity);
    }
  }

  function _applyOneShot(entry, idx) {
    const params = Object.assign({}, entry.params ?? {});
    if (entry.action === 'applyFill' && !params.id) params.id = `det-fill-${idx}`;
    if (entry.action === 'drawArrow' && !params.id) params.id = `det-arrow-${idx}`;
    if (entry.action === 'applyBorder' && !params.id) params.id = `det-border-${idx}`;
    const normalized = Object.assign({}, entry, { params });
    executeTimelineAction(map, overlayEl, normalized, { deterministic: true, runtime });
    if (entry.action === 'showLabel') _ensureLabel(normalized, idx);
  }

  function _updateCameraShake(t) {
    const shake = runtime.cameraShakeActive;
    const container = map.getContainer();
    if (!shake || !container) return;
    const elapsed = t - shake.start;
    if (elapsed < 0 || elapsed > shake.duration) {
      container.style.transform = '';
      return;
    }
    const amplitudes = { light: 3, medium: 6, heavy: 12 };
    const amp = amplitudes[shake.intensity] ?? 6;
    const nx = _seededNoise(runtime.seed, elapsed * 23) - 0.5;
    const ny = _seededNoise(runtime.seed + 17, elapsed * 29) - 0.5;
    container.style.transform = `translate(${(nx * amp).toFixed(2)}px, ${(ny * amp).toFixed(2)}px)`;
  }

  function stepTo(tSec) {
    runtime.currentTime = Math.max(0, Number(tSec ?? 0));

    runtime.timeline.forEach((entry, idx) => {
      const at = Number(entry.at ?? 0);
      const entryId = _entryId(entry, idx);
      if (runtime.currentTime < at) return;
      if (!runtime.fired.has(entryId)) {
        _applyOneShot(entry, idx);
        runtime.fired.add(entryId);
      }
      if (entry.action === 'showLabel') {
        _updateLabelDeterministic(entry, idx, runtime.currentTime);
      }
      if (entry.action === 'applyFill') {
        _updateFillDeterministic(entry, runtime.currentTime);
      }
    });

    _updateCameraShake(runtime.currentTime);
    runtime.pendingRemovals = runtime.pendingRemovals.filter(item => {
      if (runtime.currentTime < item.removeAt) return true;
      const el = document.getElementById(item.id);
      if (el) el.remove();
      return false;
    });
    runtime.pendingFillExits = runtime.pendingFillExits.filter(item => {
      const elapsed = runtime.currentTime - item.startT;
      const p = Math.min(1, elapsed / item.exitDuration);
      if (map.getLayer(item.layerId))
        map.setPaintProperty(item.layerId, 'fill-opacity', item.startOpacity * (1 - p));
      if (p < 1) return true;
      if (map.getLayer(item.layerId))  map.removeLayer(item.layerId);
      if (map.getSource(item.sourceId)) map.removeSource(item.sourceId);
      const ov = document.getElementById(item.overlayId);
      if (ov) ov.remove();
      return false;
    });
    runtime.pendingBorderExits = runtime.pendingBorderExits.filter(item => {
      const p = Math.min(1, (runtime.currentTime - item.startT) / item.exitDuration);
      const el = document.getElementById(item.id);
      if (el) el.style.opacity = String(1 - p);
      if (p >= 1) { if (el) el.remove(); return false; }
      return true;
    });
    reproject(map, overlayEl);
  }

  function reset() {
    runtime.fired.clear();
    runtime.currentTime = 0;
    runtime.cameraShakeActive = null;
    clearOverlay(overlayEl);
    runtime.createdFillIds.forEach(id => {
      if (map.getLayer(`${id}-layer`)) map.removeLayer(`${id}-layer`);
      if (map.getSource(`${id}-source`)) map.removeSource(`${id}-source`);
      const overlayFill = document.getElementById(`${id}-overlay`);
      if (overlayFill) overlayFill.remove();
      const fillSvg = document.getElementById(`${id}-fill-svg`);
      if (fillSvg) fillSvg.remove();
    });
    runtime.createdBorderIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
    runtime.createdArrowIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
    runtime.createdPulseRingIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
    runtime.createdFillIds.clear();
    runtime.createdBorderIds.clear();
    runtime.createdArrowIds.clear();
    runtime.createdPulseRingIds.clear();
    runtime.createdLabelIds.clear();
    runtime.removedLabelIds.clear();
    runtime.pendingFillExits.length = 0;
    runtime.pendingBorderExits.length = 0;
    const container = map.getContainer();
    if (container) container.style.transform = '';
  }

  function getState() {
    return {
      t: runtime.currentTime,
      firedEvents: runtime.fired.size,
      labels: runtime.overlayEl.querySelectorAll('.effect-label').length,
      arrows: runtime.overlayEl.querySelectorAll('.effect-arrow').length,
      hash: _hashString(
        JSON.stringify({
          t: runtime.currentTime.toFixed(3),
          fired: runtime.fired.size,
          labels: runtime.overlayEl.querySelectorAll('.effect-label').length,
          arrows: runtime.overlayEl.querySelectorAll('.effect-arrow').length,
        })
      ),
    };
  }

  return {
    stepTo,
    reset,
    getState,
  };
}


/* ============================================================
   EXPORTS
   ============================================================ */

// Browser global (for map.html script tag usage)
window.MapEffects = {
  applyFill,
  applyBorder,
  removeBorder,
  removeArrow,
  pulseRing,
  drawArrow,
  showLabel,
  runTimeline,
  reproject,
  clearOverlay,
  bindReproject,
  createDeterministicRuntime,
  // Internal utils exposed for testing
  _curvedPath:       curvedPath,
  _straightPath:     straightPath,
  _toPixel:          toPixel,
  _typewriterReveal: typewriterReveal,
  _animateCounter:   animateCounter,
  _animateTravelDot: animateTravelDot,
};