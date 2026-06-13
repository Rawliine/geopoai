'use strict';

/**
 * Timeline actions that manipulate the Mapbox map camera (extracted from legacy switch).
 */

MapEffects.registerAction('cameraShake', function (map, overlayEl, entry, ctx) {
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
});

MapEffects.registerAction('flyTo', function (map, overlayEl, entry, ctx) {
  const params = entry.params ?? {};
  if (!ctx.deterministic) {
    map.flyTo({
      center: params.center,
      zoom: params.zoom,
      pitch: params.pitch ?? 0,
      bearing: params.bearing ?? 0,
      duration: (params.duration ?? 2) * 1000,
      essential: true,
    });
  }
});
