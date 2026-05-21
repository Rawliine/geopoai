# recap.md — Presenter (Owl Scholar) Design Decisions

Companion to `plan.md` (what to build) and `AGENT.md` (working rules). This is the *why* — design rationale, decisions made, and what's still open.

---

## 1. Vision

A recurring animated presenter — an anthropomorphic owl scholar — appearing across episodes in two stable scenes. The persona accomplishes three things:

1. **Anti-uncanny** — synthetic humans look weird; a stylized owl doesn't have to clear the uncanny valley because there's no valley
2. **Brand recognition** — a recurring character that gets more beloved over time, the way Kurzgesagt's birds did
3. **Editorial voice anchor** — the channel has a consistent "presenter" no matter who's writing or directing individual episodes

The owl is the channel's face. Everything else is set dressing.

`[LOCKED]` — owl as recurring brand mascot.

---

## 2. Two scenes — why these two

**Diner booth** — accessible, approachable. Hopper-meets-Wes-Anderson visual reference. Warm interior, cold neon exterior. Maps and a coffee mug on the table. The owl is reading, processing, thinking. Inviting.

**War-room map table** — formal, analytical. Cool cyan underlight. Maps on a glowing tactical table. The owl is decisive, focused, briefing. Authoritative.

The split serves the editorial range. Some episodes are reflective ("here's what happened in 1991, and why it still matters"); some are urgent ("the next 90 days in the Strait of Hormuz"). Two scenes give us tone variety without proliferating sets.

A third scene becomes interesting once episodes 15-20 have run and the existing two start feeling worn. Until then, the rotation is a feature, not a limitation.

`[FLUID]` — two scenes for launch. Third scene Phase 5+.

---

## 3. Build vs buy — the asset philosophy

The owl is custom because it's the brand and it's animated. Everything else is sourced.

This is the highest-leverage decision in the whole presenter system. The alternative — building every prop, surface, light from scratch — adds weeks of modeling work that produces no incremental viewer value. Polyhaven, BlenderKit, Sketchfab, and Quixel between them cover ~95% of the environments and props two scenes need.

Concretely sourced (target):
- Diner booth, formica table, chairs, coffee mug, notebook, manila folders, pendant lamp
- War-room map table base, consoles, control panels
- Neon signs (reusable across episodes via `_shared/`)
- HDRIs for ambient lighting
- Textures (concrete floors, rain-slick window glass, tweed fabric base)
- Background props (silhouetted operators, distant cars, building facades)

Concretely custom:
- The owl (mesh, rig, materials, full shape key set)
- The owl's wardrobe (waistcoat, glasses, trousers, shirt)
- Procedurally generated troop markers and flag pins (Geometry Nodes, channel-specific style)
- The custom emissive map-table surface shader (channel-specific look)
- Color grade presets, channel-specific lighting moods

The asset marking discipline from the B-roll layer applies here exactly: every third-party asset has a `.meta.json` entry in `scenes/_assets_manifest.json`. License compliance audits work the same way.

`[LOCKED]` — build owl + brand-specific elements only; source everything else.

---

## 4. Owl design — choices behind the spec

**Stylized realism over photoreal.** Photoreal animal characters are deeply uncanny when they wear clothes and speak. Stylized — Fantastic Mr. Fox tactile, painterly editorial — sidesteps the problem entirely. The owl reads as a character, not a failed simulation.

**Anthropomorphic but not bipedal-human.** Digitigrade legs (bird-like), hybrid hand/talons, feather-covered arms. Resists the "owl in a suit" gag and lands in genuine character design. The proportions specifically — large head, slightly slumped academic build, plumage bulk — telegraph "intellectual scholar."

**Body first, clothes second.** The owl is feathered nude under the wardrobe. Wardrobe is separate geometry parented to the armature. Why: tweed deformation as a single merged mesh is brutal to author and renders inconsistently. Separate geometry deforms cleanly. The fuzz particle system targets the waistcoat specifically without polluting the rest of the body.

**Asymmetric brow tufts and subtle imperfection.** Symmetric character design reads as logo or mascot template. Asymmetric reads as character. Tiny break of symmetry in the horn tufts, brow ridge, and wing folding is what makes the owl look like a person rather than a brand asset.

