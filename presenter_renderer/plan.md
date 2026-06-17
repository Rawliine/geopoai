# GeoPoAI — Presenter (Owl Scholar) Implementation Plan

Status: proposal, fluid. The presenter is the channel's recurring face — an anthropomorphic owl scholar in two recurring scenes (war-room map table, late-night diner booth). Built in Blender, driven by JSON.

---

## Target end state

A Blender-based renderer that takes a JSON describing a presenter shot — scene choice, camera, gestures, lipsync audio, lighting mood — and produces an MP4 clip. The orchestrator (n8n / langgraph) calls into this layer when the script beat is "presenter-on-camera." Otherwise the script cuts to map, manim, or B-roll.

```
script beat: "presenter explains the Suez dilemma"
    │
    ▼
orchestrator generates presenter shot JSON
    │
    ▼
pipeline/render_presenter.py
    │
    ├── validate JSON against schema
    ├── load scene .blend (diner OR war_table)
    ├── load owl character (linked from owl.blend, single source of truth)
    ├── apply camera preset (booth_medium, booth_close, war_table_lean_in, ...)
    ├── apply lighting/mood preset (contemplative, tense, ...)
    ├── load TTS audio → drive lipsync via Rhubarb → owl visemes
    ├── sequence gesture actions from gestures library
    ├── render headless (Eevee preview / Cycles final)
    ├── post-render composite (color grade, grain, vignette)
    └── output/presenter/<clip_id>.mp4
```

---

## Build vs buy decision

**Build from scratch:**
- The owl mesh, rig, materials, shape keys (channel IP — recurring character)
- Owl wardrobe — tweed waistcoat, glasses, trousers (character-specific)
- A small set of custom presets — channel-specific lighting moods, camera framing, color grading
- The Python orchestration layer (runner, lipsync mapping, gesture sequencing)

**Buy / source freely:**
- All scene environments — diner booth, war-room consoles, neon signs, props
- All textures, HDRIs, materials for environments
- Specific props — coffee mugs, notebooks, table lamps, file folders, maps as textured planes

The owl is the brand asset. Everything else is set dressing. Polyhaven, BlenderKit, Sketchfab CC0/CC-BY assets cover ~95% of environment needs. Asset marking discipline (`.meta.json` per asset) applies here exactly as it does for B-roll.

---

## Phase 0 — Owl base (≈2 weeks)

Goal: a working owl mesh, rigged, with the minimal shape keys to lipsync.

- `characters/owl.blend` — single source of truth, linked into scenes
- Mesh: built body-first from primitive sphere/cube blocks, sculpted to spec. Anthropomorphic stylized realism; subtle "plumage bulk" silhouette.
- Armature: standard hierarchy (root → spine → neck → head; root → wing_L/R; root → leg_L/R → talon controls)
- Control bones / empties:
  - `eye_L_target` + `eye_R_target` (Track To constraints on each eye)
  - `eye_convergence_target` (parent target that both eye targets follow, gives natural focus convergence)
  - `head_tilt_target` (Damped Track on head bone)
  - IK chains on talons for prop interaction
- Shape keys (Basis + visemes only, full set in Phase 1):
  - `Basis`
  - `viseme_A` through `viseme_X` (9 Rhubarb shapes, adapted for owl beak/disc)
- Proxy mode: low-poly placeholder feathers in viewport; full feather system gated to render time
- `characters/owl_shapekey_reference.md` — human-readable mapping of every shape key

Exit criteria: owl mesh visible in viewport, eye tracking works (move target empty → eyes follow), all 9 visemes blend correctly. Render time per frame at preview Eevee < 5s on local RTX 3070 Ti.

---

## Phase 1 — Owl details (≈1 week)

Goal: production-ready owl with full expression range.

- Wardrobe as separate geometry:
  - Off-white shirt
  - Dark olive/charcoal tweed waistcoat with herringbone pattern. Subtle hair particle system for fuzz — but with a **baked normal map alternative for medium/wide shots** to avoid render-time blowup
  - Trousers (dark brown corduroy or wool flannel) with tail accommodation
  - Small wire-frame reading glasses (separate object, parented to head)
- Materials: subtle velvet shader / SSS on feathers; matte slightly weathered tweed; brass or dark metal for glasses; rough bump for leathery talons
- Feather grooming via Geometry Nodes — facial disc gets dense radiating pattern; wings get longer structured cards; body gets soft layered down
- Full shape key set:
  - 9 visemes (refined from Phase 0)
  - 6 emotion overlays (`emo_neutral`, `emo_concerned`, `emo_alert`, `emo_contemplative`, `emo_skeptical`, `emo_focused`)
  - Micro-expressions (`brow_raise_inner`, `brow_raise_outer`, `brow_furrow`, `eye_squint_L`, `eye_squint_R`, `beak_part_slight`)
  - Asymmetric horn flexion (`horn_L_flare`, `horn_R_flare`)
- Asymmetry pass: subtle imperfection in horn tufts, brow ridge, wing folding to break logo-template symmetry

Exit criteria: owl renders at production quality (Cycles, full feathers) in ≤90s/frame on Verda B200. Shape key blending tested against canned phoneme sequences. Wardrobe deforms correctly across all gesture actions from Phase 3.

