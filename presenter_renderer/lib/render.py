"""Render orchestration + quality modes (Phase 4).

  preview -> Eevee, 64 samples, 800x450     (local RTX 3070 Ti, fast iteration)
  draft   -> Eevee, 256 samples, 1280x720
  full    -> Cycles, 1024 samples, 1920x1080 (or 1080x1920 vertical; Verda B200)

Handles GPU device selection and (for Cycles) tile/frame batching. Renders are
reproducible: same shot JSON + owl version + scene = same output (rule #10).

TODO: implement.
"""
