'use strict';

/**
 * media.js (W26) — reserved-region media support.
 *
 * The renderer draws NO media here. Screen-anchored media (a top-half video
 * box, a lower-third, etc.) is composited in post by composition/media_overlay.py.
 * This module's only job is to reserve a screen region for a bounded time window
 * so the map's own screen-fixed overlays (titles/labels) stay out of it (W26.T2)
 * — and to surface those windows (via layoutHints) for the reserved-window
 * sidecar (W26.T3).
 */

(function () {
  // Resolve a region spec to an edge + pixel rect at the current frame size.
  // Named: 'top' | 'bottom' | 'lower-third'. Custom: { rect: {x,y,w,h} } where
  // values <= 1 are treated as fractions of the frame.
  function _regionToBand(region) {
    var size = (MapEffects.layoutHints && MapEffects.layoutHints.frameSize)
      ? MapEffects.layoutHints.frameSize()
      : { w: 1920, h: 1080 };
    var W = size.w;
    var H = size.h;

    if (region && typeof region === 'object' && region.rect) {
      var rc = region.rect;
      var x = Number(rc.x) <= 1 ? Number(rc.x) * W : Number(rc.x);
      var y = Number(rc.y) <= 1 ? Number(rc.y) * H : Number(rc.y);
      var w = Number(rc.w) <= 1 ? Number(rc.w) * W : Number(rc.w);
      var h = Number(rc.h) <= 1 ? Number(rc.h) * H : Number(rc.h);
      var edge = (y + h / 2) < H / 2 ? 'top' : 'bottom';
      return { edge: edge, rectPx: { x: x, y: y, w: w, h: h } };
    }

    var name = String(region || 'top');
    if (name === 'bottom') return { edge: 'bottom', rectPx: { x: 0, y: H * 0.5, w: W, h: H * 0.5 } };
    if (name === 'lower-third') return { edge: 'bottom', rectPx: { x: 0, y: H * (2 / 3), w: W, h: H / 3 } };
    // default + 'top'
    return { edge: 'top', rectPx: { x: 0, y: 0, w: W, h: H * 0.5 } };
  }

  // reserveRegion — register a time-windowed exclusion band. Draws nothing.
  var _reserveRegion = function (map, overlayEl, entry, ctx) {
    var p = entry.params || {};
    var at = Number(entry.at != null ? entry.at : 0);
    var id = (p.id != null && String(p.id).length) ? String(p.id) : ('region-' + at);
    var band = _regionToBand(p.region);
    if (MapEffects.layoutHints && MapEffects.layoutHints.reserveBand) {
      MapEffects.layoutHints.reserveBand(id, {
        edge: band.edge,
        rectPx: band.rectPx,
        start: at,
        duration: Number(p.duration != null ? p.duration : 3),
        ramp: Number(p.ramp != null ? p.ramp : 0.4),
        region: (typeof p.region === 'string') ? p.region : 'custom',
      });
    }
  };
  _reserveRegion.eventMeta = { type: 'region', intensity: 0.5 };
  MapEffects.registerAction('reserveRegion', _reserveRegion);

  // releaseRegion — end a band early (out-ramp begins at `at`).
  var _releaseRegion = function (map, overlayEl, entry, ctx) {
    var p = entry.params || {};
    if (p.id == null) return;
    if (MapEffects.layoutHints && MapEffects.layoutHints.releaseBand) {
      MapEffects.layoutHints.releaseBand(String(p.id), Number(entry.at != null ? entry.at : 0));
    }
  };
  _releaseRegion.eventMeta = { type: 'region', intensity: 0.3 };
  MapEffects.registerAction('releaseRegion', _releaseRegion);
})();