**Glasses as a prop, not a face feature.** Wire-frame round reading glasses, separate object, parented to the head. They can be removed (gesture: `owl_remove_glasses_thoughtful`), they can catch a glint, they can be subtly different in different scenes if the channel wants to telegraph time of day or context.

`[LOCKED]` — design language. Specific shape keys may drift, rig hierarchy may evolve.

---

## 5. Rigging philosophy — animation-friendly, not perfect

The rig serves the gesture library. We're not building a feature-film hero rig. The rig needs to:
- Support 15-20 reusable gestures
- Drive eyes procedurally via target empties (eye_L_target, eye_R_target, eye_convergence_target)
- Drive head tilt via a separate target (head_tilt_target)
- Allow shape key blending for visemes + emotions + micro-expressions
- Handle talon interaction with props via IK

That's it. Don't build muscle systems, advanced facial rigging (FACS), or per-feather controls. The aesthetic is illustrative, not anatomical.

**Eye convergence is the secret weapon.** Both eyes track to a single convergence target. When the owl looks at the map on the table, the eyes converge slightly because the target is close. This is the difference between "rigged owl" and "alive owl." Almost no other detail matters as much for perceived intelligence.

`[LOCKED]` — rig serves the library, not a hero rig.

---

## 6. Shape key vocabulary

```
Basis              (neutral default)

Visemes (Rhubarb 9-shape, owl-adapted):
viseme_A through viseme_X

Emotion overlays (additive, layer on visemes):
emo_neutral, emo_concerned, emo_alert, emo_contemplative,
emo_skeptical, emo_focused

Micro-expressions (additive, blend at low values):
brow_raise_inner, brow_raise_outer, brow_furrow,
eye_squint_L, eye_squint_R, beak_part_slight,
horn_L_flare, horn_R_flare
```

Why this structure: **layering, not exhaustive enumeration**. We have 9 visemes + 6 emotions + 8 micro-expressions = 23 keys. Combined additively, they cover ~80 distinct expressions. If we built each expression as its own shape key, we'd need 80+ keys, each pre-baked, and editing one would require re-sculpting everything.

The Rhubarb 9-shape system is a phoneme-cluster mapping designed for cartoon mouths. Owls have beaks — direct translation looks unnatural. The `gestures/owl_viseme_mapping.json` translates Rhubarb's 9 to owl-specific blends that use beak articulation + facial disc feather deformation. This is the channel-specific cheat that makes the lipsync feel like an owl talking, not a human mouth grafted onto an owl head.

`[LOCKED]` — additive layered system. Specific keys may grow.

---

## 7. Gesture library — vocabulary of motion

15-20 reusable gesture actions, each 1-3s, returning to neutral so they chain. Built as Blender Actions in `characters/owl.blend`.

This is the channel's vocabulary of motion. Every episode is sequenced from this set plus auto-generated lipsync plus procedural idle (breathing, blinks). The library is small enough to author manually (no performance capture needed) and large enough to never feel repetitive when mixed.

Decision: hand-keyed, not motion-captured. The owl isn't a realistic character — exaggerated, stylized animation reads better. Motion capture would smooth out exactly the intentional stylization that makes the character work.

Idle loops (breathing, blinking) run procedurally on top of the gesture timeline. They're driven by `lib/animation.py` based on the shot duration, not authored per-shot.

`[FLUID]` — library grows by demand. Probably 25-30 actions by episode 20.

---

## 8. Lipsync approach — Rhubarb + owl mapping

```
TTS audio → Rhubarb (phoneme detection) → 9-shape viseme timeline
                                            │
                                            ▼
                            owl_viseme_mapping.json
                                            │
                                            ▼
                          owl shape keys at audio timecode
```

Rhubarb is open-source, runs offline, handles long audio in seconds. It's the cheap reliable workhorse of indie animation lipsync.

The mapping layer is the channel-specific work. Rhubarb's "A" (closed-mouth, M/B/P) maps to `viseme_A: 1.0` for the owl. Rhubarb's "D" (wide-open, A/O) maps to `viseme_D: 0.8 + beak_part_slight: 0.6` — wide-open beak alone looks unnatural on an owl, but combined with a slight beak part and disc feather deformation, it reads as a vocalized vowel.

