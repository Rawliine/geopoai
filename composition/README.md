# Composition layer

Episode assembly: ordered clips, transitions, policy-driven caption burn-in,
sound mix, grading, and per-platform exports. Driven by
`docs/contracts/compose.schema.json`.

## CLI

```bash
conda run -n geopo python pipeline/compose.py <compose.json> <out_name>
```

Writes `output/episodes/<out_name>/final_<profile>.mp4` for each profile in the
compose spec. Intermediate artifacts land in `output/episodes/<out_name>/work/`.

| Flag | Effect |
|------|--------|
| `--keep-temp` | Retain intermediate files in the workdir for debugging |
| `--no-grade` | Skip the grading LUT / vignette pass |

## Pass pipeline order

Each pass is idempotent and individually skippable via compose `flags` or CLI:

1. **Assemble video** — `composition/transitions.py` concatenates clips and
   applies boundary transitions (`cut`, `crossfade`, `whoosh`).
1b. **Media overlays** (W26) — `composition/media_overlay.py` composites each
   `media_overlays[]` box (a top-half video, lower-third, …) onto the assembled
   timeline: contain-fit + letterbox (no stretch), token-styled border, gated to
   its `[start, end]` episode-time window. Runs once before the profile loop;
   skipped when there are no overlays or `flags.media: false`. The map renderer
   keeps its own screen-fixed text out of the reserved band and emits the matching
   window in `{clip}.regions.json` (cross-check); media is never decoded in the
   browser.
2. **`captions.build`** — W15 generates ASS from VO + layouts (stub in W17 lane).
3. **Burn ASS** — ffmpeg subtitles filter; limited to `burn_windows` (see below).
4. **`sound.build`** — W16 mixes SFX from shifted `events.json` files (stub in W17).
5. **Mux audio** — replace/add `mix.wav` (or VO when sound is skipped).
6. **Grade** — optional `lut3d` when `tokens.grading.lut` is set; vignette/grain
   from tokens. Skipped with `--no-grade` or `flags.grade: false`.
7. **Export** — scale/pad to profile resolution; single H.264 encode
   (`h264_nvenc` when ffmpeg reports it, else `libx264`); AAC 192k.

Re-encode policy: `cut` boundaries use the concat demuxer with stream copy when
codecs match; crossfade/whoosh use ffmpeg filters during assembly. Caption burn,
grade, and the final export encode are the remaining video encodes.

## Compose spec fields

Core fields are validated against `docs/contracts/compose.schema.json`.

| Field | Purpose |
|-------|---------|
| `episode_id` | Episode identifier |
| `clips[]` | `clip_id`, `path`, `offset_s`, optional `events_path`, `layout_path` |
| `transitions[]` | `after_clip_id`, `type` (`cut` \| `crossfade` \| `whoosh`), optional `duration` |
| `audio.vo` | Episode voice-over WAV |
| `audio.bed` | Optional music bed (reserved) |
| `export.profiles` | `yt_long` and/or `shorts` |
| `flags` | `captions`, `sound`, `grade` booleans (default on when omitted) |

**Relaxed (lane-local until schema amend):**

| Field | Purpose |
|-------|---------|
| `caption_policy.burn_in` | `never` \| `broll_only` (default) \| `shorts_only` \| `always` |
| `caption_policy.sidecar` | Emit `.srt` sidecar when burn is `never` |
| `clip.renderer` | Storyboard renderer tag (`broll`, `mapbox`, …) for burn windows |
| `clip.captions` | Per-clip `false` subtracts that interval from burn windows |
| `light_leak` | Optional screen-blend overlay at last transition (off by default) |

Legacy `flags.captions: false` is equivalent to `caption_policy.burn_in: never`.

## Caption policy → `burn_windows`

`burn_windows` are half-open `[start, end)` intervals in **episode time** passed
to the ASS burn step (and conceptually to `captions.build` at integration):

- `never` — skip ASS burn; emit `.srt` only when `sidecar: true`.
- `broll_only` — burn only on clips whose `renderer === "broll"` (or path under
  `/broll/` when renderer is absent).
- `shorts_only` — burn only for the active `shorts` export profile.
- `always` — full assembled timeline.

Per-clip `captions: false` removes that clip's interval from the windows.

## Transitions

| Type | Behaviour |
|------|-----------|
| `cut` | Plain concat (demuxer stream copy when codecs match). |
| `crossfade` | ffmpeg `xfade`; `duration` from spec (default 0.5s). |
| `whoosh` | Motion-cut: trim motion frames from the outgoing clip tail and incoming
  clip head using `camera` events (`phase` `end` / `start`) from each clip's
  `events.json`. Falls back to `crossfade` 0.25s when no camera event is near the
  boundary. Emits a synthetic `camera` event at the cut for W16 whoosh SFX. |

## Export profiles

| Profile | Resolution | Format token |
|---------|------------|--------------|
| `yt_long` | 1920×1080 | `horizontal` |
| `shorts` | 1080×1920 | `vertical` (TikTok/Reels) |

Encoder detection mirrors `map_renderer/runner.py` (`h264_nvenc` probe, `libx264`
fallback). Vertical source clips pass through; **horizontal-only** episodes refuse
the `shorts` profile with a clear error (no auto-crop in W17).

## Tests

```bash
conda run -n geopo pytest tests/test_compose.py -m "not render"   # fast
conda run -n geopo pytest tests/test_compose.py -m render         # demo mp4 + frame dumps
```
