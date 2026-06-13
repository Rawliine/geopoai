'use strict';

function _triggerArrowExit(el, exitDuration = 0.6) {
  const pathEl = el.querySelector('path.arrow-path');
  const dotEl  = el.querySelector('.travel-dot');
  if (pathEl) {
    pathEl.removeAttribute('marker-end');   // hide arrowhead immediately on exit
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
      <marker id="${markerId}" markerWidth="10" markerHeight="7"
              refX="9" refY="3.5" orient="auto" markerUnits="userSpaceOnUse">
        <polygon points="0 0, 10 3.5, 0 7" fill="${color}"/>
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
  // marker-end for arrow-draw is deferred until draw-on completes (see below)
  if (headed && effect !== 'arrow-draw') path.setAttribute('marker-end', `url(#arrowhead-${id})`);

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
    overlayEl.appendChild(svg);       // append first so reflow is real
    void path.getBoundingClientRect();
    path.classList.add('arrow-draw');
    // Defer arrowhead: SVG marker-end is always at the geometric endpoint,
    // not at the current dashoffset position, so it must appear only after
    // the draw-on animation finishes.
    if (headed) {
      setTimeout(() => {
        if (path.parentNode) path.setAttribute('marker-end', `url(#arrowhead-${id})`);
      }, (delay + duration) * 1000 + 50);
    }

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

MapEffects.registerAction('drawArrow', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  const arrow = drawArrow(map, overlayEl, params);
  if (ctx.runtime && arrow?.id) ctx.runtime.createdArrowIds.add(arrow.id);
});

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
