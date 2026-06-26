# Escape hatch — guarded custom Manim path

A **caged pressure valve** for visuals the component library cannot express.
Custom scenes live only under `custom_scenes/`, pass a static guard linter
before every render, run in a sandboxed subprocess, and leave an audit trail.

## When to use

Use the hatch for **one-off** bespoke diagrams. If the same visual pattern
appears in **three or more** episodes, **promote it to a real component**
instead — file an entry in `plans/backlog/` describing the pattern and
proposed component action. The hatch must never become a parallel renderer.

## Scene JSON contract

```json
{
  "renderer": "manim",
  "format": "horizontal",
  "quality": "preview",
  "scene": { "duration": 8 },
  "escape_hatch": {
    "file": "escape_hatch/custom_scenes/my_scene.py",
    "class": "MyScene",
    "reason": "Why components were insufficient (mandatory)"
  }
}
```

Optional: `escape_hatch.timeout_s` (default 300).

## Authoring rules (enforced by `guard.py`)

- Subclass `EscapeHatchScene` from `manim_renderer.escape_hatch.base`.
- Imports: `manim`, `manim_renderer.theme`, `manim_renderer.escape_hatch`,
  `tools.tokens`, `math`, `numpy`, `json` only.
- **No** `os`, `sys`, `subprocess`, `requests`, `pathlib`, or other modules.
- **No** hex color literals — use `manim_renderer.theme.palette`.
- **No** font name literals — use `manim_renderer.theme.typography.FONTS`.
- Emit extra cues via `self.emit(type, intensity)`; scene start/end chapter
  events are automatic.

## Outputs

Same contract as component renders:

- `output/manim/<clip>.mp4`
- `output/manim/<clip>.events.json`
- `output/manim/<clip>.meta.json` (`reason`, `file_hash`, `duration`)

Every render appends one JSON line to `usage_log.jsonl` in this directory.

## Promotion rule

| Occurrences | Action |
|-------------|--------|
| 1–2 | Keep using the hatch; document `reason` in scene JSON |
| 3+ same pattern | File `plans/backlog/<component-name>.md` to promote to registry |

Review `usage_log.jsonl` periodically to spot promotion candidates.
