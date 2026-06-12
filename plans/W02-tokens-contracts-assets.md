# W02 — Design tokens, frozen contracts, asset provisioning

Branch: `agents/w02-tokens` · Depends on: W00. May run parallel to W01.
**Highest-leverage lane: W10–W17 all build against these artifacts.**

## Goal
One source of truth for the brand (tokens), frozen interchange schemas
(events/layout/episode/compose), an automated asset-pack provisioner
(manifest-as-lockfile — no manual link hunting, ever), and the composition
package skeleton.

## Allowlist
config/design_tokens.json · docs/contracts/ · tools/ · assets/ ·
composition/ (stubs only) · manim_renderer/theme/*.py ·
map_renderer/web/css/base.css · tools/gen_tokens_css.py · .gitignore additions

## Checklist

### T1 — `config/design_tokens.json`
Source of truth for palette = the EXISTING manim theme: extract canonical
values from `manim_renderer/theme/palette.py` (background `#0e1116`, surface
`#1a1f2e`, the neon set, text colors) — do not invent new hex unless a role
below has no equivalent. Structure:

```jsonc
{
  "version": 1,
  "palette": {
    "background": "...", "surface": "...",
    "text": { "primary": "...", "secondary": "..." },
    "roles": {            // semantic, used by ALL renderers + captions + icons
      "highlight": { "core": "...", "glow": "...", "dim": "..." },
      "threat":    { "core": "...", "glow": "...", "dim": "..." },
      "ally":      { "core": "...", "glow": "...", "dim": "..." },
      "contested": { "core": "...", "glow": "...", "dim": "..." },
      "neutral":   { "core": "...", "glow": "...", "dim": "..." }
    }
  },
  "typography": {         // keep what manim already uses
    "display": "Barlow Condensed", "primary": "Inter",
    "mono": "JetBrains Mono", "math": "STIX Two Math",
    "scale": { /* copy FONT_SCALE from typography.py */ }
  },
  "glow": { "core_px": 2, "halo_px": 6, "halo_opacity": 0.35 },
  "timing": {
    "beat_min_s": 2.0, "beat_max_s": 4.0, "static_max_s": 2.5,
    "stagger_ms": 120, "exit_ratio": 0.6,
    "read_rate_cps": 15, "callout_min_s": 1.2
  },
  "safe_areas": {
    "vertical":   { "caption_band": [0.78, 0.92],
                    "platform_margins": { "top": 0.06, "bottom": 0.10, "left": 0.04, "right": 0.14 } },
    "horizontal": { "caption_band": [0.84, 0.96],
                    "platform_margins": { "top": 0.04, "bottom": 0.04, "left": 0.04, "right": 0.04 } }
  },
  "grading": { "lut": null, "vignette_opacity": 0.25, "grain_opacity": 0.06 },
  "sound": { "palette_manifest": "assets/sfx/palette.json", "vo_duck_db": -6, "target_lufs": -14 }
}
```

### T2 — Consumers
- `tools/tokens.py`: cached loader (`load_tokens()`), used by Python consumers.
- `manim_renderer/theme/palette.py` + `typography.py` + `timing.py`: read from
  tokens with the current literals as fallback. Manim renders must be
  pixel-identical before/after (the tokens were extracted FROM them).
- `tools/gen_tokens_css.py`: emits `map_renderer/web/css/tokens.css`
  (`:root { --role-threat-core: ...; --glow-halo-px: ...; ... }`); generated
  file is committed; `base.css` imports it; script is idempotent.

### T3 — Frozen contracts in `docs/contracts/` (JSON Schema + one fixture each)
- `events.schema.json` — per-clip `*.events.json`:
  `{ clip_id, fps, events: [{ t, type, phase, intensity, role, id }] }`,
  `type ∈ {fill, border, arrow, label, callout, highlight, camera, chapter,
  counter, insight, image, model, remove}`, `phase ∈ {start, peak, end}`,
  `intensity ∈ [0,1]`.
- `layout.schema.json` — per-clip `*.layout.json`:
  `{ clip_id, format, sample_hz, frames: [{ t, boxes: [{ id, kind, x, y, w, h }] }] }`,
  coords normalized 0–1.
- `episode.schema.json` — episode manifest: show_id, episode_id, format
  targets, stages (name → status/artifact/hash), evidence[], script
  (beats[] with VO text + emphasis markup), storyboard (beat → clip:
  renderer, scene ref, duration), clips[] (id, renderer, scene_hash,
  outputs), compose, qc, publish.
- `compose.schema.json` — clip order, per-boundary transition
  `{type: cut|crossfade|whoosh, duration}`, audio inputs (vo, bed), export
  profiles.
- `asset_manifest.schema.json` — packs: name, kind (icons|font|sfx|model),
  resolved_url, version, sha256, license, license_url, files[].
- Fixtures in `docs/contracts/fixtures/` — hand-written minimal valid
  examples; W15/W16/W17 develop against these before real emitters land.

### T4 — `tools/prepare_assets.py` + blessed catalog
`assets/catalog.py`: blessed packs with programmatic resolvers (GitHub
releases API / google/fonts raw) — `lucide`, `tabler`, `phosphor`,
`circle-flags`, `kenney-ui-audio`, `kenney-impact-sounds`, fonts
(`Inter`, `Barlow Condensed`, `JetBrains Mono`, `STIX Two Math`).
CLI: `--add <pack>`, `--all`, `--verify` (hash check), `--list`.
Behavior: resolve latest release → pin URL+sha256+license into
`assets/manifest.json` (committed lockfile) → download to `data/.cache/assets/`
→ extract needed subset to `assets/<kind>/<pack>/` (gitignored except
manifest + `assets/sfx/palette.json`). Re-running with a manifest entry uses
the pinned URL (lockfile semantics). License field mandatory; fail closed.

### T5 — SFX palette skeleton
`assets/sfx/palette.json`: event-type → sound-family mapping with fields
(file, gain_db, cooldown_s, max_per_10s) for families: whoosh, impact,
tick, swell, ambient_bed. Pick ~12 concrete files from the Kenney packs;
leave `TODO_CURATE` markers where taste is needed.

### T6 — `composition/` package skeleton
`composition/{__init__.py, engine.py, captions.py, sound.py, transitions.py,
export.py}` — signatures + docstrings + `NotImplementedError`. Signatures
(frozen, W15/16/17 implement against them):
`captions.build(vo_wav, words_json|None, layout_jsons, tokens, fmt) -> ass_path`
`sound.build(events_jsons, offsets, vo_wav, tokens) -> mix_wav`
`engine.compose(compose_spec, workdir) -> mp4` · `export.profiles(tokens) -> {...}`

## Out of scope
Implementing composition modules; renderer emission of events/layout (W10/W13);
icon/image components (W10/W12).

## Acceptance
`python tools/prepare_assets.py --add lucide && --verify` green ·
`gen_tokens_css.py` idempotent · all fixtures validate against schemas
(`python -m jsonschema` or a 10-line check script) ·
`python pipeline/render.py scripts/manim/hello.json w02_check` output visually
identical to pre-lane render.