---

## Phase 2 — Scenes (≈1 week)

Goal: both scenes assembled, owl integrated, ready for animation.

### Scene 1 — War-Room Map Table (`scenes/war_table.blend`)

Editorial illustration aesthetic: command center, glowing tactical map-table, cool cyan underlight on owl's face.

Asset sources (target):
- Map table — Sketchfab or BlenderKit (custom emissive material applied)
- Consoles, command room interior — Sketchfab CC-BY or Kitbash3D
- Troop markers, flags — procedural Geometry Nodes (custom, recurring brand)
- Background silhouettes (operators) — low-poly placeholder geometry, deep depth-of-field blur
- HDRI — dim industrial interior from Polyhaven

The map texture on the table surface is **a frame rendered by the Mapbox engine** — this is a deliberate cross-engine reuse. Whatever territory is being discussed in the episode, render a Mapbox frame, drop it onto the table as an image texture, light from below.

### Scene 2 — Late-Night Diner Booth (`scenes/diner.blend`)

Editorial illustration aesthetic: Hopper-meets-Wes-Anderson, warm amber interior, cold teal/magenta neon through rain-slick window.

Asset sources (target):
- Diner booth, formica table, chairs — BlenderKit diner pack
- Coffee mug, notebook, manila folders — BlenderKit or Polyhaven
- Pendant lamp — custom or BlenderKit, key practical light source
- Window + rain-slick effect — geometry + custom shader; rain texture from Polyhaven
- Neon signs — `scenes/_shared/neon_signs.blend` (reusable across episodes)
- Background street — low-detail facade with strong DOF blur
- HDRI — night urban, very dim, mostly overridden by practical lights

Maps and document props on the table are textured planes with image textures — same Mapbox-frame reuse pattern as war-table.

Both scenes use the same owl, linked from `characters/owl.blend`. Edit the owl once, both scenes update.

Exit criteria: both scenes render at production quality with owl placed and lit. Asset manifests complete. Switching between scenes is a single config change in the shot JSON.

---

## Phase 3 — Animation pipeline (≈1.5 weeks)

Goal: JSON-driven scene runner with gesture library + lipsync.

### Gesture library

15-20 reusable actions on the owl armature, each ~1-3s, returning to neutral.

```
owl_idle_breathing         (4s loop, subtle chest movement)
owl_idle_micro_blink       (blink pattern, parallel-safe)
owl_lean_in                (1.5s, returns to neutral)
owl_lean_back              (1.5s)
owl_head_tilt_left         (1s)
owl_head_tilt_right        (1s)
owl_glance_down            (look at table briefly, 1s)
owl_glance_up              (1s)
owl_beak_tap               (small thinking beat, 0.7s)
owl_wings_settle           (rare beat for emphasis, 2s)
owl_lift_coffee            (interaction with prop, 3s, diner-scene only)
owl_remove_glasses_thoughtful  (gesture beat, 2s)
owl_steeple_talons         (1s, contemplative)
owl_point_at_map           (1.5s, war-room scene)
owl_shake_head_no          (1.2s)
owl_nod_yes                (1s)
```

Each stored as a Blender Action in `characters/owl.blend`, accessed via NLA editor or python.

### Lipsync pipeline

1. TTS audio (`fishaudio/s2-pro`) generates the line, saved as WAV with timecode
2. Rhubarb processes WAV → phoneme timeline → 9-shape viseme sequence
3. `lib/lipsync.py` maps Rhubarb's 9 shapes to **owl-adapted visemes** (the mapping is in `gestures/owl_viseme_mapping.json` — owl beak has limited mouth shape, so the mapping cheats with facial disc feather deformation)
4. Animation curves baked onto owl shape keys at audio timecode
5. Cached by audio hash in `cache/visemes/` — never reprocess the same audio

### Scene runner

`runner.py` is the Blender Python entry point invoked as `blender --background <scene>.blend --python runner.py -- <shot.json>`.

Reads the shot JSON, applies camera preset, applies mood preset, sequences gestures along the timeline, loads TTS audio into VSE for sync, drives lipsync from cached visemes, renders.

Shot JSON example:
```json
{
  "shot_id": "ep017-presenter-002",
  "scene": "diner",
  "duration_seconds": 12,
  "camera_preset": "booth_medium",
  "mood_preset": "contemplative",
  "audio_path": "audio/ep017_002.wav",
  "timeline": [
    { "at": 0.0,  "gesture": "owl_idle_breathing", "loop": true },
    { "at": 1.2,  "gesture": "owl_lean_in" },
    { "at": 3.5,  "gesture": "owl_glance_down" },
    { "at": 6.0,  "gesture": "owl_lean_back" },
    { "at": 8.5,  "gesture": "owl_lift_coffee" }
  ],
  "quality": "preview"
}
```

Exit criteria: a 15-second clip rendered end-to-end from JSON, with lipsync, gestures, and proper mood lighting. Two such clips, one in each scene, demonstrate cross-scene reuse.

---

## Phase 4 — Render pipeline + compositor (≈4-5 days)

