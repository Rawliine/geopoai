'use strict';

/* ── Token / role helpers (W12) ─────────────────────────────── */
function _roleColor(role, variant) {
  const r = role || 'threat';
  const v = variant || 'core';
  return `var(--role-${r}-${v})`;
}

function _seeded(seed, x) {
  const s = Math.sin((x + 1) * 12.9898 + Number(seed) * 78.233) * 43758.5453;
  return s - Math.floor(s);
}

function _wobbleArc(arc, wobble, seed, fromPx, toPx) {
  if (!wobble) return arc;
  const amp = typeof wobble === 'number' ? wobble : 25;
  const midX = (fromPx.x + toPx.x) / 2;
  const midY = (fromPx.y + toPx.y) / 2;
  const n = _seeded(seed, midX * 0.01 + midY * 0.02) - 0.5;
  return arc + n * amp * 2;
}

function _samplePathPoints(pathEl, steps) {
  const len = pathEl.getTotalLength();
  const pts = [];
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const pt = pathEl.getPointAtLength(t * len);
    pts.push({ x: pt.x, y: pt.y, t });
  }
  return pts;
}

function _tangentNormal(pts, i) {
  const prev = pts[Math.max(0, i - 1)];
  const next = pts[Math.min(pts.length - 1, i + 1)];
  const dx = next.x - prev.x;
  const dy = next.y - prev.y;
  const mag = Math.hypot(dx, dy) || 1;
  return { nx: -dy / mag, ny: dx / mag };
}

function _taperPolygonD(pts, baseWidth, drawProgress) {
  if (!pts.length || drawProgress <= 0) return '';
  const endIdx = Math.max(1, Math.floor(drawProgress * (pts.length - 1)));
  const slice = pts.slice(0, endIdx + 1);
  const left = [];
  const right = [];
  slice.forEach((p, i) => {
    const w = Math.max(1, baseWidth * (1 - p.t) * 0.5);
    const { nx, ny } = _tangentNormal(slice, i);
    left.push({ x: p.x + nx * w, y: p.y + ny * w });
    right.push({ x: p.x - nx * w, y: p.y - ny * w });
  });
  const parts = [`M${left[0].x},${left[0].y}`];
  left.slice(1).forEach(pt => parts.push(`L${pt.x},${pt.y}`));
  for (let i = right.length - 1; i >= 0; i -= 1) {
    parts.push(`L${right[i].x},${right[i].y}`);
  }
  parts.push('Z');
  return parts.join(' ');
}

function _greatCircleCoords(from, to, npoints) {
  if (typeof turf === 'undefined') return [from, to];
  const gc = turf.greatCircle(turf.point(from), turf.point(to), { npoints: npoints || 64 });
  return gc.geometry.coordinates;
}

function _geoPathWithBow(map, coords, bowScale) {
  const pixels = coords.map(c => toPixel(map, c)).filter(Boolean);
  if (pixels.length < 2) return { d: '', pixels: [] };
  const dist = Math.hypot(
    pixels[pixels.length - 1].x - pixels[0].x,
    pixels[pixels.length - 1].y - pixels[0].y,
  );
  const bow = dist * (bowScale ?? 0.15);
  const bowed = pixels.map((p, i) => {
    if (i === 0 || i === pixels.length - 1) return p;
    const t = i / (pixels.length - 1);
    const chordX = pixels[0].x + (pixels[pixels.length - 1].x - pixels[0].x) * t;
    const chordY = pixels[0].y + (pixels[pixels.length - 1].y - pixels[0].y) * t;
    const dx = pixels[pixels.length - 1].x - pixels[0].x;
    const dy = pixels[pixels.length - 1].y - pixels[0].y;
    const mag = Math.hypot(dx, dy) || 1;
    const nx = -dy / mag;
    const ny = dx / mag;
    const bowFactor = Math.sin(Math.PI * t);
    return { x: chordX + nx * bow * bowFactor, y: chordY + ny * bow * bowFactor };
  });
  return { d: polylinePath(bowed), pixels: bowed };
}

function _easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2;
}

