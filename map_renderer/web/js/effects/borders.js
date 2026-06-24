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

function _roleColors(role) {
  const tokens = window.DESIGN_TOKENS || {};
  const roles = (tokens.palette && tokens.palette.roles) || {};
  const r = roles[role] || roles.neutral || { core: '#95a5a6', glow: '#bac4c5' };
  const glow = tokens.glow || {};
  return {
    core: r.core,
    glow: r.glow,
    haloOpacity: glow.halo_opacity ?? 0.35,
    corePx: glow.core_px ?? 2,
    haloPx: glow.halo_px ?? 6,
  };
}

function applyBorder(map, overlayEl, borderSpec) {
  const {
    id = `border-${Date.now()}`,
    geojson,
    color,
    role,
    width = 2.5,
    effect = 'border-neon',
    duration = 1.2,
    delay = 0,
    glowColor,
    dashPattern,
    deterministic = false,
    fadeIn = 0.4,
  } = borderSpec;

  const lines = _geojsonToBorderLines(geojson);
  if (!lines.length) {
    console.warn('[effects.js] applyBorder: unsupported or empty geojson');
    return null;
  }

  const rc = _roleColors(role || 'highlight');
  const strokeColor = color || rc.core;
  const haloColor = glowColor || rc.glow;
  const isNeon = effect === 'border-neon';

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
    --glow-color: ${haloColor};
    --role-core: ${strokeColor};
    --role-glow: ${haloColor};
    --glow-core-px: ${rc.corePx}px;
    --glow-halo-px: ${rc.haloPx}px;
    --halo-opacity: ${rc.haloOpacity};
    --enter-duration: ${Math.min(0.4, Math.max(0, fadeIn))}s;
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
    if (!isNeon) {
      path.setAttribute('stroke', strokeColor);
      path.setAttribute('stroke-width', width);
    }
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
    if (effect) {
      path.classList.add(effect);
      if (isNeon && fadeIn > 0 && !deterministic) {
        path.classList.add('border-neon-enter');
      }
    }
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
  const border = applyBorder(map, overlayEl, Object.assign({}, params, {
    deterministic: Boolean(ctx.deterministic),
  }));
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
