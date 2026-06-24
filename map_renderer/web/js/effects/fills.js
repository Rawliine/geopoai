'use strict';

/* ============================================================
   W11 — shared helpers (role colors, geojson, progress)
   ============================================================ */
function _roleColors(role) {
  const tokens = window.DESIGN_TOKENS || {};
  const roles = (tokens.palette && tokens.palette.roles) || {};
  const r = roles[role] || roles.neutral || { core: '#95a5a6', glow: '#bac4c5', dim: '#616b6c' };
  const glow = tokens.glow || {};
  const timing = tokens.timing || {};
  return {
    core: r.core,
    glow: r.glow,
    dim: r.dim,
    haloOpacity: glow.halo_opacity ?? 0.35,
    corePx: glow.core_px ?? 2,
    haloPx: glow.halo_px ?? 6,
    exitRatio: timing.exit_ratio ?? 0.6,
  };
}

function _geojsonToFillRings(geojson) {
  if (!geojson) return [];
  const source = geojson.type === 'Feature' ? geojson.geometry : geojson;
  if (!source) return [];
  if (source.type === 'Polygon') return source.coordinates;
  if (source.type === 'MultiPolygon') return source.coordinates.flat();
  return [];
}

function _toTurfFeature(geojson) {
  if (!geojson) return null;
  if (geojson.type === 'Feature') return geojson;
  if (geojson.type === 'FeatureCollection') {
    let best = geojson.features[0];
    let bestArea = 0;
    (geojson.features || []).forEach(f => {
      const a = turf.area(f);
      if (a > bestArea) { bestArea = a; best = f; }
    });
    return best || null;
  }
  return turf.feature(geojson);
}

function _geojsonFromMapSource(map, sourceKey) {
  if (!map || !sourceKey) return null;
  const src = map.getSource(`${sourceKey}-source`);
  if (!src) return null;
  const data = src._data || src.serialize?.();
  return data || null;
}

function _resolveGeojson(map, params) {
  if (params.geojson) return params.geojson;
  const key = params.geojsonSource || params.sourceId;
  if (key) return _geojsonFromMapSource(map, key);
  if (params.id) return _geojsonFromMapSource(map, `${params.id}-geo`);
  return null;
}

function _largestOuterRing(geojson) {
  const feat = _toTurfFeature(geojson);
  const rings = _geojsonToFillRings(feat);
  if (!rings.length) return [];
  let best = rings[0];
  let bestLen = best.length;
  rings.forEach(r => { if (r.length > bestLen) { best = r; bestLen = r.length; } });
  return best;
}

function _ringToPathD(map, ring) {
  const pts = ring.map(([lng, lat]) => toPixel(map, [lng, lat])).filter(Boolean);
  if (pts.length < 3) return '';
  return `M${pts[0].x},${pts[0].y} ${pts.slice(1).map(p => `L${p.x},${p.y}`).join(' ')} Z`;
}

function _ringsToPathD(map, rings) {
  return rings.map(r => _ringToPathD(map, r)).filter(Boolean).join(' ');
}

function _interpKeyframes(keyframes, localT, easingName) {
  const kf = Array.isArray(keyframes) ? [...keyframes] : [{ t: 0, v: 0 }];
  kf.sort((a, b) => a.t - b.t);
  if (localT <= kf[0].t) return kf[0].v;
  if (localT >= kf[kf.length - 1].t) return kf[kf.length - 1].v;
  let i = 0;
  while (i < kf.length - 1 && localT > kf[i + 1].t) i += 1;
  const a = kf[i];
  const b = kf[i + 1];
  const span = Math.max(1e-6, b.t - a.t);
  let p = (localT - a.t) / span;
  const ease = (window.MapEffects && MapEffects.getEasing)
    ? MapEffects.getEasing(easingName)
    : (t => t);
  p = ease(Math.max(0, Math.min(1, p)));
  return a.v + (b.v - a.v) * p;
}

function _exitDuration(spec, fallback) {
  const tokens = window.DESIGN_TOKENS || {};
  const ratio = (tokens.timing && tokens.timing.exit_ratio) ?? 0.6;
  if (spec.exitDuration != null) return Number(spec.exitDuration);
  if (spec.duration != null) return Number(spec.duration) * ratio;
  return fallback;
}

