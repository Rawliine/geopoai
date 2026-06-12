# W01 — Documentation normalization

Branch: `agents/w01-docs` · Depends on: W00 merged. May run parallel to W02.

## Goal
Every layer carries the same doc trio — `AGENT.md` (working rules),
`SKILL.md` (JSON authoring guide), `recap.md` (decisions + why). Root
CLAUDE.md becomes an accurate thin router. Stale/dupe files archived.
`broll/recap(1).md` is the quality bar for recap files.

## Allowlist
All `*.md` files repo-wide, `docs/` (new), file renames of md files only.

## Checklist

### T1 — De-junk file names
- `broll/AGENT(1).md` → `broll/AGENT.md`; `plan(1).md` → `plan.md`;
  `recap(1).md` → `recap.md` (no name collisions exist — verify first).
- `infra/verda_workflow(2).md` → merge anything not already in
  `infra/OPERATOR_RUNBOOK.md` into it, then archive the original.
- `manim_renderer/manim md files/` → `manim_renderer/docs/` (git mv all four).
- `scripts/manim/_skill.md` → `manim_renderer/docs/SKILL.md` (leave a one-line
  pointer file at the old path since scene authors look there).
- `broll/HANDOFF_PHASE_*.md` → `docs/archive/broll/`.

### T2 — Root CLAUDE.md rewrite (router, ~120 lines max)
Must cover: the four renderers (map_renderer, manim_renderer, broll,
presenter_renderer) + infra + composition + orchestration (mark the last two
as "in progress, see plans/"), the unified dispatcher `pipeline/render.py`,
where each layer's docs live, the design-token rule (no hardcoded visual
constants), the asset-manifest rule, and the plans/ workflow. Every command
in it must be copy-paste runnable — test each one. Remove all stale paths
(e.g. old `pipeline/prepare_maps.py` reference, old `renderer/` paths).

### T3 — README refresh
Update paths post-W00, add composition/orchestration sections (status:
being built, link plans/PLAN.md), keep the engine docs accurate.

### T4 — Per-layer trios
- `map_renderer/docs/SKILL.md`: rewrite from the moved map_animation_skill.md —
  verify every action/effect it documents against `web/js/effects/*.js`
  registrations; flag (don't invent) anything undocumented.
- `map_renderer/docs/AGENT.md` + `recap.md`: write fresh; recap records the
  W00 restructure decisions and the country-data versioning rationale
  (pull from git history + CLAUDE.md).
- `manim_renderer/docs/`: AGENT/recap exist post-T1 — verify their claims
  against registry.py and scene.py; fix drift.
- `broll/`: trio exists — verify AGENT.md decision matrix matches
  `broll/lib/decision.py`; fix drift.
- `presenter_renderer/`: has AGENT/plan/recap — leave content, just add a
  SKILL.md stub pointing at its schema.
- `infra/`: keep README + OPERATOR_RUNBOOK as the pair; add 5-line AGENT.md
  pointing to them and warning about `destroy_comfyui_instance.sh` vs bare
  destroy.

### T5 — Link check
Script-or-grep every relative md link and path mention in all md files;
fix dead ones. List the fixes in the report.

## Out of scope
Code changes of any kind. plans/ files. .cursor/rules.

## Acceptance
No `(1)`/`(2)` filenames remain; `manim md files/` gone; CLAUDE.md commands
all run; link check clean.
