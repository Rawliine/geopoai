# AGENT.md — GeoPoAI Presenter (Owl Scholar)

Working brief for any agent editing the Presenter layer. Read first.

---

## What this layer is

A Blender-based renderer that produces presenter-on-camera clips. Input: JSON describing a scene, camera, mood, audio, gestures. Output: an MP4 with the owl scholar talking and gesturing in one of two scenes (diner, war-table).

Sits beside the Mapbox engine, Manim engine, and B-roll layer. All four are content producers; the orchestrator composes their outputs into the final video.

---

## Repository layout

```
GeoPoAI/
├── presenter_renderer/
│   ├── runner.py                  # Blender Python entry: invoked headless
│   ├── characters/
│   │   ├── owl.blend              # SINGLE SOURCE OF TRUTH; linked into scenes
│   │   └── owl_shapekey_reference.md
│   ├── scenes/
│   │   ├── diner.blend
│   │   ├── war_table.blend
│   │   ├── _shared/
│   │   │   └── neon_signs.blend
│   │   └── _assets_manifest.json  # third-party assets per scene
│   ├── lib/
│   │   ├── __init__.py
│   │   ├── scene_loader.py
│   │   ├── camera_presets.py
│   │   ├── lighting.py
│   │   ├── lipsync.py
│   │   ├── animation.py
│   │   ├── audio.py
│   │   ├── render.py
│   │   └── compositor.py          # post-render grade/grain/vignette
│   ├── presets/
│   │   ├── cameras/
│   │   │   ├── booth_medium.json
│   │   │   ├── booth_close.json
│   │   │   ├── war_table_lean_in.json
│   │   │   └── establishing.json
│   │   ├── moods/
│   │   │   ├── contemplative.json
│   │   │   ├── tense.json
│   │   │   ├── analytical.json
│   │   │   └── conclusive.json
│   │   ├── grade/                 # post-render color grades
│   │   │   ├── contemplative.json
│   │   │   └── tense.json
│   │   └── shots/                 # named pre-canned sequences (optional)
│   ├── gestures/
│   │   ├── owl_gestures.json      # name → action mapping
│   │   └── owl_viseme_mapping.json
│   ├── schema/
│   │   ├── presenter_schema.json
│   │   └── validator.py
│   ├── cache/
│   │   ├── visemes/               # keyed by audio hash
│   │   └── renders/               # frame caches
│   ├── audio/                     # input TTS files
│   └── tests/
│       ├── shape_keys/            # QC sheets
│       ├── gestures/              # one clip per gesture
│       └── scenes/                # render smoke tests
├── output/
│   └── presenter/
│       ├── <shot_id>.mp4
│       └── <shot_id>.meta.json
└── pipeline/
    └── render_presenter.py        # thin entry point
```

---

## Hard rules

1. **The owl is the only custom mesh.** Environments and props come from third-party assets (Polyhaven, BlenderKit, Sketchfab CC0/CC-BY). Resist the urge to model anything that's already available.

2. **Every third-party asset has a `.meta.json`** in `scenes/_assets_manifest.json`. Same asset marking discipline as the B-roll layer. No untracked assets in scenes.

3. **Body-first, clothes-second.** Wardrobe is always separate geometry parented to the armature. Tweed waistcoat, shirt, trousers, glasses are independent objects. Never merge them into the owl mesh.

4. **Proxy mode in viewport, full feathers at render.** Feather Geometry Nodes setup is gated by a `is_render_pass` boolean. Viewport stays interactive (< 200k vert proxy); render uses full system.

5. **Color grading is post, not in Blender.** Blender outputs neutral; `lib/compositor.py` applies the per-mood grade after render. Channel aesthetic is tuned in one place.