/* ============================================================
   W11 — territory runtime state + tick loop
   ============================================================ */
MapEffects._territoryState = MapEffects._territoryState || {
  fronts: Object.create(null),
  morphs: Object.create(null),
  masks: Object.create(null),
  tickRaf: null,
};

function _clearTerritoryState() {
  const st = MapEffects._territoryState;
  st.fronts = Object.create(null);
  st.morphs = Object.create(null);
  st.masks = Object.create(null);
  if (st.tickRaf) {
    cancelAnimationFrame(st.tickRaf);
    st.tickRaf = null;
  }
}

function _ensureTerritoryTickLoop() {
  const st = MapEffects._territoryState;
  if (st.tickRaf) return;
  function frame() {
    const t = Number(MapEffects._currentT || 0);
    const map = st._map;
    const overlayEl = st._overlayEl;
    if (map && overlayEl) _updateTerritoryEffects(map, overlayEl, t);
    const active = Object.keys(st.fronts).length
      || Object.keys(st.morphs).length
      || Object.keys(st.masks).length;
    if (active) st.tickRaf = requestAnimationFrame(frame);
    else st.tickRaf = null;
  }
  st.tickRaf = requestAnimationFrame(frame);
}

function _radiusForAreaFraction(countryFeat, center, targetV) {
  const total = turf.area(countryFeat);
  if (total <= 0 || targetV <= 0) return 0;
  if (targetV >= 1) return 5000;
  const bbox = turf.bbox(countryFeat);
  const diagKm = turf.distance([bbox[0], bbox[1]], [bbox[2], bbox[3]], { units: 'kilometers' }) * 1.5;
  let lo = 0;
  let hi = Math.max(10, diagKm);
  for (let i = 0; i < 22; i += 1) {
    const mid = (lo + hi) / 2;
    const circle = turf.circle(center, mid, { steps: 64, units: 'kilometers' });
    const clipped = turf.intersect(countryFeat, circle);
    const frac = clipped ? turf.area(clipped) / total : 0;
    if (frac < targetV) lo = mid;
    else hi = mid;
  }
  return hi;
}

function _edgeMaskPolygon(countryFeat, edge, targetV) {
  const bbox = turf.bbox(countryFeat);
  const pad = 20;
  const west = bbox[0] - pad;
  const east = bbox[2] + pad;
  const south = bbox[1] - pad;
  const north = bbox[3] + pad;
  const e = String(edge || 'east').toLowerCase();
  const v = Math.max(0, Math.min(1, targetV));
  let coords;
  if (e === 'west') {
    const x = west + (east - west) * v;
    coords = [[west, south], [x, south], [x, north], [west, north], [west, south]];
  } else if (e === 'north') {
    const y = south + (north - south) * v;
    coords = [[west, south], [east, south], [east, y], [west, y], [west, south]];
  } else if (e === 'south') {
    const y = north - (north - south) * v;
    coords = [[west, y], [east, y], [east, north], [west, north], [west, y]];
  } else {
    const x = east - (east - west) * v;
    coords = [[x, south], [east, south], [east, north], [x, north], [x, south]];
  }
  return turf.polygon([coords]);
}

function _clipCountryForFront(countryFeat, spec, targetV) {
  if (targetV <= 0) return null;
  let mask;
  if (spec.edge) {
    mask = _edgeMaskPolygon(countryFeat, spec.edge, targetV);
  } else if (spec.from && Array.isArray(spec.from)) {
    const km = _radiusForAreaFraction(countryFeat, spec.from, targetV);
    mask = turf.circle(spec.from, km, { steps: 64, units: 'kilometers' });
  } else {
    return null;
  }
  try {
    return turf.intersect(countryFeat, mask);
  } catch (_err) {
    return null;
  }
}

