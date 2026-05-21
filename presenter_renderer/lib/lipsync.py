"""Rhubarb -> owl-viseme lipsync, cached by audio hash (Phase 3).

1. Rhubarb processes the WAV -> 9-shape phoneme timeline
2. gestures/owl_viseme_mapping.json maps the 9 shapes to owl shape-key blends
3. curves are baked onto the owl shape keys at audio timecode
4. results cached at cache/visemes/<sha256>.json - never reprocess (rule #9)

CLI: python -m presenter_renderer.lib.lipsync --force <audio.wav>

TODO: implement.
"""
