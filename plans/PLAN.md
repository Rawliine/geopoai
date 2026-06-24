# GeoPoAI — Pre-Launch Master Plan

Team-lead model: Claude Code authored this plan and reviews/merges; lanes are
executed by an agent — Cursor Composer **or Claude Code** (e.g. W13 was executed
by Claude Code directly in-repo on its `agents/` branch). One lane = one spec
file = one git worktree (or in-repo branch) = one branch = one PR-sized diff.
Commit-per-checklist-item.

## Goal

Close the gap to genre-standard production value on the map engine (full
visual grammar incl. invasion-front modeling and 3D), bring the manim engine
to brand-quality, unify the brand (tokens: palette/fonts/timing/safe-areas),
build the composition layer (assembly + occupancy-aware captions + automatic
sound pass), expand b-roll (sources, link ingest, eval), automate GPU infra
sessions, and stand up the orchestration layer **without any LLM API** —
Claude Code acts as the brain at every authoring stage.

Out of scope for this plan (backlog): presenter-layer feature work, upload
automation, LLM-API brains, self-hosted LLM, show #2 bibles.

## Waves and dependency order

```
WAVE 0 (foundations — solo, no parallel work during W00)
  W00 map-refactor            (solo; everything else waits)
  W01 docs-normalization      ─┐ parallel after W00
  W02 tokens-contracts-assets ─┘

WAVE 1 (parallel lanes; all depend on W00+W02; W01 independent)
  W10 manim-quality
  W11 map-territory            (fills, invasion front, morph, hatch, masked images)
  W12 map-flow-text            (arrows, labels, counters, title cards, icons)
  W13 map-camera-atmosphere    (drift, ramps, fog, terrain, vertical, emission)
  W14 map-catalog              (NE discovery + historical catalogs + resolver)
  W15 captions                 (whisperX → ASS → occupancy-aware burn-in)
  W16 sound-pass               (events.json → SFX mix + bed + loudness)
  W17 composition-engine       (assembly, transitions, grading, exports)
  W18 broll-expansion          (keys, PD sources, link ingest, prompt eval)
  W19 infra-sessions           (generic GPU session manager + watchdogs)

WAVE 2 (parallel; depend on Wave 1 contracts being exercised)
  W20 orchestration            (episode manifest, stage runner, QC, publish)
  W21 escape-hatch             (guarded custom-Manim path)
  W22 map-3d                   (glTF models on map via three.js custom layer)

INTEGRATION (lead-driven, no lane file)
  End-to-end mini-episode: 2 map clips + 2 manim clips + 1 broll clip + a VO
  wav, driven through orchestrate.py with Claude Code as brain. Verifies:
  hash-based selective re-render, caption occupancy, sound pass, QC gates,
  both export formats.
  Also lead-driven here: docs sync — merge every <layer>/docs/fragments/*.md
  into that layer's SKILL.md, then delete the fragments.
```

## Lane table

| Lane | Branch | Allowlist root(s) | Depends on |
|---|---|---|---|
| W00 | agents/w00-map-refactor | repo-wide moves (see file) | — |
| W01 | agents/w01-docs | *.md, docs/ | W00 |
| W02 | agents/w02-tokens | config/, docs/contracts/, tools/, assets/, composition/ (stubs), manim_renderer/theme/ | W00 |
| W10 | agents/w10-manim | manim_renderer/ (excl. escape_hatch/), scripts/manim/ | W02 |
| W11 | agents/w11-territory | map_renderer/web/js/effects/{fills,borders}.js, web/css/{fills,borders}.css | W00, W02 |
| W12 | agents/w12-flowtext | map_renderer/web/js/effects/{arrows,labels}.js, web/css/{arrows,labels}.css | W00, W02 |
| W13 | agents/w13-camera | map_renderer/{runner.py, web/map.html, web/js/core/, web/js/effects/{camera,atmosphere}.js, web/css/{base,atmosphere}.css}, scripts/map/ | W00, W02 |
| W14 | agents/w14-catalog | map_renderer/data_prep/, map_renderer/resolver.py | W00 |
| W15 | agents/w15-captions | composition/captions.py, tools/align_vo.py | W02 |
| W16 | agents/w16-sound | composition/sound.py | W02 |
| W17 | agents/w17-compose | composition/{engine,transitions,export}.py, pipeline/compose.py | W02 |
| W18 | agents/w18-broll | broll/, pipeline/broll.py, .env.example | W02 |
| W19 | agents/w19-infra | infra/, pipeline/gpu_session.py | — |
| W20 | agents/w20-orchestration | orchestration/, pipeline/orchestrate.py, config/show_bible.*.json | Wave 1 |
| W21 | agents/w21-escape | manim_renderer/escape_hatch/ | W10 |
| W22 | agents/w22-map3d | map_renderer/web/js/effects/models3d.js, web/vendor/ (three only) | W13 |