function _ensureFrontSvg(map, overlayEl, spec) {
  const svgNS = 'http://www.w3.org/2000/svg';
  let svg = document.getElementById(`${spec.id}-front-svg`);
  const w = overlayEl.clientWidth || 1920;
  const h = overlayEl.clientHeight || 1080;
  if (!svg) {
    svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('width', w);
    svg.setAttribute('height', h);
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svg.id = `${spec.id}-front-svg`;
    svg.classList.add('effect-advance-front');
    svg.dataset.frontId = spec.id;
    svg.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;overflow:visible;';
    const fillPath = document.createElementNS(svgNS, 'path');
    fillPath.classList.add('advance-front-fill');
    fillPath.setAttribute('fill-rule', 'evenodd');
    const edgePath = document.createElementNS(svgNS, 'path');
    edgePath.classList.add('advance-front-edge');
    edgePath.setAttribute('fill', 'none');
    svg.appendChild(fillPath);
    svg.appendChild(edgePath);
    overlayEl.appendChild(svg);
  }
  return svg;
}

function _updateAdvanceFront(map, overlayEl, front, t) {
  if (front.exiting) {
    const elapsed = t - front.exitStart;
    const p = Math.min(1, elapsed / front.exitDuration);
    const svg = document.getElementById(`${front.id}-front-svg`);
    if (svg) svg.style.opacity = String(1 - p);
    if (p >= 1 && svg?.parentNode) svg.remove();
    if (p >= 1) delete MapEffects._territoryState.fronts[front.id];
    return;
  }
  const localT = Math.max(0, t - front.startAt);
  const v = _interpKeyframes(front.progress, localT, front.easing);
  const clipped = _clipCountryForFront(front.countryFeat, front, v);
  const svg = _ensureFrontSvg(map, overlayEl, front);
  const rc = _roleColors(front.role || 'threat');
  const fillPath = svg.querySelector('.advance-front-fill');
  const edgePath = svg.querySelector('.advance-front-edge');
  const softness = Number(front.front?.softness_px ?? 14);
  const glowOn = front.front?.glow !== false;
  if (!clipped) {
    if (fillPath) fillPath.setAttribute('d', '');
    if (edgePath) edgePath.setAttribute('d', '');
    return;
  }
  const geom = clipped.geometry || clipped;
  let rings = [];
  if (geom.type === 'Polygon') rings = geom.coordinates;
  else if (geom.type === 'MultiPolygon') rings = geom.coordinates.map(p => p[0]);
  const d = _ringsToPathD(map, rings);
  if (fillPath) {
    fillPath.setAttribute('d', d);
    fillPath.setAttribute('fill', rc.core);
    fillPath.setAttribute('fill-opacity', '0.55');
  }
  if (edgePath) {
    edgePath.setAttribute('d', d);
    edgePath.style.setProperty('--front-softness', `${softness}px`);
    edgePath.style.setProperty('--role-core', rc.core);
    edgePath.style.setProperty('--role-glow', rc.glow);
    edgePath.style.setProperty('--glow-core-px', `${rc.corePx}px`);
    edgePath.style.setProperty('--glow-halo-px', `${rc.haloPx}px`);
    edgePath.classList.toggle('advance-front-edge-glow', glowOn);
  }
}

function advanceFront(map, overlayEl, spec) {
  const {
    id,
    from,
    edge,
    progress = [{ t: 0, v: 0 }],
    role = 'threat',
    front = {},
    easing = 'easeInOut',
    startAt = 0,
  } = spec;
  const geojson = _resolveGeojson(map, spec);
  const countryFeat = _toTurfFeature(geojson);
  if (!countryFeat || !id) {
    console.warn('[fills.js] advanceFront: missing geojson or id');
    return null;
  }
  MapEffects._territoryState._map = map;
  MapEffects._territoryState._overlayEl = overlayEl;
  MapEffects._territoryState.fronts[id] = {
    id, from, edge, progress, role, front, easing, startAt,
    countryFeat,
  };
  _ensureFrontSvg(map, overlayEl, { id });
  _updateAdvanceFront(map, overlayEl, MapEffects._territoryState.fronts[id], startAt);
  _ensureTerritoryTickLoop();
  return id;
}

function updateFront(map, overlayEl, spec) {
  const front = MapEffects._territoryState.fronts[spec.id];
  if (!front) {
    console.warn('[fills.js] updateFront: unknown id', spec.id);
    return null;
  }
  if (Array.isArray(spec.progress)) {
    front.progress = front.progress.concat(spec.progress).sort((a, b) => a.t - b.t);
  }
  if (spec.easing) front.easing = spec.easing;
  if (spec.role) front.role = spec.role;
  if (spec.front) front.front = Object.assign({}, front.front, spec.front);
  _updateAdvanceFront(map, overlayEl, front, Number(MapEffects._currentT || front.startAt));
  _ensureTerritoryTickLoop();
  return spec.id;
}

