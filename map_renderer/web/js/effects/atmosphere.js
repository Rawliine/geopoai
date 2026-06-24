'use strict';

/**
 * Atmosphere / terrain / extruded-bar / polish hooks (W13.T2 + T4).
 * Registers actions + style-load helpers without editing map.html's script tags.
 * All visual colors come from the generated token CSS vars (tokens.css), never
 * inlined; numeric atmosphere tuning (fog range, exaggeration, opacities) are
 * rendering parameters.
 */

/* Read a generated design-token CSS custom property (token-sourced color). */
function _cssVar(name, fallback) {
  try {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || (fallback || '');
  } catch (e) {
    return fallback || '';
  }
}

function _roleColor(role) {
  return _cssVar('--role-' + (role || 'highlight') + '-core', '#f1c40f');
}

/* ============================================================
   FOG / ATMOSPHERE  (scene.atmosphere = { fog, stars })
   Applied on style load; token-tinted horizon + space glow.
   ============================================================ */
function applyAtmosphere(map, scene) {
  var atm = (scene && scene.atmosphere) || {};
  if (!atm.fog) {
    try { map.setFog(null); } catch (e) {}
    return;
  }
  try {
    map.setFog({
      'range': [0.5, 10],
      'color': _cssVar('--palette-surface', '#1a1f2e'),
      'high-color': _cssVar('--role-neutral-glow', '#bac4c5'),
      'space-color': _cssVar('--palette-background', '#0e1116'),
      'horizon-blend': 0.1,
      'star-intensity': atm.stars ? 0.45 : 0.0,
    });
  } catch (e) {
    console.warn('[atmosphere] setFog failed:', e);
  }
}

/* ============================================================
   3D TERRAIN  (scene.terrain = { enabled, exaggeration })
   DEM source is cached across scenes (survives clearSceneState
   because its id has no "-source" suffix); terrain is toggled.
   ============================================================ */
var TERRAIN_DEM_SOURCE = 'mapbox-dem';

function applyTerrain(map, scene) {
  var terr = (scene && scene.terrain) || {};
  if (terr.enabled) {
    if (!map.getSource(TERRAIN_DEM_SOURCE)) {
      map.addSource(TERRAIN_DEM_SOURCE, {
        type: 'raster-dem',
        url: 'mapbox://mapbox.mapbox-terrain-dem-v1',
        tileSize: 512,
        maxzoom: 14,
      });
    }
    map.setTerrain({ source: TERRAIN_DEM_SOURCE, exaggeration: Number(terr.exaggeration ?? 1.4) });
  } else {
    try { map.setTerrain(null); } catch (e) {}
  }
}

/* ============================================================
   extrudeBars — per-country extruded columns comparing a metric.
   { id, data:[{country,value,geojson}], max_height_m, role, duration }
   geojson is resolved by runner.py (_resolve_extrude_bars).
   The columns grow in (and shrink out via removeExtrudeBars) by ramping
   a height multiplier from runtime t, so realtime + deterministic match.
   ============================================================ */
var _extrudeSpecs = Object.create(null);

function _easeOutCubic(p) { return 1 - Math.pow(1 - Math.max(0, Math.min(1, p)), 3); }

function _setExtrudeProgress(map, layerId, progress) {
  if (!map.getLayer(layerId)) return;
  // Scale every feature's data-driven height by a shared 0..1 progress.
  map.setPaintProperty(layerId, 'fill-extrusion-height',
    ['*', ['get', '_height'], progress]);
}

