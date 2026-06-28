'use strict';

function restartAnimation(el, classes) {
  classes.forEach(c => el.classList.remove(c));
  void el.offsetWidth; // force reflow — critical trick
  classes.forEach(c => el.classList.add(c));
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
function _elasticOut(t) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI / 3)) + 1;
}

/* ============================================================
   Camera easing registry (W13.T1)
   Shared by BOTH render paths so flyTo/rotateAround look the
   same in realtime (Mapbox `easing` option) and deterministic
   (the evaluateCameraPlan interpolator in map.html).
   Every fn maps a normalized progress t∈[0,1] → eased ∈[0,1],
   with f(0)=0 and f(1)=1.
   ============================================================ */
MapEffects.easings = {
  // Constant velocity.
  linear: t => t,
  // Soft, symmetric ease (easeInOutSine) — calm pushes.
  gentle: t => 0.5 - 0.5 * Math.cos(Math.PI * t),
  // Fast depart, long decelerate (expo-out) — cinematic arrival.
  swoop: t => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  // Speed ramp: slow-fast-snap-slow (quintic in-out).
  ramp: t => (t < 0.5 ? 16 * t * t * t * t * t : 1 - Math.pow(-2 * t + 2, 5) / 2),
  // Legacy default (cubic in-out) — kept for back-compat with pre-W13 scenes.
  easeInOut: t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
};

MapEffects.getEasing = function getEasing(name) {
  return MapEffects.easings[name] || MapEffects.easings.easeInOut;
};

/* Shared camera-busy window (ms, performance.now() clock). Realtime camera
   actions push this forward so idle_drift suspends during a move (W13.T1). */
MapEffects._cameraBusyUntil = 0;

/* ============================================================
   layoutHints (W13.T3)
   Frame-format aware placement helpers. Owned by core/this lane;
   W12's label / statBox / titleCard modules consume it (if present)
   to place screen-fixed overlays inside the safe area and to resolve
   fraction-based positions. safe_areas come from the injected
   window.DESIGN_TOKENS (runner.py), with a graceful fallback so manual
   (non-runner) browser runs don't throw.
   ============================================================ */
MapEffects.layoutHints = {
  // Current frame format.
  format: function () {
    return window.sceneFormat || 'horizontal';
  },
  // Current frame size in px.
  frameSize: function () {
    return this.format() === 'vertical'
      ? { w: 1080, h: 1920 }
      : { w: 1920, h: 1080 };
  },
  // Usable rectangle (px): inside platform margins, above the caption band.
  safeRect: function () {
    var fmt = this.format();
    var size = this.frameSize();
    var sa = (window.DESIGN_TOKENS
      && window.DESIGN_TOKENS.safe_areas
      && window.DESIGN_TOKENS.safe_areas[fmt]) || null;
    var m = (sa && sa.platform_margins) || { top: 0.04, bottom: 0.04, left: 0.04, right: 0.04 };
    var band = (sa && sa.caption_band) || [0.84, 0.96];
    var leftFrac = Number(m.left) || 0;
    var rightFrac = Number(m.right) || 0;
    var topFrac = Number(m.top) || 0;
    // Usable bottom = whichever is higher: bottom margin or caption band top.
    var bottomFrac = Math.min(1 - (Number(m.bottom) || 0), band[0]);
    var rect = {
      x: Math.round(leftFrac * size.w),
      y: Math.round(topFrac * size.h),
      w: Math.round((1 - leftFrac - rightFrac) * size.w),
      h: Math.round(Math.max(0, bottomFrac - topFrac) * size.h),
    };
    // W26 — subtract any active reserved bands (media regions) from the usable
    // rect so safe-area-based placement also avoids the media box.
    var active = this.activeBands ? this.activeBands() : [];
    active.forEach(function (bd) {
      var depth = bd.rectPx.h * bd.ramp;
      if (depth <= 0) return;
      if (bd.edge === 'top') {
        var newTop = bd.rectPx.y + depth;
        var dTop = newTop - rect.y;
        if (dTop > 0) { rect.y += dTop; rect.h -= dTop; }
      } else if (bd.edge === 'bottom') {
        var bandTop = bd.rectPx.y + bd.rectPx.h - depth;
        if (bandTop < rect.y + rect.h) rect.h = Math.max(0, bandTop - rect.y);
      }
    });
    return rect;
  },
  // Resolve a scene position: {x,y,unit:'frac'} → px; {x,y} px and [lng,lat]
  // geo are passed through unchanged (geo is handled by reprojection).
  resolvePosition: function (pos) {
    if (Array.isArray(pos)) return pos;
    if (pos && typeof pos === 'object' && pos.unit === 'frac') {
      var size = this.frameSize();
      return { x: Math.round(Number(pos.x) * size.w), y: Math.round(Number(pos.y) * size.h) };
    }
    return pos;
  },
};

/* ============================================================
   Reserved bands (W26.T1)
   A reserved band is a time-windowed screen region (top half,
   lower third, …) that the renderer keeps its own screen-fixed
   overlays out of; the actual media is composited in post. Bands
   draw nothing — they only expose geometry (px) + a time-driven
   ramp (in/out), so safeRect() and the reproject enforcement pass
   (W26.T2) can avoid them and runner.py can emit them (W26.T3).
   The ramp is a pure function of MapEffects._currentT → deterministic.
   ============================================================ */
