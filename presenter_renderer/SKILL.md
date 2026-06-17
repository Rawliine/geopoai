# SKILL.md — Authoring Presenter Shot JSON (stub)

The presenter renderer is **in progress** (`pipeline/render_presenter.py` is a
Phase 3 stub). This file is a placeholder so the layer carries the standard doc
trio; it will be fleshed out when the renderer lands.

The authoritative contract for a presenter shot is the JSON Schema:

- **`presenter_renderer/schema/presenter_schema.json`** — the enums in it
  (`scene`, `camera_preset`, `mood_preset`, `gesture`, `quality`, `format`) are
  the source of truth for what a valid shot may contain, and act as the CI gate.
- **`presenter_renderer/schema/validator.py`** — validates a shot against it.

Minimal shape (see the schema for the full, current field list):

```json
{
  "shot_id": "ep017_intro",
  "scene": "diner",
  "duration_seconds": 6,
  "camera_preset": "booth_medium",
  "mood_preset": "contemplative",
  "audio_path": "output/vo/ep017_intro.wav",
  "timeline": [
    { "at": 0.0, "gesture": "owl_idle_breathing", "loop": true },
    { "at": 2.5, "gesture": "owl_lean_in" }
  ]
}
```

Design and roadmap live in `presenter_renderer/AGENT.md`, `plan.md`, and
`recap.md`.
