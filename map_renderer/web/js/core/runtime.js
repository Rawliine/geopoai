'use strict';

function _hashString(input) {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function _seededNoise(seed, x) {
  const s = Math.sin((x + 1) * 12.9898 + seed * 78.233) * 43758.5453;
  return s - Math.floor(s);
}

/* ============================================================
   events.json emission (W13.T5)
   Generic emitter: every executed action contributes an event,
   reading fn.eventMeta (fallback type "label" intensity 0.4).
   Camera actions emit start/end pairs. runner.py reads
   window.getEmittedEvents() and writes the sidecar.
   ============================================================ */
const VALID_ROLES = new Set(['highlight', 'threat', 'ally', 'contested', 'neutral']);

MapEffects._eventLog = MapEffects._eventLog || [];
MapEffects.resetEvents = function resetEvents() { MapEffects._eventLog = []; };
MapEffects.recordEvent = function recordEvent(e) { MapEffects._eventLog.push(e); };
MapEffects.getEmittedEvents = function getEmittedEvents() { return MapEffects._eventLog.slice(); };

function _emitEventForEntry(entry, fn, ctx) {
  const meta = (fn && fn.eventMeta) || { type: 'label', intensity: 0.4 };
  const params = entry.params ?? {};
  const t = Number(entry.at ?? 0);
  const id = (params.id != null && String(params.id).length)
    ? String(params.id)
    : `${entry.action}-${t}`;
  let intensity = Number(meta.intensity);
  if (!isFinite(intensity)) intensity = 0.4;
  intensity = Math.max(0, Math.min(1, intensity));
  const role = VALID_ROLES.has(params.role) ? params.role : undefined;

  const startEvt = { t, type: meta.type, phase: 'start', intensity, id };
  if (role) startEvt.role = role;
  MapEffects.recordEvent(startEvt);

  if (meta.type === 'camera') {
    let dur = Number(params.duration);
    if (!isFinite(dur)) dur = (params.durationMs != null) ? Number(params.durationMs) / 1000 : 2;
    const endEvt = { t: t + dur, type: 'camera', phase: 'end', intensity, id };
    if (role) endEvt.role = role;
    if (ctx && ctx.deterministic && ctx.runtime) {
      ctx.runtime.pendingCameraEnds.push({ at: t + dur, evt: endEvt });
    } else {
      setTimeout(function () { MapEffects.recordEvent(endEvt); }, Math.max(0, dur * 1000));
    }
  }
}

/**
 * Dispatch a single timeline entry via the action registry (W00).
 * @param {object} map
 * @param {HTMLElement} overlayEl
 * @param {object} entry
 * @param {object} [ctx]
 */
function executeTimelineAction(map, overlayEl, entry, ctx) {
  const fn = MapEffects.getAction(entry.action);
  if (!fn) {
    console.warn(`[MapEffects] unknown action "${entry.action}"`);
    return;
  }
  _emitEventForEntry(entry, fn, ctx);
  fn(map, overlayEl, entry, ctx);
}

function runTimeline(map, overlayEl, scene) {
  const { duration = 10, timeline = [] } = scene;
  const timers = [];

  // Register all timeline events
  timeline.forEach(entry => {
    const ms = (entry.at ?? 0) * 1000;

    const timer = setTimeout(() => {
      try {
        executeTimelineAction(map, overlayEl, entry, { deterministic: false });
      } catch (err) {
        console.error(`[MapEffects] runTimeline error at t=${entry.at}s:`, err);
      }
    }, ms);

    timers.push(timer);
  });

  // Return promise that resolves when scene ends
  return new Promise(resolve => {
    setTimeout(() => {
      timers.forEach(clearTimeout); // safety cleanup
      resolve();
    }, duration * 1000);
  });
}
function createDeterministicRuntime(map, overlayEl, scene, options = {}) {
  const timeline = Array.isArray(scene.timeline) ? [...scene.timeline] : [];
  timeline.sort((a, b) => (a.at ?? 0) - (b.at ?? 0));

  const runtime = {
    map,
    overlayEl,
    scene,
    timeline,
    seed: Number(options.seed ?? 1),
    fired: new Set(),
    createdFillIds: new Set(),
    createdBorderIds: new Set(),
    createdArrowIds: new Set(),
    createdPulseRingIds: new Set(),
    createdLabelIds: new Set(),
    removedLabelIds: new Set(),
    currentTime: 0,
    cameraShakeActive: null,
    pendingRemovals: [],
    pendingFillExits: [],
    pendingBorderExits: [],
    pendingCameraEnds: [],
  };

  function _entryId(entry, idx) {
    const p = JSON.stringify(entry.params ?? {});
    return `${idx}:${entry.action}:${entry.at ?? 0}:${_hashString(p)}`;
  }

  function _ensureLabel(entry, idx) {
    const params = entry.params ?? {};
    const id = params.id || `det-label-${idx}`;
    if (runtime.removedLabelIds.has(id)) return null;
    const existing = document.getElementById(id);
    if (existing) return existing;
    const spec = Object.assign({}, params, {
      id,
      delay: params.delay ?? 0,
      duration: params.duration ?? 0.8,
    });
    const label = showLabel(map, overlayEl, spec);
    if (!label) return null;
    label.classList.add('visible');
    runtime.createdLabelIds.add(id);
    return label;
  }

  function _updateLabelDeterministic(entry, idx, t) {
    const params = entry.params ?? {};
    const start = Number(entry.at ?? 0);
    const localT = Math.max(0, t - start);
    const label = _ensureLabel(entry, idx);
    if (!label) return;

    if (params.effect === 'label-typewriter') {
      const text = String(params.text ?? '');
      const charIntervalMs = Number(params.charInterval ?? 70);
      const charsVisible = Math.max(
        0,
        Math.min(text.length, Math.floor((localT * 1000) / charIntervalMs))
      );
      label.textContent = text.slice(0, charsVisible);
    } else if (params.isCounter) {
      const from = Number(params.counterFrom ?? 0);
      const to = Number(params.counterTo ?? 100);
      const duration = Math.max(0.001, Number(params.duration ?? 1));
      const suffix = String(params.counterSuffix ?? '');
      const p = Math.max(0, Math.min(1, localT / duration));
      const eased = 1 - (1 - p) ** 3;
      label.textContent = `${Math.round(from + (to - from) * eased)}${suffix}`;
    } else {
      label.textContent = String(params.text ?? '');
    }
  }

  function _updateFillDeterministic(entry, t) {
    const params = entry.params ?? {};
    const id      = params.id;
    if (!id) return;
    const effect   = params.effect ?? 'fill-fade';
    const dur      = Math.max(0.001, Number(params.duration ?? 1));
    const del      = Number(params.delay ?? 0);
    const opacity  = Number(params.opacity ?? 0.6);
    const localT   = Math.max(0, t - Number(entry.at ?? 0) - del);
    const progress = Math.min(1, localT / dur);
    const layerId  = `${id}-layer`;

    if (effect === 'fill-fade') {
      if (map.getLayer(layerId))
        map.setPaintProperty(layerId, 'fill-opacity', opacity * (1 - (1 - progress) ** 3));
      return;
    }

    const wipeDir = effect === 'fill-wipe'     ? 'ltr'
                  : effect === 'fill-wipe-rtl' ? 'rtl'
                  : effect === 'fill-wipe-ttb' ? 'ttb'
                  : effect === 'fill-wipe-btt' ? 'btt'
                  : null;
    if (wipeDir !== null) {
      const svgEl = document.getElementById(`${id}-fill-svg`);
      if (svgEl) {
        _applyWipeProgress(svgEl, progress, wipeDir);
        if (progress >= 1) {
          svgEl.remove();
          if (map.getLayer(layerId)) map.setPaintProperty(layerId, 'fill-opacity', opacity);
        }
      } else if (progress >= 1 && map.getLayer(layerId)) {
        map.setPaintProperty(layerId, 'fill-opacity', opacity);
      }
      return;
    }

    if (effect === 'fill-ripple') {
      const svgEl = document.getElementById(`${id}-fill-svg`);
      if (svgEl) {
        svgEl.style.transform = `scale(${_elasticOut(progress)})`;
        if (progress >= 1) {
          svgEl.remove();
          if (map.getLayer(layerId)) map.setPaintProperty(layerId, 'fill-opacity', opacity);
        }
      } else if (progress >= 1 && map.getLayer(layerId)) {
        map.setPaintProperty(layerId, 'fill-opacity', opacity);
      }
      return;
    }

    if (effect === 'fill-contested' || effect === 'fill-contested-smooth') {
      const svgEl = document.getElementById(`${id}-fill-svg`);
      if (!svgEl) return;
      const path = svgEl.querySelector('path');
      if (!path) return;
      const period   = Math.max(0.05, dur);
      const localTime = Math.max(0, t - Number(entry.at ?? 0) - del);
      const phase    = (localTime / period) % 1;
      const colorA   = params.color ?? '#e74c3c';
      const colorB2  = params.colorB ?? '#3498db';
      path.setAttribute('fill', phase < 0.5 ? colorA : colorB2);
      path.setAttribute('fill-opacity', opacity);
    }
  }

  function _applyOneShot(entry, idx) {
    const params = Object.assign({}, entry.params ?? {});
    if (entry.action === 'applyFill' && !params.id) params.id = `det-fill-${idx}`;
    if (entry.action === 'drawArrow' && !params.id) params.id = `det-arrow-${idx}`;
    if (entry.action === 'applyBorder' && !params.id) params.id = `det-border-${idx}`;
    const normalized = Object.assign({}, entry, { params });
    executeTimelineAction(map, overlayEl, normalized, { deterministic: true, runtime });
    if (entry.action === 'showLabel') _ensureLabel(normalized, idx);
  }

  function _updateCameraShake(t) {
    const shake = runtime.cameraShakeActive;
    const container = map.getContainer();
    if (!shake || !container) return;
    const elapsed = t - shake.start;
    if (elapsed < 0 || elapsed > shake.duration) {
      container.style.transform = '';
      return;
    }
    const amplitudes = { light: 3, medium: 6, heavy: 12 };
    const amp = amplitudes[shake.intensity] ?? 6;
    const nx = _seededNoise(runtime.seed, elapsed * 23) - 0.5;
    const ny = _seededNoise(runtime.seed + 17, elapsed * 29) - 0.5;
    container.style.transform = `translate(${(nx * amp).toFixed(2)}px, ${(ny * amp).toFixed(2)}px)`;
  }

  function stepTo(tSec) {
    runtime.currentTime = Math.max(0, Number(tSec ?? 0));

    runtime.timeline.forEach((entry, idx) => {
      const at = Number(entry.at ?? 0);
      const entryId = _entryId(entry, idx);
      if (runtime.currentTime < at) return;
      if (!runtime.fired.has(entryId)) {
        _applyOneShot(entry, idx);
        runtime.fired.add(entryId);
      }
      if (entry.action === 'showLabel') {
        _updateLabelDeterministic(entry, idx, runtime.currentTime);
      }
      if (entry.action === 'applyFill') {
        _updateFillDeterministic(entry, runtime.currentTime);
      }
    });

    _updateCameraShake(runtime.currentTime);

    // Flush camera-action end events once their end time has passed (W13.T5).
    if (runtime.pendingCameraEnds.length) {
      runtime.pendingCameraEnds = runtime.pendingCameraEnds.filter(item => {
        if (runtime.currentTime < item.at) return true;
        MapEffects.recordEvent(item.evt);
        return false;
      });
    }

    runtime.pendingRemovals = runtime.pendingRemovals.filter(item => {
      if (runtime.currentTime < item.removeAt) return true;
      const el = document.getElementById(item.id);
      if (el) el.remove();
      return false;
    });
    runtime.pendingFillExits = runtime.pendingFillExits.filter(item => {
      const elapsed = runtime.currentTime - item.startT;
      const p = Math.min(1, elapsed / item.exitDuration);
      if (map.getLayer(item.layerId))
        map.setPaintProperty(item.layerId, 'fill-opacity', item.startOpacity * (1 - p));
      const fillSvg = item.fillSvgId ? document.getElementById(item.fillSvgId) : null;
      if (fillSvg) fillSvg.style.opacity = String(1 - p);
      if (p < 1) return true;
      if (map.getLayer(item.layerId))  map.removeLayer(item.layerId);
      if (map.getSource(item.sourceId)) map.removeSource(item.sourceId);
      const ov = document.getElementById(item.overlayId);
      if (ov) ov.remove();
      if (fillSvg) fillSvg.remove();
      return false;
    });
    runtime.pendingBorderExits = runtime.pendingBorderExits.filter(item => {
      const p = Math.min(1, (runtime.currentTime - item.startT) / item.exitDuration);
      const el = document.getElementById(item.id);
      if (el) el.style.opacity = String(1 - p);
      if (p >= 1) { if (el) el.remove(); return false; }
      return true;
    });

    // Drive pulse ring expansion from scene time (CSS animation ≠ scene time in det. mode)
    overlayEl.querySelectorAll('.det-pulse-ring').forEach(circle => {
      const ringStart = parseFloat(circle.dataset.ringStart ?? 0);
      const ringDur   = parseFloat(circle.dataset.ringDuration ?? 1.8);
      const t = runtime.currentTime;
      if (t < ringStart) {
        circle.style.transform = 'scale(0)';
        circle.style.opacity   = '0';
        return;
      }
      const progress = Math.min(1, (t - ringStart) / ringDur);
      // Mirror CSS keyframe: scale 0→1, opacity 0→0.9 (at 12%)→0
      const opacity = progress < 0.12
        ? (progress / 0.12) * 0.9
        : 0.9 * (1 - (progress - 0.12) / (1 - 0.12));
      circle.style.transform = `scale(${progress})`;
      circle.style.opacity   = String(Math.max(0, opacity));
    });

    reproject(map, overlayEl);
  }

  function reset() {
    runtime.fired.clear();
    runtime.currentTime = 0;
    runtime.cameraShakeActive = null;
    clearOverlay(overlayEl);
    runtime.createdFillIds.forEach(id => {
      if (map.getLayer(`${id}-layer`)) map.removeLayer(`${id}-layer`);
      if (map.getSource(`${id}-source`)) map.removeSource(`${id}-source`);
      const overlayFill = document.getElementById(`${id}-overlay`);
      if (overlayFill) overlayFill.remove();
      const fillSvg = document.getElementById(`${id}-fill-svg`);
      if (fillSvg) fillSvg.remove();
    });
    runtime.createdBorderIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
    runtime.createdArrowIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
    runtime.createdPulseRingIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
    runtime.createdFillIds.clear();
    runtime.createdBorderIds.clear();
    runtime.createdArrowIds.clear();
    runtime.createdPulseRingIds.clear();
    runtime.createdLabelIds.clear();
    runtime.removedLabelIds.clear();
    runtime.pendingFillExits.length = 0;
    runtime.pendingBorderExits.length = 0;
    runtime.pendingCameraEnds.length = 0;
    // Restart event collection on a backward step so the re-walk stays consistent.
    MapEffects.resetEvents();
    const container = map.getContainer();
    if (container) container.style.transform = '';
  }

  function getState() {
    return {
      t: runtime.currentTime,
      firedEvents: runtime.fired.size,
      labels: runtime.overlayEl.querySelectorAll('.effect-label').length,
      arrows: runtime.overlayEl.querySelectorAll('.effect-arrow').length,
      hash: _hashString(
        JSON.stringify({
          t: runtime.currentTime.toFixed(3),
          fired: runtime.fired.size,
          labels: runtime.overlayEl.querySelectorAll('.effect-label').length,
          arrows: runtime.overlayEl.querySelectorAll('.effect-arrow').length,
        })
      ),
    };
  }

  return {
    stepTo,
    reset,
    getState,
  };
}

// Public API (map.html + tests) — merge with registry helpers on MapEffects
window.MapEffects = Object.assign(window.MapEffects || {}, {
  applyFill,
  applyBorder,
  removeBorder,
  removeArrow,
  pulseRing,
  drawArrow,
  showLabel,
  runTimeline,
  reproject,
  clearOverlay,
  bindReproject,
  createDeterministicRuntime,
  _curvedPath: curvedPath,
  _straightPath: straightPath,
  _toPixel: toPixel,
  _typewriterReveal: typewriterReveal,
  _animateCounter: animateCounter,
  _animateTravelDot: animateTravelDot,
});