function removeFront(map, overlayEl, spec, sceneT) {
  const front = MapEffects._territoryState.fronts[spec.id];
  if (!front) return;
  const exitDur = _exitDuration(spec, 0.6);
  front.exiting = true;
  front.exitStart = Number(sceneT ?? MapEffects._currentT ?? 0);
  front.exitDuration = exitDur;
  _ensureTerritoryTickLoop();
}

/* ============================================================
   W11 — morphTerritory (flubber)
   Multipolygon: largest outer ring heuristic only (see W11.md).
   ============================================================ */
function _ensureMorphSvg(map, overlayEl, spec) {
  const svgNS = 'http://www.w3.org/2000/svg';
  let svg = document.getElementById(`${spec.id}-morph-svg`);
  const w = overlayEl.clientWidth || 1920;
  const h = overlayEl.clientHeight || 1080;
  if (!svg) {
    svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('width', w);
    svg.setAttribute('height', h);
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svg.id = `${spec.id}-morph-svg`;
    svg.classList.add('effect-morph-territory');
    svg.dataset.morphId = spec.id;
    svg.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;overflow:visible;';
    const path = document.createElementNS(svgNS, 'path');
    path.classList.add('morph-territory-path');
    path.setAttribute('fill-rule', 'evenodd');
    svg.appendChild(path);
    overlayEl.appendChild(svg);
  }
  return svg;
}

function morphTerritory(map, overlayEl, spec) {
  const {
    id,
    duration = 2,
    role = 'contested',
    easing = 'easeInOut',
    startAt = 0,
  } = spec;
  let geoFrom = spec.geojson_from || spec.geojsonFrom;
  let geoTo = spec.geojson_to || spec.geojsonTo;
  if (!geoFrom) geoFrom = _geojsonFromMapSource(map, spec.fromSource || `${id}-from`);
  if (!geoTo) geoTo = _geojsonFromMapSource(map, spec.toSource || `${id}-to`);
  const ringFrom = _largestOuterRing(geoFrom);
  const ringTo = _largestOuterRing(geoTo);
  if (!id || !ringFrom.length || !ringTo.length || typeof flubber === 'undefined') {
    console.warn('[fills.js] morphTerritory: missing rings, id, or flubber');
    return null;
  }
  const interp = flubber.interpolate(
    ringFrom.map(c => [c[0], c[1]]),
    ringTo.map(c => [c[0], c[1]]),
    { maxSegmentLength: 0.25 }
  );
  MapEffects._territoryState._map = map;
  MapEffects._territoryState._overlayEl = overlayEl;
  MapEffects._territoryState.morphs[id] = {
    id, interp, role, duration, easing, startAt, exiting: false,
  };
  _ensureMorphSvg(map, overlayEl, { id });
  _ensureTerritoryTickLoop();
  return id;
}

function _updateMorphTerritory(map, overlayEl, morph, t) {
  if (morph.exiting) {
    const elapsed = t - morph.exitStart;
    const p = Math.min(1, elapsed / morph.exitDuration);
    const svg = document.getElementById(`${morph.id}-morph-svg`);
    if (svg) svg.style.opacity = String(1 - p);
    if (p >= 1 && svg?.parentNode) svg.remove();
    if (p >= 1) delete MapEffects._territoryState.morphs[morph.id];
    return;
  }
  const localT = Math.max(0, t - morph.startAt);
  const span = Math.max(0.001, morph.duration);
  let p = Math.min(1, localT / span);
  const ease = (window.MapEffects && MapEffects.getEasing)
    ? MapEffects.getEasing(morph.easing)
    : (x => x);
  p = ease(p);
  const ring = morph.interp(p);
  const d = _ringToPathD(map, ring);
  const svg = _ensureMorphSvg(map, overlayEl, morph);
  const path = svg.querySelector('.morph-territory-path');
  const rc = _roleColors(morph.role || 'contested');
  if (path) {
    path.setAttribute('d', d);
    path.setAttribute('fill', rc.core);
    path.setAttribute('fill-opacity', '0.5');
  }
}

