'use strict';

function clearOverlay(overlayEl) {
  overlayEl.querySelectorAll('.effect-arrow, .effect-label, .effect-pulse-ring, .effect-fill-svg').forEach(el => el.remove());
}
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

MapEffects.registerAction('showLabel', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  showLabel(map, overlayEl, params);
});

MapEffects.registerAction('clearOverlay', function (map, overlayEl, entry, ctx) {
  clearOverlay(overlayEl);
});

MapEffects.registerAction('removeLabel', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
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
});
