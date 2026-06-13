'use strict';

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

MapEffects.registerAction('applyBorder', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  const border = applyBorder(map, overlayEl, params);
  if (ctx.runtime && border?.id) ctx.runtime.createdBorderIds.add(border.id);
});

MapEffects.registerAction('removeBorder', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  const exitDur = params.exitDuration ?? 0.6;
  if (ctx.deterministic && ctx.runtime) {
    const el = document.getElementById(params.id);
    if (el && el.classList.contains('effect-border')) {
      ctx.runtime.pendingBorderExits.push({
        id: params.id, startT: entry.at ?? 0, exitDuration: exitDur,
      });
    }
  } else {
    removeBorder(overlayEl, params.id, exitDur);
  }
});