Goal: production-quality renders with a tunable channel-look post-pass.

- Render modes:
  - `preview` — Eevee, 64 samples, 800x450, ~3s/frame on RTX 3070 Ti
  - `draft` — Eevee, 256 samples, 1280x720, ~10s/frame on RTX 3070 Ti or Verda L40S
  - `full` — Cycles, 1024 samples, 1920x1080, ~60-90s/frame on Verda B200
- `lib/render.py` — orchestrates the render, handles tile-based for Cycles, GPU device selection
- `lib/compositor.py` — post-render pass (independent of Blender's compositor, runs in ffmpeg/python):
  - Color grade applied per mood (`presets/grade/contemplative.json`, etc.)
  - Subtle film grain
  - Light vignette
  - Optional chromatic aberration on neon scenes
- `lib/audio.py` — drops final audio into VSE, exports synced

The grade is applied post-render, never baked into Blender materials. This lets the channel aesthetic be tuned without re-rendering 100+ frames.

Exit criteria: end-to-end production render of a 20-second clip in both scenes. Render farm-style batch job runs on Verda B200, completes within wall-clock target (clip duration × 60s/frame ÷ 60fps × 24 batch-parallel ≈ 5 minutes wall-clock for 20s clip).

---

## Phase 5 — Asset hygiene + iteration tools (≈3 days)

Goal: the system is maintainable by the user + Claude Code over months.

- `_assets_manifest.json` in `scenes/` — tracks every third-party asset used per scene file. Critical because Blend files don't carry license metadata.
- Asset audit pass — walks scenes, verifies every external asset has `.meta.json`, surfaces missing
- Preview render harness — for Claude Code iteration loops (see `infra/OPERATOR_RUNBOOK.md` for the iteration pattern):
  - `scripts/preview.py` — runs a script, generates multi-angle preview PNG, prints mesh/scene stats to stdout
  - Output to `/tmp/preview_*.png` — Claude Code reads them between iterations
- Shape key tester — renders the owl through every shape key in a sequence, produces a QC sheet for visual review
- Gesture catalog renderer — renders each gesture in the library as a 3-second clip, indexed for review

Exit criteria: any edit to the owl or scenes can be reviewed via preview render within 10 seconds. Asset audit passes cleanly.

---

## Cross-cutting decisions to lock in

**Owl is the only fully-custom mesh.** Every other asset (props, environment, materials, HDRIs) is sourced. This compresses the build timeline by weeks and reduces maintenance surface.

**Body-first, clothes-second.** Mesh built nude (feathered), wardrobe added as separate geometry parented to the armature. Tweed deformation as a single mesh is hell; separate geometry deforms cleanly and the fuzz particle system can target the waistcoat surface specifically.

**Proxy feathers in viewport, full feathers at render.** Viewport stays interactive; render quality is uncompromised.

**Color grading is post.** Blender outputs flat-ish; the grade applies in compositor.py per mood preset. Channel aesthetic stays tunable.

**Single source of truth for the owl.** `characters/owl.blend` linked into every scene. Edit once, both scenes update.

**Map textures on props come from the Mapbox engine.** A frame rendered by Mapbox is dropped onto the war-room table or diner table as an image texture. Cross-engine reuse keeps geographic content consistent.

**Cache aggressively.** Visemes cached by audio hash. Render frames cached by scene+animation hash. Re-renders should hit cache when nothing changed.

---

## Open questions

- **Voice + audio quality tier.** Is `fishaudio/s2-pro` good enough as a long-term choice, or should we plan for a tier-2 upgrade after Phase 4? Probably good enough to launch; revisit at episode 10.
- **Performance capture vs hand-keyframing.** Should the gesture library be hand-keyed or driven by a performance capture tool? Hand-keyed for now — the gestures are stylized, not realistic, and the library is small enough to author manually. Performance capture is overkill.
- **Number of scenes.** Two scenes (diner + war-table) is the launch set. When does a third scene make sense? Episode 15-20, once the existing two start feeling repeated.
- **Subtle character development.** Should the owl evolve subtly over time (slightly older glasses, different waistcoat in winter, new prop on the table)? Aspirational; possibly Phase 5+ if the channel takes off.
- **Variant owls.** Twin/sibling characters for dialogue scenes? Out of scope for now. Solo presenter is the format.
- **Audio-reactive secondary motion.** Idle breathing rate responding to script intensity, brow tension following narration tone? Cool but deferred — gesture library handles 90% of this manually.
- **Render farm vs local for Cycles final.** Local RTX 3070 Ti can do Cycles but slowly. Verda B200 is faster but has cold-start overhead. Threshold: clips longer than 8s probably warrant Verda.

---

## What we're not building

- Realistic owl. The aesthetic is stylized — Wes Anderson / Fantastic Mr. Fox tactile, not photorealistic.
- Full body animation system. The owl sits or stands behind a table; legs are present but rarely visible. Don't over-rig.
- Multiple owl variants per episode. One owl, two scenes. Variants are speculation.
- A custom shape key editor UI. Use Blender's native shape key panel; no point reinventing.
- Live performance capture. Not the right tool for the channel's aesthetic.