Cache by audio hash. Once we Rhubarb a line, we never re-process it. Cache hit = free.

`[LOCKED]` — Rhubarb + owl mapping layer. Mapping file fluid.

---

## 9. Scene texture reuse — Mapbox frames as props

The map on the diner table and the tactical surface of the war-room table are both **image textures, not 3D geometry**. The image source is a frame rendered by the Mapbox engine, dropped onto a named plane object.

Why: the maps the owl is "studying" should match the episode's geographic content. Manually painting a different map texture per episode is wasted work. The Mapbox engine already produces these frames for the main video — reusing them on props is one of the highest-leverage cross-engine wins in the whole architecture.

The shot JSON's optional `map_texture` field tells the runner which Mapbox-rendered PNG to drop onto which named object. Naming convention: objects in the scene have semantic names (`diner_table_map_plane`, `war_table_surface`) so shots can target them.

`[LOCKED]` — map prop textures from Mapbox renders.

---

## 10. Render strategy

Three quality modes. Local handles preview; Verda handles final.

```
preview → Eevee, 64 samples, 800x450    — RTX 3070 Ti, ~3s/frame
draft   → Eevee, 256 samples, 1280x720  — RTX 3070 Ti or Verda L40S
full    → Cycles, 1024 samples, 1080p   — Verda B200, ~60-90s/frame
```

The render decision is hardware-aware:
- **All authoring work** happens at preview locally. Iteration speed dominates.
- **Batch finals** go to Verda. A 20-second clip at full quality on the local 3070 Ti would take ~30 minutes; on a B200 with frame parallelism, ~5 minutes wall-clock.
- **Cycles vs Eevee**: Eevee is good enough for ~80% of shots. Cycles when SSS, complex feather lighting, or volumetric haze (war-room cyan glow on consoles) matters.

Color grade lives in post (`lib/compositor.py`), not in Blender. Blender outputs neutral; the channel grade is applied by ffmpeg/python afterward, per mood. This means tuning the channel aesthetic doesn't require re-rendering frames — just re-running compositor.py.

`[LOCKED]` — three-mode system, post-render grade.

---

## 11. The Claude Code iteration loop for 3D

The user works on 3D with Claude Code in the loop. Critical to make this fast.

**Loop:**
1. User describes an edit ("make the brow tufts more asymmetric")
2. Claude Code edits a Python script (e.g., `scripts/edit_owl.py`)
3. Script runs Blender headless: edit applied, file saved, multi-angle preview rendered to `/tmp/`
4. Stats printed to stdout (vert count, shape key list, bone count, any errors)
5. Claude Code reads the PNGs (multimodal — Claude can see images), comments on what changed
6. User reviews same PNGs, gives natural-language feedback
7. Loop

**For this to work:**
- Preview render must be under 10 seconds. Eevee + workbench shading + 800x450 = 3-5 seconds on RTX 3070 Ti.
- Multi-angle output, not single-angle. The "QC sheet" pattern: front + 3/4 + side + isometric, composited into one image.
- Stats dump in stdout. Vert count, shape key inventory, bone hierarchy diff — text Claude Code can read directly without rendering.
- Determinism. Same edit script = same output, every time. No accidental randomness in seeds or modifiers.

This loop is described in detail in `verda_workflow.md`, but the design implication for the presenter system is: **preview render must be optimized for Claude Code iteration speed, not for human visual review quality.** A slightly worse-looking preview that renders in 3s beats a better preview that renders in 30s, by a wide margin.

`[LOCKED]` — preview render optimized for iteration speed.

---

## 12. Integration with other pipeline layers

```
              Orchestrator (n8n / langgraph)
                       │
       ┌───────────────┼────────────────┐
       │               │                │
       ▼               ▼                ▼
   Mapbox engine    Manim engine    B-roll layer    Presenter engine
                                                          │
                                                          ▼
                                          output/presenter/<shot_id>.mp4
                                                          │
                       ┌─────────────────────────────────┘
                       ▼
              ffmpeg compose
                       │
                       ▼
                final video
```

