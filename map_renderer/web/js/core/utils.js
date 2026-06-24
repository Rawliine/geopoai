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