function removeMorphTerritory(map, overlayEl, spec, sceneT) {
  const morph = MapEffects._territoryState.morphs[spec.id];
  if (!morph) return;
  morph.exiting = true;
  morph.exitStart = Number(sceneT ?? MapEffects._currentT ?? 0);
  morph.exitDuration = _exitDuration(spec, 0.6);
  _ensureTerritoryTickLoop();
}

/* ============================================================
   W11 — maskImage (clipPath + optional Ken Burns pan)
   Image+clip reproject on every camera move via _reprojectTerritoryEffects.
   ============================================================ */
function _ensureMaskSvg(map, overlayEl, spec) {
  const svgNS = 'http://www.w3.org/2000/svg';
  const svgId = `${spec.id}-mask-svg`;
  let svg = document.getElementById(svgId);
  const w = overlayEl.clientWidth || 1920;
  const h = overlayEl.clientHeight || 1080;
  if (!svg) {
    svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('width', w);
    svg.setAttribute('height', h);
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svg.id = svgId;
    svg.classList.add('effect-mask-image');
    svg.dataset.maskId = spec.id;
    svg.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;overflow:visible;';
    const defs = document.createElementNS(svgNS, 'defs');
    const clip = document.createElementNS(svgNS, 'clipPath');
    clip.id = `${spec.id}-clip`;
    const clipPath = document.createElementNS(svgNS, 'path');
    clipPath.classList.add('mask-clip-path');
    clipPath.setAttribute('fill-rule', 'evenodd');
    clip.appendChild(clipPath);
    defs.appendChild(clip);
    svg.appendChild(defs);
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('clip-path', `url(#${spec.id}-clip)`);
    const img = document.createElementNS(svgNS, 'image');
    img.classList.add('mask-image-el');
    img.setAttribute('preserveAspectRatio', spec.fit === 'contain' ? 'xMidYMid meet' : 'xMidYMid slice');
    g.appendChild(img);
    svg.appendChild(g);
    overlayEl.appendChild(svg);
  }
  return svg;
}

function maskImage(map, overlayEl, spec) {
  const {
    id,
    image,
    fit = 'cover',
    opacity = 0.9,
    pan,
    startAt = 0,
  } = spec;
  const geojson = _resolveGeojson(map, spec);
  const rings = _geojsonToFillRings(geojson);
  if (!id || !image || !rings.length) {
    console.warn('[fills.js] maskImage: missing id, image, or country geojson');
    return null;
  }
  MapEffects._territoryState._map = map;
  MapEffects._territoryState._overlayEl = overlayEl;
  MapEffects._territoryState.masks[id] = {
    id, image, fit, opacity, pan: pan || null, rings, startAt, exiting: false,
  };
  const svg = _ensureMaskSvg(map, overlayEl, { id, fit });
  const img = svg.querySelector('.mask-image-el');
  if (img) {
    img.setAttributeNS('http://www.w3.org/1999/xlink', 'href', image);
    img.setAttribute('href', image);
    img.setAttribute('opacity', String(opacity));
  }
  _updateMaskImage(map, overlayEl, MapEffects._territoryState.masks[id], startAt);
  _ensureTerritoryTickLoop();
  return id;
}

function _maskImageBounds(map, rings) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  rings.forEach(ring => {
    ring.forEach(([lng, lat]) => {
      const pt = toPixel(map, [lng, lat]);
      if (!pt) return;
      minX = Math.min(minX, pt.x);
      minY = Math.min(minY, pt.y);
      maxX = Math.max(maxX, pt.x);
      maxY = Math.max(maxY, pt.y);
    });
  });
  if (!isFinite(minX)) return null;
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