MapEffects.layoutHints._bands = MapEffects.layoutHints._bands || {};

// Eased 0→1 (matches the cubic in-out used elsewhere).
function _reservedEase(p) {
  p = Math.max(0, Math.min(1, p));
  return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
}

// Current ramp (0..1) of a band at scene time t: in-ramp, hold, out-ramp.
function _reservedBandRamp(b, t) {
  var start = b.start;
  var end = b.start + b.duration;
  var ramp = b.ramp;
  if (t <= start || t >= end + ramp) return 0;
  if (t < start + ramp) return _reservedEase((t - start) / ramp);
  if (t < end) return 1;
  return _reservedEase(1 - (t - end) / ramp);
}

MapEffects.layoutHints.reserveBand = function reserveBand(id, band) {
  this._bands[String(id)] = {
    id: String(id),
    edge: band.edge === 'bottom' ? 'bottom' : 'top',
    rectPx: band.rectPx,
    start: Number(band.start) || 0,
    duration: Math.max(0.01, Number(band.duration) || 3),
    ramp: Math.max(0.001, Number(band.ramp) || 0.4),
    region: band.region || 'custom',
  };
};

MapEffects.layoutHints.releaseBand = function releaseBand(id, atT) {
  var b = this._bands[String(id)];
  if (!b) return;
  var rel = Number(atT) || 0;
  if (rel < b.start + b.duration) b.duration = Math.max(0, rel - b.start);
};

MapEffects.layoutHints.clearBands = function clearBands() {
  this._bands = {};
};

// Bands with ramp > 0 at time t (default: the current scene clock).
MapEffects.layoutHints.activeBands = function activeBands(t) {
  if (t == null) t = Number(MapEffects._currentT || 0);
  var out = [];
  var bands = this._bands;
  Object.keys(bands).forEach(function (k) {
    var b = bands[k];
    var r = _reservedBandRamp(b, t);
    if (r > 0.001) out.push({ id: b.id, edge: b.edge, rectPx: b.rectPx, ramp: r });
  });
  return out;
};

// All reserved windows with resolved pixel rects + [start,end] — sidecar (W26.T3).
MapEffects.layoutHints.getReservedWindows = function getReservedWindows() {
  var out = [];
  var bands = this._bands;
  Object.keys(bands).forEach(function (k) {
    var b = bands[k];
    var rc = b.rectPx;
    out.push({
      id: b.id,
      region: b.region,
      edge: b.edge,
      rect: [Math.round(rc.x), Math.round(rc.y), Math.round(rc.w), Math.round(rc.h)],
      start: b.start,
      end: b.start + b.duration,
      ramp: b.ramp,
    });
  });
  out.sort(function (a, c) { return a.start - c.start; });
  return out;
};

/* ============================================================
   layout.json emission state + helpers (W13.T6)
   reproject.js snapshots overlay box occupancy at 2 Hz of the
   runtime clock (MapEffects._currentT); runner.py writes the
   sidecar. createOverlayEl tags elements with data-kind so W11/W12
   overlays land in the right layout `kind`; _kindFromEl is the
   class-name fallback for elements that didn't use the helper.
   ============================================================ */
MapEffects._currentT = MapEffects._currentT || 0;
MapEffects._layoutFrames = MapEffects._layoutFrames || [];
MapEffects._lastLayoutT = -Infinity;
MapEffects.LAYOUT_SAMPLE_HZ = 2;

MapEffects.resetLayout = function resetLayout() {
  MapEffects._layoutFrames = [];
  MapEffects._lastLayoutT = -Infinity;
  MapEffects._currentT = 0;
};
MapEffects.getLayoutFrames = function getLayoutFrames() {
  return MapEffects._layoutFrames.slice();
};

// Create an overlay element pre-tagged with its layout kind (W11/W12 opt-in).
MapEffects.createOverlayEl = function createOverlayEl(tag, kind, opts) {
  var el = document.createElement(tag || 'div');
  if (kind) el.setAttribute('data-kind', kind);
  if (opts && opts.id) el.id = opts.id;
  if (opts && opts.className) el.className = opts.className;
  return el;
};

var LAYOUT_KINDS = { callout: 1, label: 1, chart: 1, matrix: 1, caption: 1, image: 1, other: 1 };
MapEffects._kindFromEl = function _kindFromEl(el) {
  var k = el.getAttribute && el.getAttribute('data-kind');
  if (k && LAYOUT_KINDS[k]) return k;
  var cls = '';
  if (el.className) cls = (el.className.baseVal !== undefined) ? el.className.baseVal : el.className;
  cls = String(cls || '');
  if (/title-?card/i.test(cls) || /callout/i.test(cls)) return 'callout';
  if (/stat-?box|chart/i.test(cls)) return 'chart';
  if (/matrix/i.test(cls)) return 'matrix';
  if (/caption/i.test(cls)) return 'caption';
  if (/mask|image|flag/i.test(cls)) return 'image';
  if (/label/i.test(cls)) return 'label';
  return 'other';
};