function _arrowDrawProgress(localT, duration, delay) {
  const d = Math.max(0.001, Number(duration) || 1.8);
  const del = Number(delay) || 0;
  const raw = Math.max(0, Math.min(1, (localT - del) / d));
  return _easeInOutCubic(raw);
}

function _applyStrokeDraw(pathEl, pathLen, progress) {
  const visible = Math.max(0, pathLen * progress);
  pathEl.style.strokeDasharray = `${visible} ${pathLen}`;
  pathEl.style.strokeDashoffset = '0';
}

function _setTravelDotProgress(pathEl, dotEl, progress) {
  const len = pathEl.getTotalLength();
  const pt = pathEl.getPointAtLength(Math.max(0, Math.min(1, progress)) * len);
  dotEl.setAttribute('cx', pt.x);
  dotEl.setAttribute('cy', pt.y);
  dotEl.style.opacity = progress < 0.05 ? String(progress / 0.05)
    : progress > 0.9 ? String((1 - progress) / 0.1) : '1';
}

function _rebuildTaperFill(svgEl, progress) {
  const center = svgEl.querySelector('path.arrow-path');
  const fill = svgEl.querySelector('path.taper-fill');
  if (!center || !fill) return;
  const baseWidth = parseFloat(svgEl.dataset.widthPx || '24');
  const pts = _samplePathPoints(center, 48);
  fill.setAttribute('d', _taperPolygonD(pts, baseWidth, progress));
}

