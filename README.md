# GeoPoAI

Put your token in `.env`:

`MAPBOX_TOKEN=...`

Run:

`python pipeline/render_scene.py scripts/test_scene.json hook_clip`

Deterministic render mode (recommended for consistent motion quality):

- Add these scene keys in your JSON:
  - `_deterministic: true`
  - `_fps: 60`
  - `_seed: 1`
  - `_nvenc_qp: 14` (for NVENC GPUs; lower is higher quality)
- Deterministic mode renders exactly `round(duration * fps)` frames and assembles with ffmpeg.
- Determinism validation:
  - Runtime target is logged as `round(duration * fps) / fps`.
  - Repeat runs with same scene + `_seed` should produce near-identical output.