function extrudeBars(map, overlayEl, entry, ctx) {
  var params = entry.params ?? {};
  var id = params.id || 'extrude';
  var data = Array.isArray(params.data) ? params.data : [];
  var maxH = Number(params.max_height_m ?? 200000);
  var role = params.role || 'highlight';

  var values = data.map(function (d) { return Number(d.value) || 0; });
  var maxV = Math.max.apply(null, values.concat([0])) || 1;

  var features = data
    .filter(function (d) { return d && d.geojson; })
    .map(function (d) {
      var f = JSON.parse(JSON.stringify(d.geojson));
      f.properties = Object.assign({}, f.properties, {
        _height: ((Number(d.value) || 0) / maxV) * maxH,
      });
      return f;
    });

  var sourceId = id + '-source';
  var layerId = id + '-layer';
  if (map.getLayer(layerId)) { try { map.removeLayer(layerId); } catch (e) {} }
  if (map.getSource(sourceId)) { try { map.removeSource(sourceId); } catch (e) {} }

  map.addSource(sourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: features },
  });
  map.addLayer({
    id: layerId,
    type: 'fill-extrusion',
    source: sourceId,
    paint: {
      'fill-extrusion-color': _roleColor(role),
      'fill-extrusion-height': ['*', ['get', '_height'], 0],  // start flat; ramped by updateExtrudeBars
      'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.85,
    },
  });

  // Record the spec so updateExtrudeBars can ramp the height from t.
  _extrudeSpecs[id] = {
    layerId: layerId,
    sourceId: sourceId,
    at: Number(entry.at ?? 0),
    duration: Math.max(0.001, Number(params.duration ?? 1.0)),
    removeAt: null,
    exitDuration: 1.0,
  };

  if (ctx && ctx.runtime && ctx.runtime.createdFillIds) {
    ctx.runtime.createdFillIds.add(id);
  }
}
extrudeBars.eventMeta = { type: 'fill', intensity: 0.7 };
MapEffects.registerAction('extrudeBars', extrudeBars);

/* removeExtrudeBars — shrink the columns back down, then remove. */
function removeExtrudeBars(map, overlayEl, entry, ctx) {
  var params = entry.params ?? {};
  var id = params.id;
  var spec = id ? _extrudeSpecs[id] : null;
  if (!spec) return;
  spec.removeAt = Number(entry.at ?? 0);
  spec.exitDuration = Math.max(0.001, Number(params.exitDuration ?? params.duration ?? 1.0));
}
removeExtrudeBars.eventMeta = { type: 'remove', intensity: 0.3 };
MapEffects.registerAction('removeExtrudeBars', removeExtrudeBars);

/* Drive extrude grow-in / shrink-out from runtime t (deterministic). */
function updateExtrudeBars(map, t) {
  t = Math.max(0, Number(t) || 0);
  Object.keys(_extrudeSpecs).forEach(function (id) {
    var spec = _extrudeSpecs[id];
    if (!map.getLayer(spec.layerId)) { delete _extrudeSpecs[id]; return; }
    if (spec.removeAt != null && t >= spec.removeAt) {
      var pOut = (t - spec.removeAt) / spec.exitDuration;
      if (pOut >= 1) {
        try { map.removeLayer(spec.layerId); } catch (e) {}
        try { map.removeSource(spec.sourceId); } catch (e) {}
        delete _extrudeSpecs[id];
        return;
      }
      _setExtrudeProgress(map, spec.layerId, 1 - _easeOutCubic(pOut));
      return;
    }
    var pIn = (t - spec.at) / spec.duration;
    _setExtrudeProgress(map, spec.layerId, _easeOutCubic(pIn));
  });
}

function resetExtrudeBars() {
  _extrudeSpecs = Object.create(null);
}

MapEffects.updateExtrudeBars = updateExtrudeBars;
MapEffects.resetExtrudeBars = resetExtrudeBars;

/* ============================================================
   POLISH STACK  (scene.polish = { vignette, grain, haze })
   Configures the #polish-* sublayers; updatePolish(t) drives the
   8-step grain loop + slow haze pan from runtime t (deterministic).
   ============================================================ */
var GRAIN_STEPS = 8;
var GRAIN_STEPS_PER_S = 8;          // one full 8-step cycle per second
var GRAIN_POSITIONS = [             // small offsets so grain shimmers, not slides
  [0, 0], [13, 7], [7, 17], [19, 3], [3, 23], [23, 13], [11, 29], [29, 19],
];
var HAZE_PAN_PX_PER_S = 4;          // very slow drift

