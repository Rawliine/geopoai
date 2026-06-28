'use strict';

/**
 * media.js (W26) — reserved-region media support.
 *
 * The renderer draws NO media here. Screen-anchored media (a top-half video
 * box, a lower-third, etc.) is composited in post by composition/media_overlay.py.
 * This module's only job is to reserve a screen region for a bounded time window
 * so the map's own screen-fixed overlays (titles/labels) stay out of it — and to
 * surface those windows (via layoutHints) for the reserved-window sidecar.
 *
 * Actions are registered in W26.T1.
 */