function _updateMaskImage(map, overlayEl, mask, t) {
  if (mask.exiting) {
    const elapsed = t - mask.exitStart;
    const p = Math.min(1, elapsed / mask.exitDuration);
    const svg = document.getElementById(`${mask.id}-mask-svg`);
    if (svg) svg.style.opacity = String(1 - p);
    if (p >= 1 && svg?.parentNode) svg.remove();
    if (p >= 1) delete MapEffects._territoryState.masks[mask.id];
    return;
  }
  const svg = _ensureMaskSvg(map, overlayEl, mask);
  const clipPath = svg.querySelector('.mask-clip-path');
  const img = svg.querySelector('.mask-image-el');
  const d = _ringsToPathD(map, mask.rings);
  if (clipPath) clipPath.setAttribute('d', d);
  const bounds = _maskImageBounds(map, mask.rings);
  if (!bounds || !img) return;
  let ox = 0; let oy = 0;
  if (mask.pan) {
    const span = Math.max(0.001, Number(mask.pan.duration ?? 8));
    const localT = Math.max(0, t - mask.startAt);
    const p = (localT % span) / span;
    const dx = Number(mask.pan.dx ?? 0.08) * bounds.w;
    const dy = Number(mask.pan.dy ?? 0.05) * bounds.h;
    ox = dx * Math.sin(p * Math.PI * 2);
    oy = dy * Math.cos(p * Math.PI * 2);
  }
  img.setAttribute('x', String(bounds.x + ox));
  img.setAttribute('y', String(bounds.y + oy));
  img.setAttribute('width', String(bounds.w));
  img.setAttribute('height', String(bounds.h));
}

function removeMaskImage(map, overlayEl, spec, sceneT) {
  const mask = MapEffects._territoryState.masks[spec.id];
  if (!mask) return;
  mask.exiting = true;
  mask.exitStart = Number(sceneT ?? MapEffects._currentT ?? 0);
  mask.exitDuration = _exitDuration(spec, 0.6);
  _ensureTerritoryTickLoop();
}

function _updateTerritoryEffects(map, overlayEl, t) {
  const st = MapEffects._territoryState;
  Object.keys(st.fronts).forEach(id => _updateAdvanceFront(map, overlayEl, st.fronts[id], t));
  Object.keys(st.morphs).forEach(id => _updateMorphTerritory(map, overlayEl, st.morphs[id], t));
  Object.keys(st.masks).forEach(id => _updateMaskImage(map, overlayEl, st.masks[id], t));
}

function _reprojectTerritoryEffects(map, overlayEl) {
  const t = Number(MapEffects._currentT || 0);
  _updateTerritoryEffects(map, overlayEl, t);
  overlayEl.querySelectorAll('svg.effect-advance-front, svg.effect-morph-territory, svg.effect-mask-image').forEach(svg => {
    const w = overlayEl.clientWidth || 1920;
    const h = overlayEl.clientHeight || 1080;
    svg.setAttribute('width', w);
    svg.setAttribute('height', h);
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  });
}

function _installTerritoryHooks() {
  if (!window.MapEffects || MapEffects._w11Hooks) return false;
  MapEffects._w11Hooks = true;
  const origReproject = MapEffects.reproject;
  if (typeof origReproject === 'function') {
    MapEffects.reproject = function (map, overlayEl) {
      _reprojectTerritoryEffects(map, overlayEl);
      return origReproject(map, overlayEl);
    };
  }
  const origClear = MapEffects.clearOverlay;
  if (typeof origClear === 'function') {
    MapEffects.clearOverlay = function (overlayEl) {
      _clearTerritoryState();
      return origClear(overlayEl);
    };
  }
  const origCreate = MapEffects.createDeterministicRuntime;
  if (typeof origCreate === 'function') {
    MapEffects.createDeterministicRuntime = function (...args) {
      const rt = origCreate(...args);
      const origReset = rt.reset;
      rt.reset = function () {
        _clearTerritoryState();
        return origReset();
      };
      return rt;
    };
  }
  MapEffects.updateTerritoryEffects = _updateTerritoryEffects;
  return true;
}

setTimeout(_installTerritoryHooks, 0);

/* ============================================================
   Pattern fills (W11.T4): hatch | gradient-radial | gradient-linear
   ============================================================ */
