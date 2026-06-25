'use strict';

/* ── Token / layout helpers (W12) ─────────────────────────────── */
function _roleColor(role, variant) {
  const r = role || 'highlight';
  const v = variant || 'core';
  return `var(--role-${r}-${v})`;
}

function _fontScale(key) {
  const fmt = (window.sceneFormat === 'vertical') ? 'vertical' : 'horizontal';
  return `var(--font-size-${fmt}-${key})`;
}

function _assetUrl(relPath) {
  return `../../${relPath}`;
}

function _iconUrl(pack, name) {
  const base = String(name).replace(/\.svg$/i, '');
  return _assetUrl(`assets/icons/${pack}/icons/${base}.svg`);
}

function _flagUrl(code) {
  return _assetUrl(`assets/icons/circle-flags/${String(code).toLowerCase()}.svg`);
}

function _labelsLayer(overlayEl) {
  return overlayEl.querySelector('#labels-layer') || overlayEl;
}

function _easeOutCubic(t) {
  return 1 - (1 - t) ** 3;
}

function _exitRatio() {
  return parseFloat(getComputedStyle(document.documentElement)
    .getPropertyValue('--timing-exit-ratio')) || 0.6;
}

function _staggerMs() {
  return parseFloat(getComputedStyle(document.documentElement)
    .getPropertyValue('--timing-stagger-ms')) || 120;
}

function _formatCounterValue(value, format, prefix, suffix) {
  const n = Math.round(Number(value) || 0);
  const pre = prefix || '';
  const suf = suffix || '';
  if (format === 'comma') {
    return `${pre}${n.toLocaleString('en-US')}${suf}`;
  }
  if (format === 'short') {
    const abs = Math.abs(n);
    if (abs >= 1e9) return `${pre}${(n / 1e9).toFixed(1).replace(/\.0$/, '')}B${suf}`;
    if (abs >= 1e6) return `${pre}${(n / 1e6).toFixed(1).replace(/\.0$/, '')}M${suf}`;
    if (abs >= 1e3) return `${pre}${(n / 1e3).toFixed(1).replace(/\.0$/, '')}K${suf}`;
    return `${pre}${n}${suf}`;
  }
  return `${pre}${n}${suf}`;
}

function _counterAtProgress(counter, localT) {
  const from = Number(counter.from ?? 0);
  const to = Number(counter.to ?? 100);
  const dur = Math.max(0.001, Number(counter.duration ?? 1));
  const p = Math.max(0, Math.min(1, localT / dur));
  const eased = _easeOutCubic(p);
  const val = from + (to - from) * eased;
  return _formatCounterValue(val, counter.format, counter.prefix, counter.suffix);
}

function setCounterAtProgress(el, counter, localT) {
  /* W12.T4 — progress-driven counter (deterministic-safe) */
  el.textContent = _counterAtProgress(counter, localT);
}

function animateCounterProgress(el, counter, localT) {
  setCounterAtProgress(el, counter, localT);
}

function _leaderOffset(anchorPx) {
  return {
    x: anchorPx.x,
    y: anchorPx.y - 56,
  };
}

function _reprojectLeaderLabel(el, map) {
  const toLng = parseFloat(el.dataset.leaderLng);
  const toLat = parseFloat(el.dataset.leaderLat);
  if (!isFinite(toLng) || !isFinite(toLat)) return;
  const anchor = toPixel(map, [toLng, toLat]);
  if (!anchor) return;
  const boxPos = _leaderOffset(anchor);
  el.style.left = `${boxPos.x}px`;
  el.style.top = `${boxPos.y}px`;
  const line = el.querySelector('.label-leader-line');
  if (!line) return;
  line.innerHTML = '';
  const svgNS = 'http://www.w3.org/2000/svg';
  const w = overlayElWidth();
  const h = overlayElHeight();
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.style.cssText = 'position:absolute;top:0;left:0;overflow:visible;pointer-events:none;';
  const boxRect = el.getBoundingClientRect();
  const ov = document.getElementById('overlay');
  const ovRect = ov ? ov.getBoundingClientRect() : { left: 0, top: 0 };
  const x1 = boxRect.left - ovRect.left + boxRect.width / 2;
  const y1 = boxRect.bottom - ovRect.top;
  const ln = document.createElementNS(svgNS, 'line');
  ln.setAttribute('x1', x1);
  ln.setAttribute('y1', y1);
  ln.setAttribute('x2', anchor.x);
  ln.setAttribute('y2', anchor.y);
  ln.classList.add('leader-connector');
  svg.appendChild(ln);
  line.appendChild(svg);
}