function _reprojectArrowSvg(map, svgEl) {
  const w = svgEl.parentElement?.clientWidth || svgEl.clientWidth || 1920;
  const h = svgEl.parentElement?.clientHeight || svgEl.clientHeight || 1080;
  svgEl.setAttribute('width', w);
  svgEl.setAttribute('height', h);
  svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`);

  const style = svgEl.dataset.arrowStyle || 'stroke';
  const pathEl = svgEl.querySelector('path.arrow-path');
  if (!pathEl) return;

  if (style === 'supply') {
    let points;
    try { points = JSON.parse(svgEl.dataset.waypoints || '[]'); } catch (_) { return; }
    const projected = points.map(p => toPixel(map, p)).filter(Boolean);
    const d = polylinePath(projected);
    pathEl.setAttribute('d', d);
    pathEl.style.setProperty('--path-length', pathEl.getTotalLength());
    return;
  }

  if (style === 'arc') {
    const from = [parseFloat(svgEl.dataset.fromLng), parseFloat(svgEl.dataset.fromLat)];
    const to = [parseFloat(svgEl.dataset.toLng), parseFloat(svgEl.dataset.toLat)];
    const bow = parseFloat(svgEl.dataset.bowScale || '0.15');
    const coords = _greatCircleCoords(from, to, 64);
    const { d } = _geoPathWithBow(map, coords, bow);
    pathEl.setAttribute('d', d);
    pathEl.style.setProperty('--path-length', pathEl.getTotalLength());
    return;
  }

  const fromLng = parseFloat(svgEl.dataset.fromLng);
  const fromLat = parseFloat(svgEl.dataset.fromLat);
  const toLng = parseFloat(svgEl.dataset.toLng);
  const toLat = parseFloat(svgEl.dataset.toLat);
  const arc = parseFloat(svgEl.dataset.arc ?? 80);
  const curved = svgEl.dataset.curved !== 'false';
  const from = toPixel(map, [fromLng, fromLat]);
  const to = toPixel(map, [toLng, toLat]);
  if (!from || !to) return;
  const seed = parseFloat(svgEl.dataset.wobbleSeed || '1');
  const wobble = svgEl.dataset.wobble === 'true';
  const bowedArc = wobble ? _wobbleArc(arc, true, seed, from, to) : arc;
  const d = curved ? curvedPath(from, to, bowedArc) : straightPath(from, to);
  pathEl.setAttribute('d', d);
  const pathLen = pathEl.getTotalLength();
  pathEl.style.setProperty('--path-length', pathLen);
  if (style === 'taper') {
    const progress = parseFloat(svgEl.dataset.drawProgress || '1');
    _rebuildTaperFill(svgEl, progress);
  }
}

function _updateArrowDeterministic(svgEl, sceneT) {
  const start = parseFloat(svgEl.dataset.actionAt || '0');
  const duration = parseFloat(svgEl.dataset.duration || '1.8');
  const delay = parseFloat(svgEl.dataset.delay || '0');
  const localT = Math.max(0, sceneT - start);
  const progress = _arrowDrawProgress(localT, duration, delay);
  svgEl.dataset.drawProgress = String(progress);

  const style = svgEl.dataset.arrowStyle || 'stroke';
  const pathEl = svgEl.querySelector('path.arrow-path');
  if (!pathEl) return;
  const pathLen = parseFloat(pathEl.style.getPropertyValue('--path-length'))
    || pathEl.getTotalLength();

  if (style === 'taper') {
    _rebuildTaperFill(svgEl, progress);
    return;
  }

  if (style === 'supply') {
    const speed = parseFloat(svgEl.dataset.flowSpeed || '60');
    const dash = parseFloat(svgEl.dataset.dashPeriod || '24');
    const offset = (localT * speed) % dash;
    pathEl.style.strokeDashoffset = String(-offset);
    return;
  }

  _applyStrokeDraw(pathEl, pathLen, progress);
  const dot = svgEl.querySelector('.travel-dot');
  if (dot && svgEl.dataset.travelDot === 'true') {
    const travelStart = delay + Math.min(0.9, duration * 0.25);
    const travelDur = Math.max(0.001, duration - travelStart);
    const travelP = Math.max(0, Math.min(1, (localT - travelStart) / travelDur));
    _setTravelDotProgress(pathEl, dot, _easeInOutCubic(travelP));
  }
}

function _patchReprojectForW12() {
  if (MapEffects._w12ReprojectPatched) return;
  MapEffects._w12ReprojectPatched = true;
  const orig = MapEffects.reproject;
  MapEffects.reproject = function w12Reproject(map, overlayEl) {
    orig(map, overlayEl);
    overlayEl.querySelectorAll('svg.effect-arrow[data-arrow-style]').forEach(svgEl => {
      _reprojectArrowSvg(map, svgEl);
      if (MapEffects._currentT != null) {
        _updateArrowDeterministic(svgEl, MapEffects._currentT);
      }
    });
  };
}

function _patchDeterministicRuntime() {
  if (MapEffects._w12DetPatched) return;
  MapEffects._w12DetPatched = true;
  const orig = MapEffects.createDeterministicRuntime;
  MapEffects.createDeterministicRuntime = function w12DetRuntime(map, overlayEl, scene, options) {
    const rt = orig(map, overlayEl, scene, options);
    const origStep = rt.stepTo;
    rt.stepTo = function w12StepTo(tSec) {
      origStep(tSec);
      overlayEl.querySelectorAll('svg.effect-arrow[data-arrow-style]').forEach(svgEl => {
        _updateArrowDeterministic(svgEl, tSec);
      });
      if (typeof MapEffects._updateW12Labels === 'function') {
        MapEffects._updateW12Labels(map, overlayEl, scene, tSec);
      }
    };
    return rt;
  };
}

function _installW12Hooks() {
  _patchReprojectForW12();
  _patchDeterministicRuntime();
}

if (typeof window !== 'undefined') {
  window.addEventListener('load', _installW12Hooks);
}

function _triggerArrowExit(el, exitDuration = 0.6) {
  const pathEl = el.querySelector('path.arrow-path');
  const taperEl = el.querySelector('path.taper-fill');
  const dotEl = el.querySelector('.travel-dot');
  const exitRatio = parseFloat(getComputedStyle(document.documentElement)
    .getPropertyValue('--timing-exit-ratio')) || 0.6;
  const dur = exitDuration ?? exitRatio;
  el.style.setProperty('--exit-duration', `${dur}s`);
  if (taperEl) {
    taperEl.classList.remove('taper-draw');
    void taperEl.getBoundingClientRect();
    taperEl.classList.add('taper-exit');
  }
  if (pathEl) {
    pathEl.removeAttribute('marker-end');
    const pathLen = parseFloat(pathEl.style.getPropertyValue('--path-length'))
      || el.style.getPropertyValue('--path-length')
      || 1000;
    el.style.setProperty('--path-length', pathLen);
    pathEl.style.strokeDasharray = `${pathLen}`;
    pathEl.style.strokeDashoffset = '0';
    pathEl.classList.remove('arrow-draw', 'arrow-draw-headed', 'arrow-glow', 'arrow-entrance', 'arrow-exit');
    void pathEl.getBoundingClientRect();
    pathEl.classList.add('arrow-exit');
  }
  if (dotEl) {
    dotEl.classList.remove('travel-dot');
    dotEl.style.transition = `opacity ${dur}s ease-out`;
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

function drawArrow(map, overlayEl, arrowSpec) {
  const {
    id = `arrow-${Date.now()}`,
    from,
    to,
    color,
    width = 2.5,
    width_px: widthPx = 24,
    role = 'threat',
    style: arrowStyle,
    effect = 'arrow-draw',
    curved = true,
    arc = 80,
    headed = true,
    glowColor,
    duration = 1.8,
    delay = 0,
    wobble = false,
    travelDot = false,
    bowScale = 0.15,
    _actionAt = 0,
    _deterministic = false,
    _seed = 1,
  } = arrowSpec;

  const strokeColor = color || _roleColor(role, 'core');
  const haloColor = glowColor || _roleColor(role, 'glow');

  const fromPx = toPixel(map, from);
  const toPx = toPixel(map, to);
  if (!fromPx || !toPx) {
    console.warn('[arrows.js] drawArrow: could not project coordinates', from, to);
    return null;
  }

  const w = overlayEl.clientWidth;
  const h = overlayEl.clientHeight;
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.classList.add('effect-arrow');
  svg.id = id;
  svg.dataset.fromLng = from[0];
  svg.dataset.fromLat = from[1];
  svg.dataset.toLng = to[0];
  svg.dataset.toLat = to[1];
  svg.dataset.arc = arc;
  svg.dataset.curved = curved;
  svg.dataset.duration = duration;
  svg.dataset.delay = delay;
  svg.dataset.actionAt = _actionAt;
  svg.dataset.arrowStyle = arrowStyle || 'stroke';
  svg.dataset.widthPx = widthPx;
  svg.dataset.wobble = wobble ? 'true' : 'false';
  svg.dataset.wobbleSeed = _seed;
  svg.dataset.bowScale = bowScale;
  svg.dataset.travelDot = travelDot ? 'true' : 'false';

  svg.style.cssText = `
    position: absolute; top: 0; left: 0; pointer-events: none;
    overflow: visible;
    --path-length: 0;
    --effect-duration: ${duration}s;
    --effect-delay: ${delay}s;
    --glow-color: ${haloColor};
  `;

  let pathD;
  if (arrowStyle === 'arc') {
    const coords = _greatCircleCoords(from, to, 64);
    svg.dataset.bowScale = bowScale;
    const bowed = _geoPathWithBow(map, coords, bowScale);
    pathD = bowed.d;
  } else {
    const bowedArc = wobble ? _wobbleArc(arc, wobble, _seed, fromPx, toPx) : arc;
    pathD = curved ? curvedPath(fromPx, toPx, bowedArc) : straightPath(fromPx, toPx);
  }

  if (arrowStyle === 'taper') {
    const center = document.createElementNS(svgNS, 'path');
    center.classList.add('arrow-path', 'taper-centerline');
    center.setAttribute('d', pathD);
    center.setAttribute('fill', 'none');
    center.setAttribute('stroke', 'none');
    svg.appendChild(center);

    const fill = document.createElementNS(svgNS, 'path');
    fill.classList.add('taper-fill');
    fill.setAttribute('fill', strokeColor);
    fill.setAttribute('stroke', 'none');
    svg.appendChild(fill);

    const pathLen = center.getTotalLength();
    svg.style.setProperty('--path-length', pathLen);
    center.style.setProperty('--path-length', pathLen);

    overlayEl.appendChild(svg);
    if (_deterministic) {
      _rebuildTaperFill(svg, 0);
      _updateArrowDeterministic(svg, _actionAt);
    } else {
      const pts = _samplePathPoints(center, 48);
      let start = null;
      const run = ts => {
        if (!start) start = ts;
        const localT = (ts - start) / 1000;
        const p = _arrowDrawProgress(localT, duration, delay);
        fill.setAttribute('d', _taperPolygonD(pts, widthPx, p));
        if (p < 1) requestAnimationFrame(run);
      };
      requestAnimationFrame(run);
    }
    return svg;
  }

  if (headed && arrowStyle !== 'taper') {
    const defs = document.createElementNS(svgNS, 'defs');
    const markerId = `arrowhead-${id}`;
    defs.innerHTML = `
      <marker id="${markerId}" markerWidth="10" markerHeight="7"
              refX="9" refY="3.5" orient="auto" markerUnits="userSpaceOnUse">
        <polygon points="0 0, 10 3.5, 0 7" fill="${strokeColor}"/>
      </marker>`;
    svg.appendChild(defs);
  }

  const path = document.createElementNS(svgNS, 'path');
  path.classList.add('arrow-path');
  if (arrowStyle === 'arc') path.classList.add('arrow-arc');
  path.setAttribute('d', pathD);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', strokeColor);
  path.setAttribute('stroke-width', width);
  path.setAttribute('stroke-linecap', 'round');
  if (headed && effect !== 'arrow-draw' && arrowStyle !== 'taper') {
    path.setAttribute('marker-end', `url(#arrowhead-${id})`);
  }

  svg.appendChild(path);
  const pathLen = path.getTotalLength();
  svg.style.setProperty('--path-length', pathLen);

  const useTravel = travelDot || effect === 'arrow-travel';

  if (useTravel) {
    path.setAttribute('stroke', `${strokeColor}44`);
    path.setAttribute('stroke-width', width * 0.7);
    const dot = document.createElementNS(svgNS, 'circle');
    dot.classList.add('travel-dot');
    dot.setAttribute('cx', fromPx.x);
    dot.setAttribute('cy', fromPx.y);
    dot.style.setProperty('--glow-color', haloColor);
    dot.style.setProperty('--dot-radius', '5px');
    dot.style.opacity = '0';
    svg.appendChild(dot);

    const entranceDur = Math.min(0.9, duration * 0.25);
    svg.style.setProperty('--entrance-duration', `${entranceDur}s`);
    overlayEl.appendChild(svg);

    if (_deterministic) {
      _updateArrowDeterministic(svg, _actionAt);
    } else {
      void path.getBoundingClientRect();
      path.classList.add('arrow-entrance');
      setTimeout(() => {
        if (!path.parentNode) return;
        path.classList.remove('arrow-entrance');
        path.style.removeProperty('stroke-dasharray');
        path.style.removeProperty('stroke-dashoffset');
        dot.style.opacity = '';
        animateTravelDot(path, dot, duration * 1000, 0);
      }, (delay + entranceDur) * 1000 + 50);
    }
  } else if (effect === 'arrow-draw' || arrowStyle === 'arc') {
    overlayEl.appendChild(svg);
    if (_deterministic) {
      _updateArrowDeterministic(svg, _actionAt);
    } else {
      void path.getBoundingClientRect();
      path.classList.add('arrow-draw');
      if (headed) {
        setTimeout(() => {
          if (path.parentNode) path.setAttribute('marker-end', `url(#arrowhead-${id})`);
        }, (delay + duration) * 1000 + 50);
      }
    }
  } else {
    const entranceDur = Math.min(0.9, duration * 0.35);
    svg.style.setProperty('--entrance-duration', `${entranceDur}s`);
    overlayEl.appendChild(svg);
    if (_deterministic) {
      _updateArrowDeterministic(svg, _actionAt);
    } else {
      void path.getBoundingClientRect();
      path.classList.add('arrow-entrance');
      setTimeout(() => {
        if (!path.parentNode) return;
        path.classList.remove('arrow-entrance');
        path.style.removeProperty('stroke-dasharray');
        path.style.removeProperty('stroke-dashoffset');
        void path.getBoundingClientRect();
        path.classList.add('arrow-glow');
      }, (delay + entranceDur) * 1000 + 50);
    }
  }

  return svg;
}