Within a wave, allowlists are disjoint by construction. Two lanes may never
hold the same file. W00 pre-creates every module file and `map.html` script
tag so Wave-1 map lanes never edit shared files.

## Standing rules (mirrored in .cursor/rules/agent-discipline.mdc)

- One commit per checklist item, in three parts: (1) subject
  `<type>(<scope>): <summary>` with NO marker; (2) a body of bullet points
  grouped by file (a `<path>:` header, then `- ` bullets of what changed); (3)
  the `(W<lane>.T<item>)` marker ALONE on the final line. Never use the marker
  as the prefix or glue it to the subject. Types: feat, fix, docs, refactor,
  test, chore. (Full example in `plans/AGENT_PROMPTS.md`.)
- Acceptance commands run before "done"; output goes in the report.
- `docs/contracts/` and `config/design_tokens.json` are frozen — changes only
  via the lead (Claude Code), never inside a lane.
- No hardcoded colors/fonts/timing anywhere: tokens only.
- Effects animate **in and out**: every visual effect has a deliberate,
  token-timed entrance and exit (use `timing` tokens incl. `exit_ratio`); never
  an instant pop unless the scene explicitly asks for a cut. Any effect that can
  persist on screen ships a `remove*`/`hide*` action so it can leave cleanly.
  "Static/instant" is not a substitute for a designed entrance — spell out the
  in/out behavior in the lane file so it can't be skipped.
- Assets only via `tools/prepare_assets.py` + `assets/manifest.json` (license
  field mandatory).
- Out-of-scope refactors forbidden.
- Any lane adding user-facing surface (actions, effects, params, CLI flags)
  documents it in `<layer>/docs/fragments/<lane>.md` inside its allowlist.
  SKILL.md files are merged from fragments by the lead at integration —
  feature lanes never edit SKILL.md directly.

## Dispatch protocol (operator)

```bash
git worktree add ../geopoai-w11 -b agents/w11-territory
ln -s ~/GeoPoAI/.env ../geopoai-w11/.env        # lanes that render need it
cursor ../geopoai-w11
# Composer prompt:
#   Read plans/W11-map-territory.md and execute it exactly, checklist items
#   in order. One commit per item.
```

A lane may instead be executed by **Claude Code** directly (its own
`agents/<lane-id>` branch in the repo, same prompt and discipline) — as W13 was.
When Claude Code is the executor and you (the user) are the lead, you may have it
merge/push at the end; the "executor never touches GitHub" rule below applies to
the *executor role*, not to lead-directed merges.

Review: run the lane's acceptance yourself, read commits one by one, then
have Claude Code `/code-review` the branch. Merge serially:

```bash
git merge agents/w11-territory
git worktree remove ../geopoai-w11 && git branch -d agents/w11-territory
```

Suggested concurrency: 2–3 lanes at once. Suggested wave-1 start order:
W13 + W10 + W18 first (W13 lands the emission machinery other lanes' outputs
get verified against; W10/W18 are independent), then W11 + W12 + W14, then
W15 + W16 + W17, then W19.

## Definition of done (plan-wide)

1. Every lane merged, acceptance green.
2. Integration mini-episode renders end-to-end in both formats with captions,
   SFX, grading, and QC report.
3. `python pipeline/render.py` works for every scene JSON in `scripts/`.
4. CLAUDE.md/README accurately describe the repo (W01) and a fresh clone can
   self-provision maps + assets with two commands.

## Backlog (explicitly deferred, do not implement)

Presenter integration beyond the events/tokens contract · platform upload
automation · API-driven brains in orchestration · self-hosted LLM · second
show bible · occupancy v2 (saliency-aware) · fine-tuned CLIP verifier.