function overlayElWidth() {
  const ov = document.getElementById('overlay');
  return ov ? ov.clientWidth : 1920;
}

function overlayElHeight() {
  const ov = document.getElementById('overlay');
  return ov ? ov.clientHeight : 1080;
}

function _reprojectGeoIcon(el, map) {
  const lng = parseFloat(el.dataset.lng);
  const lat = parseFloat(el.dataset.lat);
  const pt = toPixel(map, [lng, lat]);
  if (!pt) return;
  el.style.left = `${pt.x}px`;
  el.style.top = `${pt.y}px`;
}

function _updateW12Labels(map, overlayEl, scene, sceneT) {
  overlayEl.querySelectorAll('.effect-label[data-counter]').forEach(el => {
    const start = parseFloat(el.dataset.actionAt || '0');
    const counter = JSON.parse(el.dataset.counter || '{}');
    setCounterAtProgress(el, counter, Math.max(0, sceneT - start));
  });

  overlayEl.querySelectorAll('.stat-box-row [data-row-counter]').forEach(valEl => {
    const counter = JSON.parse(valEl.dataset.rowCounter || '{}');
    const start = parseFloat(valEl.dataset.counterStart || '0');
    setCounterAtProgress(valEl, counter, Math.max(0, sceneT - start));
  });

  overlayEl.querySelectorAll('.title-card[data-hold-s]').forEach(el => {
    const start = parseFloat(el.dataset.actionAt || '0');
    const hold = parseFloat(el.dataset.holdS || '2');
    const exitDur = hold * _exitRatio();
    const localT = sceneT - start;
    if (localT > hold + exitDur) {
      el.style.display = 'none';
    } else if (localT > hold) {
      const p = (localT - hold) / exitDur;
      el.style.opacity = String(1 - p);
    } else {
      el.style.display = '';
      el.style.opacity = '1';
    }
  });

  overlayEl.querySelectorAll('.effect-label[data-leader="true"]').forEach(el => {
    _reprojectLeaderLabel(el, map);
  });

  overlayEl.querySelectorAll('.effect-icon[data-lng]').forEach(el => {
    _reprojectGeoIcon(el, map);
  });
}

MapEffects._updateW12Labels = _updateW12Labels;

function clearOverlay(overlayEl) {
  overlayEl.querySelectorAll(
    '.effect-arrow, .effect-label, .effect-pulse-ring, .effect-fill-svg, .effect-icon, .title-card, .stat-box',
  ).forEach(el => el.remove());
}

