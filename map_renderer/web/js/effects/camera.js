'use strict';

/**
 * Timeline actions that manipulate the Mapbox map camera (extracted from legacy switch).
 */

const _cameraShake = function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  if (ctx.deterministic && ctx.runtime) {
    const { intensity = 'medium', durationMs = 400 } = params;
    ctx.runtime.cameraShakeActive = {
      start: Number(entry.at ?? 0),
      duration: Math.max(0, Number(durationMs) / 1000),
      intensity: String(intensity),
    };
  } else {
    const { intensity = 'medium', durationMs = 400 } = params;
    const container = map.getContainer();
    const amplitudes = { light: 3, medium: 6, heavy: 12 };
    const amp = amplitudes[intensity] ?? 6;
    container.style.transition = 'none';
    let elapsed = 0;
    const interval = 30;
    const shakeTimer = setInterval(() => {
      elapsed += interval;
      const dx = (Math.random() - 0.5) * amp;
      const dy = (Math.random() - 0.5) * amp;
      container.style.transform = `translate(${dx}px, ${dy}px)`;
      if (elapsed >= durationMs) {
        clearInterval(shakeTimer);
        container.style.transform = '';
      }
    }, interval);
  }
};
_cameraShake.eventMeta = { type: 'camera', intensity: 0.6 };
MapEffects.registerAction('cameraShake', _cameraShake);

const _flyTo = function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  // Deterministic camera is driven by the camera plan in map.html
  // (buildDeterministicCameraPlan / evaluateCameraPlan), not by this action.
  if (ctx.deterministic) return;
  const durationMs = (params.duration ?? 2) * 1000;
  // Suspend idle_drift for the duration of the move; it resumes after (W13.T1).
  MapEffects._cameraBusyUntil = Math.max(
    MapEffects._cameraBusyUntil || 0,
    performance.now() + durationMs
  );
  map.flyTo({
    center: params.center,
    zoom: params.zoom,
    pitch: params.pitch ?? 0,
    bearing: params.bearing ?? 0,
    duration: durationMs,
    easing: MapEffects.getEasing(params.easing),
    essential: true,
  });
};
_flyTo.eventMeta = { type: 'camera', intensity: 0.5 };
MapEffects.registerAction('flyTo', _flyTo);

/* rotateAround — bearing orbit around a pinned point, pitch held (W13.T1).
   Realtime: easeTo the new bearing while keeping the orbit center centered.
   Deterministic: handled as a camera-plan segment in map.html. */
const _rotateAround = function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  if (ctx.deterministic) return;
  const durationMs = (params.duration ?? 2) * 1000;
  const degrees = Number(params.degrees ?? 0);
  MapEffects._cameraBusyUntil = Math.max(
    MapEffects._cameraBusyUntil || 0,
    performance.now() + durationMs
  );
  map.easeTo({
    center: params.center ?? map.getCenter(),
    bearing: map.getBearing() + degrees,
    pitch: map.getPitch(),         // pitch held
    zoom: map.getZoom(),
    duration: durationMs,
    easing: MapEffects.getEasing(params.easing),
    essential: true,
  });
};
_rotateAround.eventMeta = { type: 'camera', intensity: 0.5 };
MapEffects.registerAction('rotateAround', _rotateAround);
