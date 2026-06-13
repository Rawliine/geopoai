'use strict';

/**
 * Timeline action registry. Effect modules self-register; runtime dispatches via getAction.
 * @global
 */
(function initMapEffectsRegistry(global) {
  const g = global;
  g.MapEffects = g.MapEffects || {};
  const M = g.MapEffects;
  if (M.registerAction) return;

  const actions = Object.create(null);

  M.registerAction = function registerAction(name, fn) {
    if (actions[name]) {
      console.warn('[MapEffects] overwriting registered action:', name);
    }
    actions[name] = fn;
  };

  M.getAction = function getAction(name) {
    return actions[name] || null;
  };
}(typeof window !== 'undefined' ? window : globalThis));
