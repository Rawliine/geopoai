# W25 — Manim media component: fitted image/video box (no stretch)

Branch: `agents/w25-manim-media` · Depends on: W10 (manim live, merged) — runs in
parallel with W24/W26/W27.

## Goal
A proper **media component** for manim scenes: a layout-sized **box** that displays
an image **or** a video, scaled to **fit inside without stretching** (object-fit:
contain → letterboxed), reworking the existing `ImageCard`
(`components/narrative/image_card.py`, "works but not great"). The composer / LLM
targets it for any `manim_media` input. Tokenized styling, in/out animation, optional
caption + attribution chip.

## Allowlist
`manim_renderer/components/` (new `media_frame.py`; `image_card.py` may be
superseded/aliased) · `manim_renderer/registry.py` · `manim_renderer/schema/`
(action + params) · `manim_renderer/theme/` (media tokens) ·
`manim_renderer/docs/fragments/w25-manim-media.md` (new) ·
`manim_renderer/tests/` · `scripts/manim/`

## Read first
`manim_renderer/components/narrative/image_card.py` (Ken Burns + attribution chip
to reuse) · `components/base.py` · `registry.py` · `schema/scene_schema.json` +
the validator · `theme/` (no raw values rule) · `manim_renderer/docs/SKILL.md`

## Checklist

### T1 — MediaFrame component (contain-fit box)
`components/media_frame.py`: a box sized by its layout slot rect; renders an image
scaled to **contain** (letterbox bars from a token color), never stretched; border /
corner-radius / padding from theme tokens. Entrance + exit per `timing` tokens
(never an instant pop). Optional caption line + attribution chip (reuse ImageCard's).

### T2 — Video inside the box
Support a video `src` played within the same fitted box (Manim video display),
duration-aware, deterministic under frame-stepping; same contain-fit + letterbox.
Image vs video auto-detected by extension (override via param).

### T3 — Registry + schema action
`showMedia` action → MediaFrame; schema params `{ id, src, fit?: "contain"|"cover",
caption?, attribution?, ken_burns?: bool }`; validator rejects raw coords (keep the
no-coordinates rule) and unknown fit. A `removeMedia`/`hideMedia` for clean exit.

### T4 — Tokens
Letterbox bg, frame border, padding, chip styling all from `theme/` — zero hardcoded
hex/px. Add the media tokens to the theme if missing.

### T5 — Supersede ImageCard
Migrate ImageCard's behavior into MediaFrame (Ken Burns as an opt-in flag); keep
`showImageCard` working as a thin alias so existing scenes don't break.

### T6 — Tests + fragment + demo
Component test (image + video, contain math, both formats), one golden frame,
`docs/fragments/w25-manim-media.md` (action surface), a `scripts/manim/` demo scene.

## Out of scope
Orchestration / input routing (W20) · sourcing media (provided by W20 inputs) ·
map media (W26) · escape-hatch.

## Acceptance
`showMedia` renders a portrait and a landscape image **and** a video, each fit-inside
its box without stretching, in horizontal + vertical; validator green; golden frame +
`pytest manim_renderer/tests/...` green.