6. **Single source of truth for the owl.** `characters/owl.blend` is the only file where the owl mesh, rig, and shape keys live. Scenes link to it (Blender's `File → Link`), never duplicate it.

7. **Map textures on props come from the Mapbox engine.** Don't paint maps by hand. A Mapbox-rendered frame is dropped onto the war-table or diner table as an image texture. Cross-engine consistency.

8. **No hardcoded paths.** Use `presenter_renderer.lib.paths` for all file lookups. Scenes need to work across machines (laptop, Verda instances).

9. **Lipsync is cached by audio hash.** Never reprocess the same audio. `cache/visemes/<sha256>.json` is the lookup. Cache hits are free.

10. **Renders are reproducible.** Same shot JSON + same owl version + same scene file = same output. Pin Blender version in `requirements.txt` or document explicitly.

---

## The shot JSON — what the orchestrator produces

```json
{
  "shot_id": "ep017-presenter-002",
  "scene": "diner",
  "duration_seconds": 12,
  "camera_preset": "booth_medium",
  "mood_preset": "contemplative",
  "format": "horizontal",
  "audio_path": "audio/ep017_002.wav",
  "timeline": [
    { "at": 0.0,  "gesture": "owl_idle_breathing", "loop": true },
    { "at": 1.2,  "gesture": "owl_lean_in" },
    { "at": 3.5,  "gesture": "owl_glance_down" },
    { "at": 6.0,  "gesture": "owl_lean_back" },
    { "at": 8.5,  "gesture": "owl_lift_coffee" }
  ],
  "map_texture": {
    "target": "diner_table_map_plane",
    "source": "output/maps/ep017_suez_frame.png"
  },
  "quality": "preview",
  "seed": 42
}
```

`scene` selects the .blend file. `camera_preset` and `mood_preset` are JSON-defined and applied at load. `timeline` schedules gesture actions; gestures map to NLA strips via `gestures/owl_gestures.json`. `map_texture` (optional) drops a Mapbox-rendered frame onto a named object in the scene.

---

## How to add a gesture

1. Open `characters/owl.blend`
2. Switch to the Action Editor, create a new Action named `owl_<verb>` (snake_case, owl_ prefix)
3. Keyframe the bones over 1-3 seconds — return to neutral at the end so the gesture can be chained
4. Save the Action with Fake User on (so it persists)
5. Update `gestures/owl_gestures.json`:
   ```json
   "owl_<verb>": {
     "duration": 1.5,
     "scene_restrictions": null,  // or ["diner"] etc.
     "notes": "short description for the LLM"
   }
   ```
6. Add the name to `schema/presenter_schema.json:gestures.enum`
7. Render a 3s test clip via `scripts/render_gesture_test.py owl_<verb>` and review

---

## How to add a shape key

1. Open `characters/owl.blend`
2. In the Object Data Properties → Shape Keys, add a new key
3. Name it following convention: `viseme_X` / `emo_X` / `brow_X` / `eye_X` etc.
4. Sculpt the deformation in Sculpt mode (or Edit mode with Shape Key active)
5. Test: scrub the slider from 0 to 1; deformation should be clean across the range
6. Update `characters/owl_shapekey_reference.md` with name + 1-line description
7. If it's a new viseme used by lipsync, update `gestures/owl_viseme_mapping.json`

---

## How to add a scene

1. Create `scenes/<name>.blend` — start from a template if available
2. Source environment + props from third-party assets, registering each in `scenes/_assets_manifest.json`:
   ```json
   {
     "scene": "<name>",
     "assets": [
       { "name": "diner_booth_v3", "source": "blenderkit", "url": "...", "license": "CC-BY-4.0", "attribution": "..." }
     ]
   }
   ```
3. Link `characters/owl.blend` (File → Link → Collection → Owl_Rig). **Don't append, link** — preserves single source of truth.
4. Place the owl with an empty parent for re-positioning across shots
5. Mark prop objects with semantic names (`diner_table_map_plane`, `coffee_mug`, `notebook`) so shot JSONs can target them
6. Author at least one camera preset for the scene (`presets/cameras/<scene>_<framing>.json`)
7. Author at least one mood preset (`presets/moods/<mood>.json` if reusing across scenes; scene-specific lighting in the .blend file)
8. Add scene name to `schema/presenter_schema.json:scene.enum`
9. Smoke-test render at preview quality

---

## How to add a camera preset

Camera presets are JSON. Loaded by `lib/camera_presets.py`.

```json
{
  "name": "booth_medium",
  "scene_restriction": "diner",
  "position": [2.5, -1.8, 1.4],
  "rotation_euler": [1.4, 0, 0.3],
  "focal_length_mm": 50,
  "depth_of_field": {
    "focus_object": "Owl_Rig",
    "f_stop": 2.8
  },
  "notes": "medium shot framing the owl from waist up, slight angle"
}
```

Add to `presets/cameras/`, register in `schema/presenter_schema.json:camera_preset.enum`.

---

## The owl viseme mapping

Rhubarb outputs 9 standard shapes (`A`-`H` + `X` for silence) tuned for human mouths. Owls have a beak, not a mouth — direct mapping looks wrong. The `gestures/owl_viseme_mapping.json` translates Rhubarb's 9 to a blend of owl shape keys + facial-disc-feather deformation that suggests the mouth shape without an unnatural mouth open.

```json
{
  "A": { "viseme_A": 1.0 },
  "B": { "viseme_B": 0.7, "beak_part_slight": 0.3 },
  "C": { "viseme_C": 1.0 },
  "D": { "viseme_D": 0.8, "beak_part_slight": 0.6 },
  "E": { "viseme_E": 0.9, "beak_part_slight": 0.4 },
  "F": { "viseme_F": 1.0 },
  "G": { "viseme_G": 0.8 },
  "H": { "viseme_H": 1.0 },
  "X": { "viseme_X": 1.0 }
}
```

Update this file if visemes are added or the mapping needs tuning.

---

## Quality modes

```
preview → Eevee, 64 samples, 800x450, fast iteration (~3s/frame on RTX 3070 Ti)
draft   → Eevee, 256 samples, 1280x720
full    → Cycles, 1024 samples, 1920x1080 (or 1080x1920 for vertical)
```

LLM-authored shots default to `preview` until human approval. Schema validates the enum.

---

## Render targets

```
Local (RTX 3070 Ti)         → preview, occasionally draft for spot-checks
Verda L40S (cheap GPU)       → draft batch
Verda B200 (production)      → full quality, parallelizable across frames
```

Local handles all authoring work. Verda handles final renders only. See `infra/OPERATOR_RUNBOOK.md` for instance management.

---

## Commands

```bash
# render a single shot
python pipeline/render_presenter.py <shot.json>

# render a gesture test clip
python presenter_renderer/scripts/render_gesture_test.py owl_lean_in

# generate shape key QC sheet (renders owl through every shape key)
python presenter_renderer/scripts/render_shapekey_qc.py

# audit scene assets — checks every third-party asset has metadata
python -m presenter_renderer.lib.asset_audit

# regenerate viseme cache for an audio file (force re-Rhubarb)
python -m presenter_renderer.lib.lipsync --force <audio.wav>

# Blender invocation (raw, mostly for debugging)
blender --background scenes/diner.blend --python runner.py -- shot.json
```

---

## Pitfalls

- **Linked owl gotchas.** Linking the owl into a scene means edits to `owl.blend` propagate. If you change a shape key name in `owl.blend`, every scene's animation that references it breaks silently. Use the `owl_shapekey_reference.md` as the contract; rename via a deliberate migration, not casual editing.
- **Hair particle system memory.** Full feather system can consume gigabytes. Always render with `is_render_pass=True` switch; viewport in `False` mode. If the file becomes slow to open, the switch was probably left on.
- **Cycles + denoiser quirks.** Some denoisers smudge fine feather detail. Test the OpenImageDenoise pre-render denoise vs viewport denoise. Production quality usually needs OIDN with a higher prefilter.
- **Audio sync drift.** The VSE timeline and the 3D timeline can drift if scene fps and audio sample rate aren't matched. Standardize at 24fps + 48kHz. `lib/audio.py` validates on load.
- **Rhubarb on noisy audio.** TTS output is clean; if you ever swap to recorded voice, Rhubarb can mis-detect on background noise. Pre-process with a denoise pass.
- **Render to single image when iterating, sequence only for final.** Single image lets Claude Code read one PNG and comment quickly. Image sequence + ffmpeg is overhead during iteration.

---

## The Claude Code iteration loop

For authoring/editing the owl, scenes, or gestures with Claude Code in the loop:

1. Claude Code edits a Python script (e.g., adjusts a shape key sculpt programmatically, or tweaks a material)
2. Script invoked: `blender --background characters/owl.blend --python <script>.py`
3. Script saves the .blend and runs `scripts/render_qc.py` which produces multi-angle preview PNGs in `/tmp/`:
   - `/tmp/owl_front.png`
   - `/tmp/owl_three_quarter.png`
   - `/tmp/owl_side.png`
   - Plus a stats dump to stdout (vert count, materials, shape keys, errors)
4. Claude Code reads the PNGs, sees the result, comments or iterates
5. User reviews the same PNGs in their file browser, gives natural-language feedback
6. Loop continues until satisfactory

See `infra/OPERATOR_RUNBOOK.md` for the broader iteration pattern + render harness details.

---

## When in doubt

- Buy the asset, don't model it. Only the owl gets bespoke treatment.
- Preview render first, always. Cycles is for final.
- If a gesture or shape key is missing, add it deliberately with a test, don't improvise inline.
- Read `recap.md` for design rationale, `plan.md` for build sequence.