function showLabel(map, overlayEl, labelSpec) {
  const {
    id = `label-${Date.now()}`,
    text = '',
    position,
    anchor = 'center',
    effect = 'label-fade',
    fontSize,
    color,
    role = 'highlight',
    duration = 0.8,
    delay = 0,
    charInterval = 70,
    isCounter = false,
    counter,
    counterFrom = 0,
    counterTo = 100,
    counterSuffix = '',
    leader,
    _actionAt = 0,
    _deterministic = false,
  } = labelSpec;

  const textColor = color || _roleColor(role, 'core');
  const size = fontSize || _fontScale('label');

  let px;
  let isGeoPinned = false;

  if (Array.isArray(position)) {
    px = toPixel(map, position);
    isGeoPinned = true;
  } else if (position && typeof position === 'object') {
    px = MapEffects.layoutHints
      ? MapEffects.layoutHints.resolvePosition(position)
      : position;
  } else {
    console.warn('[labels.js] showLabel: no valid position provided');
    return null;
  }

  if (!px) return null;

  const hasCounter = Boolean(counter) || isCounter;
  const counterSpec = counter || {
    from: counterFrom,
    to: counterTo,
    duration,
    format: 'raw',
    suffix: counterSuffix,
  };

  const el = MapEffects.createOverlayEl
    ? MapEffects.createOverlayEl('div', 'label', { id, className: 'map-label effect-label' })
    : document.createElement('div');
  if (!MapEffects.createOverlayEl) {
    el.id = id;
    el.classList.add('map-label', 'effect-label');
  }

  if (hasCounter) {
    el.classList.add('label-counter-digits');
    el.style.fontFamily = 'var(--font-mono)';
    el.dataset.counter = JSON.stringify(counterSpec);
    el.dataset.actionAt = _actionAt;
    if (_deterministic) {
      el.textContent = _counterAtProgress(counterSpec, 0);
    } else {
      el.textContent = _formatCounterValue(counterSpec.from, counterSpec.format,
        counterSpec.prefix, counterSpec.suffix);
    }
  } else {
    el.textContent = text;
  }

  const anchorPx = px;
  let boxPx = _leaderOffset(anchorPx);
  if (!leader || !leader.to) {
    boxPx = px;
  }

  el.style.cssText = `
    position: absolute;
    left: ${boxPx.x}px;
    top:  ${boxPx.y}px;
    color: ${textColor};
    font-size: ${size};
    translate: -50% -50%;
    transform-origin: ${anchor};
    --effect-duration: ${duration}s;
    --effect-delay: ${delay}s;
    border-left: 3px solid ${_roleColor(role, 'core')};
    background: var(--palette-surface);
    padding: 0.35em 0.65em;
    border-radius: 2px;
  `;

  if (isGeoPinned) {
    el.dataset.lng = position[0];
    el.dataset.lat = position[1];
  }

  if (leader && leader.to) {
    /* W12.T3 — leader-line connector to geo anchor */
    el.dataset.leader = 'true';
    el.dataset.leaderLng = leader.to[0];
    el.dataset.leaderLat = leader.to[1];
    const leaderWrap = document.createElement('div');
    leaderWrap.classList.add('label-leader-line');
    el.insertBefore(leaderWrap, el.firstChild);
    _reprojectLeaderLabel(el, map);
  }

  el.dataset.actionAt = _actionAt;
  _labelsLayer(overlayEl).appendChild(el);

  if (!_deterministic) {
    setTimeout(() => {
      if (effect === 'label-typewriter') {
        el.classList.add('label-typewriter');
        typewriterReveal(el, text, charInterval, delay * 1000);
      } else if (hasCounter && !counter) {
        el.classList.add('label-fade');
        void el.offsetWidth;
        setTimeout(() => {
          animateCounter(el, counterFrom, counterTo, duration * 1000, counterSuffix);
        }, delay * 1000);
      } else if (hasCounter && counter) {
        el.classList.add('label-fade');
      } else {
        void el.offsetWidth;
        el.classList.add(effect);
      }
    }, 0);
  } else if (!hasCounter) {
    el.classList.add('visible');
  }

  return el;
}

function titleCard(map, overlayEl, spec) {
  /* W12.T5 — full-frame kinetic title cards */
  const {
    id = `title-${Date.now()}`,
    text = '',
    sub,
    role = 'highlight',
    effect = 'slam',
    hold_s: holdS = 2.5,
    duration = 0.5,
    _actionAt = 0,
    _deterministic = false,
  } = spec;

  const el = MapEffects.createOverlayEl
    ? MapEffects.createOverlayEl('div', 'callout', { id, className: 'title-card effect-label' })
    : document.createElement('div');
  if (!MapEffects.createOverlayEl) {
    el.id = id;
    el.classList.add('title-card', 'effect-label');
  }

  el.dataset.actionAt = _actionAt;
  el.dataset.holdS = holdS;
  el.dataset.effect = effect;

  const inner = document.createElement('div');
  inner.classList.add('title-card-inner');

  if (effect === 'letterbox') {
    const topBar = document.createElement('div');
    topBar.classList.add('title-letterbox-bar', 'title-letterbox-top');
    const bottomBar = document.createElement('div');
    bottomBar.classList.add('title-letterbox-bar', 'title-letterbox-bottom');
    el.appendChild(topBar);
    el.appendChild(bottomBar);
    inner.classList.add('title-letterbox-text');
  }

  const h = document.createElement('div');
  h.classList.add('title-card-text');
  h.textContent = text;
  h.style.color = _roleColor(role, 'core');
  h.style.fontFamily = 'var(--font-display)';
  h.style.fontSize = _fontScale('title');
  inner.appendChild(h);

  if (sub) {
    const s = document.createElement('div');
    s.classList.add('title-card-sub');
    s.textContent = sub;
    s.style.color = 'var(--text-secondary)';
    s.style.fontFamily = 'var(--font-primary)';
    s.style.fontSize = _fontScale('body');
    inner.appendChild(s);
  }

  el.appendChild(inner);
  el.style.setProperty('--effect-duration', `${duration}s`);
  el.style.setProperty('--hold-s', `${holdS}s`);

  const layer = _labelsLayer(overlayEl);
  layer.appendChild(el);

  const effectClass = effect === 'cut' ? 'title-cut'
    : effect === 'letterbox' ? 'title-letterbox'
      : 'title-slam';
  if (!_deterministic) {
    void el.offsetWidth;
    el.classList.add(effectClass);
    const exitDelay = (holdS + duration) * 1000;
    const exitDur = holdS * _exitRatio();
    setTimeout(() => {
      el.classList.add('title-exit');
      el.style.setProperty('--exit-duration', `${exitDur}s`);
      setTimeout(() => { if (el.parentNode) el.remove(); }, exitDur * 1000 + 50);
    }, exitDelay);
  }

  return el;
}