function _ensurePatternDef(svg, patternId, patternType, color, opacity) {
  const svgNS = 'http://www.w3.org/2000/svg';
  let defs = svg.querySelector('defs');
  if (!defs) {
    defs = document.createElementNS(svgNS, 'defs');
    svg.insertBefore(defs, svg.firstChild);
  }
  const existing = defs.querySelector(`#${patternId}`);
  if (existing) existing.remove();
  if (patternType === 'hatch') {
    const pat = document.createElementNS(svgNS, 'pattern');
    pat.id = patternId;
    pat.setAttribute('patternUnits', 'userSpaceOnUse');
    pat.setAttribute('width', '8');
    pat.setAttribute('height', '8');
    pat.setAttribute('patternTransform', 'rotate(45)');
    const line = document.createElementNS(svgNS, 'line');
    line.setAttribute('x1', '0');
    line.setAttribute('y1', '0');
    line.setAttribute('x2', '0');
    line.setAttribute('y2', '8');
    line.setAttribute('stroke', color);
    line.setAttribute('stroke-width', '2');
    line.setAttribute('stroke-opacity', String(opacity ?? 0.7));
    pat.appendChild(line);
    defs.appendChild(pat);
    return `url(#${patternId})`;
  }
  if (patternType === 'gradient-radial' || patternType === 'gradient-linear') {
    const grad = document.createElementNS(svgNS, patternType === 'gradient-radial' ? 'radialGradient' : 'linearGradient');
    grad.id = patternId;
    if (patternType === 'gradient-linear') {
      grad.setAttribute('x1', '0%');
      grad.setAttribute('y1', '0%');
      grad.setAttribute('x2', '100%');
      grad.setAttribute('y2', '100%');
    }
    const stop0 = document.createElementNS(svgNS, 'stop');
    stop0.setAttribute('offset', '0%');
    stop0.setAttribute('stop-color', color);
    stop0.setAttribute('stop-opacity', String(opacity ?? 0.65));
    const stop1 = document.createElementNS(svgNS, 'stop');
    stop1.setAttribute('offset', '100%');
    stop1.setAttribute('stop-color', color);
    stop1.setAttribute('stop-opacity', '0');
    grad.appendChild(stop0);
    grad.appendChild(stop1);
    defs.appendChild(grad);
    return `url(#${patternId})`;
  }
  return color;
}

function _createFillSVG(map, overlayEl, geojson, id, color, opacity, pattern, role) {
  const lines = _geojsonToFillRings(geojson);
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
  let fillPaint = color;
  if (pattern) {
    const rc = _roleColors(role || 'contested');
    const patColor = color || rc.core;
    fillPaint = _ensurePatternDef(svg, `${id}-pat`, pattern, patColor, opacity);
  }
  path.setAttribute('fill', fillPaint);
  path.setAttribute('fill-opacity', pattern ? 1 : opacity);
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
    color,
    role,
    opacity    = 0.6,
    effect     = 'fill-fade',
    duration   = 1.2,
    delay      = 0,
    colorB,
    origin,
    pattern,
    deterministic = false,
  } = fillSpec;
  const rc = _roleColors(role || 'highlight');
  const fillColor = color || rc.core;
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
                   paint: { 'fill-color': fillColor, 'fill-opacity': 0 } });
  } else {
    map.setPaintProperty(layerId, 'fill-color', fillColor);
    map.setPaintProperty(layerId, 'fill-opacity', 0);
  }

  const useSvgPattern = pattern && ['hatch', 'gradient-radial', 'gradient-linear'].includes(pattern);

  const wipeDir = effect === 'fill-wipe'     ? 'ltr'
                : effect === 'fill-wipe-rtl' ? 'rtl'
                : effect === 'fill-wipe-ttb' ? 'ttb'
                : effect === 'fill-wipe-btt' ? 'btt'
                : null;

  if (wipeDir !== null || useSvgPattern) {
    const svgEl = overlayEl && _createFillSVG(map, overlayEl, geojson, id, fillColor, opacity, pattern, role);
    if (svgEl && wipeDir !== null) {
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
    } else if (svgEl && useSvgPattern && !deterministic) {
      map.setPaintProperty(layerId, 'fill-opacity', 0);
      const startMs = performance.now() + delay * 1000;
      (function step() {
        if (performance.now() < startMs) { requestAnimationFrame(step); return; }
        const p = Math.min(1, (performance.now() - startMs) / (duration * 1000));
        svgEl.style.opacity = String(opacity * (1 - (1 - p) ** 3));
        if (p < 1) requestAnimationFrame(step);
      })();
    } else if (!svgEl) {
      map.setPaintProperty(layerId, 'fill-opacity', opacity);
    }
    return { layerId, sourceId };
  }

  if (effect === 'fill-ripple') {
    const svgEl = overlayEl && _createFillSVG(map, overlayEl, geojson, id, fillColor, opacity, null, role);
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
    return { layerId, sourceId };
  }

  if (effect === 'fill-contested' || effect === 'fill-contested-smooth') {
    const svgEl = overlayEl && _createFillSVG(map, overlayEl, geojson, id, fillColor, opacity, pattern, role);
    if (svgEl) {
      const path = svgEl.querySelector('path');
      path.style.setProperty('--effect-color-a', fillColor);
      path.style.setProperty('--effect-color-b', colorB ?? rc.glow);
      path.style.setProperty('--effect-duration', `${duration}s`);
      path.style.setProperty('--effect-delay', `${delay}s`);
      path.style.setProperty('--fill-opacity', opacity);
      if (!deterministic) {
        void path.getBoundingClientRect();
        path.classList.add(effect);
      }
    } else {
      map.setPaintProperty(layerId, 'fill-opacity', opacity);
    }
    return { layerId, sourceId };
  }

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
    duration     = 4.0,
    ringDuration = 1.8,
    delay        = 0,
    stagger,
    deterministic = false,
    startT        = 0,
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

  if (dotRadius > 0) {
    const dot = document.createElementNS(svgNS, 'circle');
    dot.setAttribute('cx', pt.x);
    dot.setAttribute('cy', pt.y);
    dot.setAttribute('r', dotRadius);
    dot.setAttribute('fill', dotColor ?? color);
    dot.setAttribute('opacity', '0.9');
    svg.appendChild(dot);
  }

  const isLegacy = stagger !== undefined;
  const effectiveRingDuration = isLegacy ? duration : ringDuration;
  const spacing = isLegacy ? stagger : (count > 0 ? duration / count : duration);

  for (let i = 0; i < count; i++) {
    const ringDelay = isLegacy
      ? delay + i * stagger
      : delay + spacing * 0.5 + i * spacing;

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

  const totalMs = isLegacy
    ? (delay + duration + (count - 1) * stagger + 0.2) * 1000
    : (delay + duration + ringDuration + 0.2) * 1000;
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

const _advanceFrontAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, { startAt: Number(entry.at ?? 0) });
  const frontId = advanceFront(map, overlayEl, params);
  if (ctx.runtime && frontId) {
    if (!ctx.runtime.createdFrontIds) ctx.runtime.createdFrontIds = new Set();
    ctx.runtime.createdFrontIds.add(frontId);
  }
};
_advanceFrontAction.eventMeta = { type: 'fill', intensity: 0.9 };
MapEffects.registerAction('advanceFront', _advanceFrontAction);