function applyPolish(scene) {
  var polish = (scene && scene.polish) || {};
  var vig = document.getElementById('polish-vignette');
  var grain = document.getElementById('polish-grain');
  var haze = document.getElementById('polish-haze');
  // Defaults: vignette + grain on (intensity from token opacity), haze off.
  var showV = polish.vignette !== false;
  var showG = polish.grain !== false;
  var showH = polish.haze === true;
  if (vig) vig.style.display = showV ? 'block' : 'none';
  if (grain) grain.style.display = showG ? 'block' : 'none';
  if (haze) haze.style.display = showH ? 'block' : 'none';
}

function updatePolish(t) {
  t = Math.max(0, Number(t) || 0);
  var grain = document.getElementById('polish-grain');
  if (grain && grain.style.display !== 'none') {
    // Positive modulo (JS % keeps the sign of the dividend).
    var step = ((Math.floor(t * GRAIN_STEPS_PER_S) % GRAIN_STEPS) + GRAIN_STEPS) % GRAIN_STEPS;
    var p = GRAIN_POSITIONS[step];
    grain.style.backgroundPosition = p[0] + 'px ' + p[1] + 'px';
  }
  var haze = document.getElementById('polish-haze');
  if (haze && haze.style.display !== 'none') {
    var x = ((t * HAZE_PAN_PX_PER_S) % 240) - 120;
    haze.style.transform = 'translate3d(' + x.toFixed(1) + 'px, 0, 0)';
  }
}

/* ============================================================
   BASE-MAP LABEL CONTROL (W13.T4)
   Default: hide every base-style symbol layer (text + icons) on
   style load. showPlaceLabels re-enables selected base layers.
   Own overlay labels (#labels-layer) are unaffected.
   ============================================================ */
var _hiddenBaseSymbolLayers = [];

function hideBaseLabels(map) {
  _hiddenBaseSymbolLayers = [];
  var style;
  try { style = map.getStyle(); } catch (e) { return; }
  if (!style || !style.layers) return;
  style.layers.forEach(function (layer) {
    if (layer.type !== 'symbol') return;
    try {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
      _hiddenBaseSymbolLayers.push(layer.id);
    } catch (e) {}
  });
}

var _PLACE_TYPE_PATTERNS = {
  country: [/country.*label/i, /admin.*label/i],
  state: [/state.*label/i],
  city: [/settlement/i, /place/i, /city/i, /town/i, /village/i],
  water: [/water.*label/i, /marine.*label/i, /natural.*label/i],
};

function _bboxPolygon(bbox) {
  var w = bbox[0], s = bbox[1], e = bbox[2], n = bbox[3];
  return { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
}

function showPlaceLabels(map, overlayEl, entry, ctx) {
  var params = entry.params ?? {};
  var show = params.show !== false;
  var types = Array.isArray(params.types) ? params.types : ['country'];
  var patterns = [];
  types.forEach(function (t) {
    (_PLACE_TYPE_PATTERNS[t] || []).forEach(function (re) { patterns.push(re); });
  });
  // Optional geographic restriction. Note: this replaces the layer's own
  // filter (documented limitation) — sufficient for scoping a reveal to a region.
  var within = Array.isArray(params.within) ? _bboxPolygon(params.within) : null;

  _hiddenBaseSymbolLayers.forEach(function (id) {
    if (!patterns.some(function (re) { return re.test(id); })) return;
    try {
      map.setLayoutProperty(id, 'visibility', show ? 'visible' : 'none');
      if (within && show) map.setFilter(id, ['within', within]);
    } catch (e) {}
  });
}
showPlaceLabels.eventMeta = { type: 'label', intensity: 0.4 };
MapEffects.registerAction('showPlaceLabels', showPlaceLabels);

MapEffects.applyAtmosphere = applyAtmosphere;
MapEffects.applyTerrain = applyTerrain;
MapEffects.applyPolish = applyPolish;
MapEffects.updatePolish = updatePolish;
MapEffects.hideBaseLabels = hideBaseLabels;