function statBox(map, overlayEl, spec) {
  /* W12.T6 — stat panel with flag chips and icons */
  const {
    id = `statbox-${Date.now()}`,
    title = '',
    rows = [],
    position = { x: 0.04, y: 0.08, unit: 'frac' },
    role = 'neutral',
    style = 'broadcast',
    _actionAt = 0,
    _deterministic = false,
  } = spec;
  const variant = `stat-box--${String(style).toLowerCase()}`;

  const pos = MapEffects.layoutHints
    ? MapEffects.layoutHints.resolvePosition(position)
    : position;

  const el = MapEffects.createOverlayEl
    ? MapEffects.createOverlayEl('div', 'chart', { id, className: `stat-box ${variant} effect-label` })
    : document.createElement('div');
  if (!MapEffects.createOverlayEl) {
    el.id = id;
    el.classList.add('stat-box', variant, 'effect-label');
  } else {
    el.classList.add(variant);
  }

  el.style.left = `${pos.x}px`;
  el.style.top = `${pos.y}px`;
  el.dataset.actionAt = _actionAt;
  // Role color exposed as --box-accent so each style variant can use it for its
  // accent bar / underline / leader as it sees fit.
  el.style.setProperty('--box-accent', _roleColor(role, 'core'));

  const head = document.createElement('div');
  head.classList.add('stat-box-title');
  head.textContent = title;
  el.appendChild(head);

  const body = document.createElement('div');
  body.classList.add('stat-box-body');

  rows.forEach((row, i) => {
    const rowEl = document.createElement('div');
    rowEl.classList.add('stat-box-row');
    rowEl.style.setProperty('--row-delay', `${i * _staggerMs()}ms`);

    if (row.icon) {
      const ic = document.createElement('img');
      ic.classList.add('stat-box-icon');
      ic.src = _iconUrl(row.iconPack || 'lucide', row.icon);
      ic.alt = '';
      ic.style.filter = `drop-shadow(0 0 2px ${_roleColor(role, 'glow')})`;
      rowEl.appendChild(ic);
    }
    if (row.flag) {
      const fl = document.createElement('img');
      fl.classList.add('stat-box-flag');
      fl.src = _flagUrl(row.flag);
      fl.alt = '';
      rowEl.appendChild(fl);
    }

    const lbl = document.createElement('span');
    lbl.classList.add('stat-box-label');
    lbl.textContent = row.label || '';
    rowEl.appendChild(lbl);

    const val = document.createElement('span');
    val.classList.add('stat-box-value');
    if (row.counter) {
      val.dataset.rowCounter = JSON.stringify(row.counter);
      val.dataset.counterStart = _actionAt;
      val.style.fontFamily = 'var(--font-mono)';
      if (_deterministic) {
        val.textContent = _counterAtProgress(row.counter, 0);
      } else {
        val.textContent = _formatCounterValue(row.counter.from, row.counter.format,
          row.counter.prefix, row.counter.suffix);
      }
    } else {
      val.textContent = row.value != null ? String(row.value) : '';
    }
    rowEl.appendChild(val);

    if (!_deterministic) rowEl.classList.add('stat-row-enter');
    else rowEl.style.opacity = '1';  // deterministic: no CSS entrance — show at base
    body.appendChild(rowEl);
  });

  el.appendChild(body);
  if (!_deterministic) {
    el.classList.add('stat-box-enter');
  }
  _labelsLayer(overlayEl).appendChild(el);
  return el;
}