const _updateFrontAction = function (map, overlayEl, entry, ctx) {
  updateFront(map, overlayEl, entry.params ?? {});
};
_updateFrontAction.eventMeta = { type: 'fill', intensity: 0.9 };
MapEffects.registerAction('updateFront', _updateFrontAction);

MapEffects.registerAction('removeFront', function (map, overlayEl, entry, ctx) {
  removeFront(map, overlayEl, entry.params ?? {}, Number(entry.at ?? 0));
});

const _morphTerritoryAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, { startAt: Number(entry.at ?? 0) });
  morphTerritory(map, overlayEl, params);
};
_morphTerritoryAction.eventMeta = { type: 'fill', intensity: 0.7 };
MapEffects.registerAction('morphTerritory', _morphTerritoryAction);

MapEffects.registerAction('removeMorphTerritory', function (map, overlayEl, entry, ctx) {
  removeMorphTerritory(map, overlayEl, entry.params ?? {}, Number(entry.at ?? 0));
});

const _maskImageAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, { startAt: Number(entry.at ?? 0) });
  const el = MapEffects.createOverlayEl('div', 'image', { id: `${params.id}-mask-tag` });
  el.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;';
  overlayEl.appendChild(el);
  maskImage(map, overlayEl, params);
};
_maskImageAction.eventMeta = { type: 'image', intensity: 0.6 };
MapEffects.registerAction('maskImage', _maskImageAction);

  MapEffects.registerAction('removeMaskImage', function (map, overlayEl, entry, ctx) {
  removeMaskImage(map, overlayEl, entry.params ?? {}, Number(entry.at ?? 0));
  const tag = document.getElementById(`${entry.params?.id}-mask-tag`);
  if (tag) tag.remove();
});