function supplyLine(map, overlayEl, spec) {
  /* W12.T2 — dashed/dotted supply route with flowing dashes */
  const {
    id = `supply-${Date.now()}`,
    points = [],
    role = 'neutral',
    speed = 60,
    style: lineStyle = 'dashed',
    duration = 1.2,
    delay = 0,
    width = 2.5,
    _actionAt = 0,
    _deterministic = false,
  } = spec;

  if (!Array.isArray(points) || points.length < 2) {
    console.warn('[arrows.js] supplyLine: need at least 2 waypoints');
    return null;
  }

  const strokeColor = _roleColor(role, 'core');
  const projected = points.map(p => toPixel(map, p)).filter(Boolean);
  if (projected.length < 2) return null;

  const w = overlayEl.clientWidth;
  const h = overlayEl.clientHeight;
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.classList.add('effect-arrow', 'effect-supply-line');
  svg.id = id;
  svg.dataset.arrowStyle = 'supply';
  svg.dataset.waypoints = JSON.stringify(points);
  svg.dataset.flowSpeed = speed;
  svg.dataset.dashPeriod = lineStyle === 'dotted' ? '8' : '24';
  svg.dataset.actionAt = _actionAt;
  svg.dataset.duration = duration;
  svg.dataset.delay = delay;
  svg.style.cssText = `
    position: absolute; top: 0; left: 0; pointer-events: none; overflow: visible;
    --glow-color: ${_roleColor(role, 'glow')};
  `;

  const path = document.createElementNS(svgNS, 'path');
  path.classList.add('arrow-path', 'supply-path', `supply-${lineStyle}`);
  path.setAttribute('d', polylinePath(projected));
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', strokeColor);
  path.setAttribute('stroke-width', width);
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  const dash = lineStyle === 'dotted' ? '4 8' : '12 12';
  path.setAttribute('stroke-dasharray', dash);
  svg.appendChild(path);

  const pathLen = path.getTotalLength();
  path.style.setProperty('--path-length', pathLen);
  svg.style.setProperty('--path-length', pathLen);

  overlayEl.appendChild(svg);
  if (_deterministic) {
    _updateArrowDeterministic(svg, _actionAt);
  } else {
    path.classList.add('supply-flow');
    path.style.setProperty('--flow-speed', `${speed}px`);
  }
  return svg;
}

