"""Thin host-side entry point for the presenter layer (AGENT.md).

Usage:
    python pipeline/render_presenter.py <shot.json>

Validates the shot JSON (schema/validator.py), resolves paths
(presenter_renderer/lib/paths.py), then invokes Blender headless on the right
scene with presenter_renderer/runner.py. Output -> output/presenter/<shot_id>.mp4
plus <shot_id>.meta.json.

TODO: implement (Phase 3).
"""
