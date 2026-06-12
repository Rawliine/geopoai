# W21 — Escape hatch: guarded custom-Manim path

Branch: `agents/w21-escape` · Depends on: W10.

## Goal
A caged pressure valve: when the component library can't express a needed
visual, a custom Manim scene can be authored (by the brain) — but it must
obey the brand, the contracts, and leave an audit trail. Recurring patterns
get promoted into real components; the hatch must never become a parallel
renderer.

## Allowlist
manim_renderer/escape_hatch/ · pipeline/render_manim.py (dispatch hook only,
≤15 lines) · scripts/manim/qa_escape.json (new)

## Read first
manim_renderer/escape_hatch/__init__.py + custom_scenes/ (current scaffold) ·
scene.py (how render_manim drives scenes) · theme/*.py · tools/tokens.py ·
docs/contracts/events.schema.json

## Checklist

### T1 — Input contract
Scene JSON `{ "renderer": "manim", "escape_hatch": { "file":
"escape_hatch/custom_scenes/<name>.py", "class": "<SceneClass>",
"reason": "<why components were insufficient>" } }` — `reason` mandatory.
Custom scene files live ONLY under custom_scenes/.

### T2 — Guard linter (escape_hatch/guard.py)
Static checks before render, hard-fail on violation:
- imports allowlist: manim, manim_renderer.theme, tools.tokens, math,
  numpy, json — nothing else (no os/sys/subprocess/requests/pathlib writes);
- no hex color literals (`#[0-9a-fA-F]{3,8}` outside comments) — colors via
  theme/tokens only;
- no font name literals — typography via theme only;
- class must subclass the project base scene (or a provided
  EscapeHatchScene base that wires theme + format + safe areas in).

### T3 — Sandboxed execution
Render in a subprocess with timeout (default 300s, param), workdir confined
to a temp dir, output contract identical to components: mp4 + events.json
(EscapeHatchScene base emits at least scene-start/end events; author may
emit more via a provided `self.emit(type, intensity)` helper) + meta.json
(reason, file hash, duration).

### T4 — Audit trail + promotion rule
Append every render to escape_hatch/usage_log.jsonl (timestamp, episode,
file, reason, hash). `escape_hatch/README.md`: the promotion rule — same
visual pattern used 3× → file an entry in plans/backlog: promote to
component; the hatch is for one-offs.

### T5 — QA
One real custom scene (e.g. a bespoke "incentive flywheel" diagram not
expressible with current components) passing guard + rendering on-brand;
one fixture that VIOLATES each guard rule with a test asserting rejection.

## Out of scope
LLM authoring of scenes (brain does that at W20's scenes stage) · new
components · registry changes.

## Acceptance
qa_escape.json renders via `pipeline/render.py`; guard violations all caught
in tests; usage_log entry written; events.json validates.