function showIcon(map, overlayEl, spec) {
  const {
    id = `icon-${Date.now()}`,
    position,
    icon,
    iconPack = 'lucide',
    role = 'highlight',
    size = 28,
    lift = false,
    _actionAt = 0,
    _deterministic = false,
  } = spec;

  if (!Array.isArray(position)) {
    console.warn('[labels.js] showIcon: position must be [lng, lat]');
    return null;
  }
  const pt = toPixel(map, position);
  if (!pt) return null;

  const el = MapEffects.createOverlayEl
    ? MapEffects.createOverlayEl('div', 'image', { id, className: 'effect-icon map-icon' })
    : document.createElement('div');
  if (!MapEffects.createOverlayEl) {
    el.id = id;
    el.classList.add('effect-icon', 'map-icon');
  }

  el.dataset.lng = position[0];
  el.dataset.lat = position[1];
  el.dataset.actionAt = _actionAt;
  el.style.left = `${pt.x}px`;
  el.style.top = `${pt.y}px`;
  el.style.width = `${size}px`;
  el.style.height = `${size}px`;
  if (lift) el.classList.add('map-icon-lift');

  const img = document.createElement('img');
  img.src = _iconUrl(iconPack, icon);
  img.alt = '';
  img.style.width = '100%';
  img.style.height = '100%';
  img.style.filter = `drop-shadow(0 0 var(--glow-core-px) ${_roleColor(role, 'glow')})`;
  el.appendChild(img);

  _labelsLayer(overlayEl).appendChild(el);
  if (!_deterministic) el.classList.add('map-icon-enter');  // det: show at base
  return el;
}

const _showLabelAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, {
    _actionAt: entry.at ?? 0,
    _deterministic: Boolean(ctx.deterministic),
  });
  const label = showLabel(map, overlayEl, params);
  if (ctx.runtime && label?.id) ctx.runtime.createdLabelIds.add(label.id);
};
_showLabelAction.eventMeta = { type: 'label', intensity: 0.4 };
MapEffects.registerAction('showLabel', _showLabelAction);

const _titleCardAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, {
    _actionAt: entry.at ?? 0,
    _deterministic: Boolean(ctx.deterministic),
  });
  titleCard(map, overlayEl, params);
};
_titleCardAction.eventMeta = { type: 'chapter', intensity: 1.0 };
MapEffects.registerAction('titleCard', _titleCardAction);

const _statBoxAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, {
    _actionAt: entry.at ?? 0,
    _deterministic: Boolean(ctx.deterministic),
  });
  statBox(map, overlayEl, params);
};
_statBoxAction.eventMeta = { type: 'callout', intensity: 0.6 };
MapEffects.registerAction('statBox', _statBoxAction);

const _showIconAction = function (map, overlayEl, entry, ctx) {
  const params = Object.assign({}, entry.params ?? {}, {
    _actionAt: entry.at ?? 0,
    _deterministic: Boolean(ctx.deterministic),
  });
  showIcon(map, overlayEl, params);
};
_showIconAction.eventMeta = { type: 'image', intensity: 0.4 };
MapEffects.registerAction('showIcon', _showIconAction);

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

MapEffects.registerAction('removeTitleCard', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  const el = document.getElementById(params.id);
  if (!el) return;
  const exitDur = (params.exitDuration ?? 0.6);
  el.classList.add('title-exit');
  el.style.setProperty('--exit-duration', `${exitDur}s`);
  if (ctx.deterministic && ctx.runtime) {
    ctx.runtime.pendingRemovals.push({ id: params.id, removeAt: (entry.at ?? 0) + exitDur });
  } else {
    setTimeout(() => el.remove(), exitDur * 1000 + 50);
  }
});