The presenter sits beside the three other content producers. Shared concerns:
- Asset marking (`.meta.json` for everything)
- Shot/scene ID conventions (stable, used across layers)
- Format flag (horizontal/vertical)
- Schema validation as CI gate
- Output naming convention

The presenter has the highest per-clip cost (rendering 3D character animation is heavier than rendering Manim or Mapbox). Episode design should be conscious — not every script beat needs the presenter on camera. The presenter is the periodic anchor between map/data segments and B-roll.

`[LOCKED]` — layered architecture, shared conventions.

---

## 13. Open questions

- **Voice quality long-term.** `fishaudio/s2-pro` is the launch choice. When does it stop being good enough? Probably re-evaluate at episode 10. Watch for: emotional range plateauing, audience comments about "AI voice."
- **Subtle character development over time.** Should the owl evolve (slightly different waistcoat in winter, new prop on the table, glasses with progressive wear)? Aesthetically appealing, technically annoying — every change needs to be tracked. Defer.
- **Audio-reactive idle motion.** Breathing rate matching script intensity, brow tension following narration tone? Possible with audio analysis driving shape key sliders. Probably overkill for launch. Re-evaluate if the owl ever feels "still" during heavy moments.
- **Performance capture for special shots.** A handful of episodes per year might warrant a single mocap shot for emotional payoff. Probably handled outside the standard pipeline, as a one-off custom shot. Not a system feature.
- **Twin owl / second character.** Recurring interlocutor for dialogue beats? Probably not — the solo-presenter format is cleaner and the owl works because it's *the* owl, not "an" owl. Possible variant character (different owl, different role) much later.
- **Render farm topology.** Multi-instance distributed rendering on Verda for very long clips? Possibly worth setting up if clips ever exceed ~30 seconds at full quality.
- **Style consistency across scenes.** If the diner and war-room scenes are graded differently, does the channel still feel unified? Yes — context-appropriate lighting matters more than uniformity. But the underlying owl-on-camera framing, focal length range, and gesture vocabulary stay consistent across scenes.
- **B-roll-style stock owl footage?** Could specialized AI generation produce owl footage matching the character? In principle yes (LoRA-trained model), in practice the rigged 3D owl is more controllable. Skip.

---

## 14. What we're not building

- Photoreal owl. The aesthetic is stylized; photoreal would be uncanny in combination with clothes and speech.
- Full-body animation system. The owl sits or stands behind a table; legs are rarely visible. Don't over-rig.
- Multiple owl variants. One owl, two scenes, optionally one variant scene Phase 5+.
- Custom shape key UI. Use Blender's native panel.
- Live performance capture. Wrong tool for the channel's aesthetic.
- Realistic feather physics. Stylized layered cards are sufficient.
- Audio recording booth pipeline. TTS is the voice; if it ever becomes recorded voice, that's a separate sub-project.

---

## 15. Decision log

| Decision | Section | Status |
|---|---|---|
| Owl as recurring brand mascot | §1 | LOCKED |
| Two scenes (diner + war table) | §2 | LOCKED (count), FLUID (third scene later) |
| Build owl custom, source everything else | §3 | LOCKED |
| Stylized realism, not photoreal | §4 | LOCKED |
| Body-first, clothes-second mesh | §4 | LOCKED |
| Asymmetric design language | §4 | LOCKED |
| Rig serves library, not hero rig | §5 | LOCKED |
| Eye convergence target | §5 | LOCKED |
| Additive shape key system | §6 | LOCKED |
| 15-20 hand-keyed gesture library | §7 | LOCKED (approach), FLUID (count) |
| Rhubarb + owl viseme mapping for lipsync | §8 | LOCKED |
| Cache visemes by audio hash | §8 | LOCKED |
| Mapbox frames as prop textures | §9 | LOCKED |
| Three-mode render (preview/draft/full) | §10 | LOCKED |
| Post-render color grading, not in Blender | §10 | LOCKED |
| Preview render optimized for Claude Code iteration | §11 | LOCKED |
| Integration via output/presenter/, shared orchestrator | §12 | LOCKED |