function removeSupplyLine(overlayEl, id, exitDuration = 0.6) {
  removeArrow(overlayEl, id, exitDuration);
}

const _drawArrowAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, {
    _actionAt: entry.at ?? 0,
    _deterministic: Boolean(ctx.deterministic),
    _seed: ctx.runtime?.seed ?? Number(entry.params?._seed ?? 1),
  });
  const arrow = drawArrow(map, overlayEl, params);
  if (ctx.runtime && arrow?.id) ctx.runtime.createdArrowIds.add(arrow.id);
};
_drawArrowAction.eventMeta = { type: 'arrow', intensity: 0.8 };
MapEffects.registerAction('drawArrow', _drawArrowAction);

const _supplyLineAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, {
    _actionAt: entry.at ?? 0,
    _deterministic: Boolean(ctx.deterministic),
  });
  const line = supplyLine(map, overlayEl, params);
  if (ctx.runtime && line?.id) ctx.runtime.createdArrowIds.add(line.id);
};
_supplyLineAction.eventMeta = { type: 'arrow', intensity: 0.5 };
MapEffects.registerAction('supplyLine', _supplyLineAction);

MapEffects.registerAction('removeArrow', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
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
});

MapEffects.registerAction('removeSupplyLine', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  const exitDur = params.exitDuration ?? 0.6;
  if (ctx.deterministic && ctx.runtime) {
    const el = document.getElementById(params.id);
    if (el && el.classList.contains('effect-supply-line')) {
      _triggerArrowExit(el, exitDur);
      ctx.runtime.pendingRemovals.push({ id: params.id, removeAt: (entry.at ?? 0) + exitDur });
    }
  } else {
    removeSupplyLine(overlayEl, params.id, exitDur);
  }
});
