"""Post-render channel look - independent of Blender's compositor (Phase 4).

Runs in ffmpeg/python AFTER render (rule #5): per-mood color grade
(presets/grade/*.json), subtle film grain, light vignette, optional chromatic
aberration on neon scenes. Keeps the aesthetic tunable without re-rendering.

TODO: implement.
"""
