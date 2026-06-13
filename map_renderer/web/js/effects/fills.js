'use strict';

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
    deterministic = false,
    startT        = 0,   // absolute scene time of the pulseRing action (for det. mode)
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
    if (deterministic) {
      // Disable CSS animation; drive scale/opacity from stepTo via scene time
      circle.style.animation = 'none';
      circle.style.transform = 'scale(0)';
      circle.style.opacity   = '0';
      circle.dataset.ringStart    = String(startT + ringDelay);
      circle.dataset.ringDuration = String(effectiveRingDuration);
      circle.classList.add('det-pulse-ring');
    }
    svg.appendChild(circle);
  }

  overlayEl.appendChild(svg);

  // Legacy cleanup: last ring ends at delay + (count-1)*stagger + duration
  // Radar cleanup: total lifetime is duration, plus time for last ring to finish
  const totalMs = isLegacy
    ? (delay + duration + (count - 1) * stagger + 0.2) * 1000
    : (delay + duration + ringDuration + 0.2) * 1000;
  // In deterministic mode the SVG lives until reset() — no wall-clock timer
  if (!deterministic) {
    setTimeout(() => { if (svg.parentNode) svg.remove(); }, totalMs);
  }

  return svg;
}

MapEffects.registerAction('applyFill', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  applyFill(map, Object.assign({}, params, { deterministic: Boolean(ctx.deterministic) }), overlayEl);
  if (ctx.runtime && params.id) ctx.runtime.createdFillIds.add(params.id);
});

MapEffects.registerAction('pulseRing', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  const ringParams = Object.assign({}, params, {
    deterministic: Boolean(ctx.deterministic),
    startT: Number(entry.at ?? 0),
  });
  const ring = pulseRing(map, overlayEl, ringParams);
  if (ctx.runtime && ring?.id) ctx.runtime.createdPulseRingIds.add(ring.id);
});

MapEffects.registerAction('removeLayer', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  const { id } = params;
  const exitDur = params.exitDuration ?? 0.6;
  const layerId2 = `${id}-layer`;
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
      fillSvgId: `${id}-fill-svg`,
    });
  } else {
    if (map.getLayer(layerId2)) {
      const startOpacity = map.getPaintProperty(layerId2, 'fill-opacity') ?? 0.6;
      const startMs = performance.now();
      (function step() {
        const p = Math.min(1, (performance.now() - startMs) / (exitDur * 1000));
        map.setPaintProperty(layerId2, 'fill-opacity', startOpacity * (1 - p));
        if (p < 1) { requestAnimationFrame(step); }
        else {
          if (map.getLayer(layerId2)) map.removeLayer(layerId2);
          if (map.getSource(sourceId2)) map.removeSource(sourceId2);
        }
      })();
    } else if (map.getSource(sourceId2)) {
      map.removeSource(sourceId2);
    }
    const overlayFill = document.getElementById(`${id}-overlay`);
    if (overlayFill) overlayFill.remove();
    const fillSvg3 = document.getElementById(`${id}-fill-svg`);
    if (fillSvg3) {
      fillSvg3.style.transition = `opacity ${exitDur}s ease-out`;
      fillSvg3.style.opacity = '0';
      setTimeout(() => { if (fillSvg3.parentNode) fillSvg3.remove(); }, exitDur * 1000 + 50);
    }
  }
});
