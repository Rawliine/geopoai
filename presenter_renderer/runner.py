"""Blender Python entry point for the presenter layer (Phase 3).

Invoked headless:
    blender --background <scene>.blend --python runner.py -- <shot.json>

Reads the shot JSON, applies the camera + mood preset, sequences gesture
actions along the timeline, loads TTS audio into the VSE, drives lipsync from
cached visemes, and renders. Composes the lib/* building blocks. See AGENT.md
"The shot JSON".

TODO: implement (Phase 3 - animation pipeline).
"""
