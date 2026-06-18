# Agent dispatch prompts (Cursor Composer)

Copy **one block per agent** into a new Cursor Agent/Composer tab. Each block is
self-contained. The `.cursor/rules/agent-discipline.mdc` rules also load
automatically, but the blocks restate the load-bearing parts so nothing is
missed.

## Commit format — read this once

The prefix is a **conventional-commit type**, and the `Wxx.Ty` marker goes at
the **end** in parentheses. This is the one thing agents got wrong before.

- ✅ `feat(map): static neon border effect (W11.T1)`
- ✅ `fix(manim): close matrix label gap (W10.T2)`
- ✅ `docs(map): SKILL fragment for territory effects (W11.T8)`
- ❌ `W11.T1: static neon border effect`  ← never put the marker as the prefix

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. No `Co-authored-by`.
Never push — the operator merges and pushes.

## Dispatch order

- **W00, W01, W02 are merged.** Every Wave-1 lane below is unblocked now.
- Run **2–3 at a time** (review attention is the bottleneck).
- **Map lanes:** dispatch **W13 first** — it owns `core/runtime.js` and the
  `events.json` / `layout.json` emitters that W11, W12, and W22 attach to. Then
  W11 + W12 + W14 in parallel (disjoint files).
- **Wave 2:** W20 waits for all of Wave 1 merged; **W21 waits for W10**; **W22
  waits for W13**.

---

## W10 — Manim quality (fonts, layout fixes, emission, pacing, icons, images)

```text
/worktree Read plans/W10-manim-quality.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w10-manim (git checkout -b agents/w10-manim); if the worktree auto-named the branch, rename it with git branch -m agents/w10-manim. Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render or test needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item. Conventional-commit prefix with the lane/item marker at the END in parentheses — e.g. `fix(manim): close payoff-matrix label gap (W10.T2)`. Valid types: feat, fix, docs, refactor, test, chore. DO NOT use "W10.Ty" as the prefix. No Co-authored-by trailer. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY files in your allowlist (manim_renderer/ except escape_hatch/, scripts/manim/, pipeline/render_manim.py). No placeholders, no shortcuts — actually fix the font warning, actually render the QA scenes, paste acceptance output. If blocked or ambiguous, stop and report.

Context: fonts are provisioned to assets/font/ (singular) by tools/prepare_assets.py — load Barlow Condensed/Inter/etc. from there with manim.utils.register_font. You EMIT events.json + layout.json (W15/W16/W17 consume them) — match docs/contracts/{events,layout}.schema.json exactly. Read tokens via tools/tokens.load_tokens; never hardcode colors/fonts.
```

---

## W13 — Map camera, atmosphere, vertical format, emitters (DISPATCH FIRST among map lanes)

```text
/worktree Read plans/W13-map-camera-atmosphere.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w13-camera (git checkout -b agents/w13-camera); rename with git branch -m agents/w13-camera if auto-named. Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(map): idle camera drift + swoop easing (W13.T1)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W13.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md and skim W11/W12 so the emitter you build matches what they attach (fn.eventMeta). Touch ONLY your allowlist (map_renderer/runner.py, web/map.html, web/js/core/*, web/js/effects/{camera,atmosphere}.js, web/css/{base,atmosphere}.css, scripts/map/). No placeholders — vertical renders must actually be 1080x1920, emitters must produce schema-valid events.json/layout.json. Run acceptance in both realtime + deterministic modes; paste output.

Context: you own core/runtime.js + the GENERIC events/layout emitters that W11/W12/W22 rely on (they attach fn.eventMeta to their action fns; your emitter reads it, fallback type "label" intensity 0.4). map.html already has script tags for every effects module incl. stubs — DO NOT add/remove script tags. Safe areas + timing come from config/design_tokens.json.
```

---

## W11 — Map territory (border-neon, invasion advanceFront, morph, hatch, masked images)

```text
/worktree Read plans/W11-map-territory.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w11-territory (git checkout -b agents/w11-territory); rename with git branch -m agents/w11-territory if auto-named. Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(map): advanceFront invasion modeling (W11.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W11.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (web/js/effects/{fills,borders}.js, web/css/{fills,borders}.css, scripts/map/qa_territory.json, map_renderer/docs/fragments/W11.md). Read core/*.js and registry.js but DO NOT edit them — they belong to W13. No placeholders: advanceFront must work in BOTH realtime and deterministic (stepTo) modes, driven by runtime t, not wall clock. Run acceptance; paste frame screenshots/notes.

Context: attach `fn.eventMeta = {type, intensity}` to each registered action (W13's emitter reads it — do NOT modify registry.js). Effects must be token-driven (config/design_tokens.json) — no hardcoded hex. vendored turf + flubber are already loaded by map.html.
```

---

## W12 — Map flow + text (arrows, arcs, supply lines, leader labels, counters, title cards, stat boxes, icons)

```text
/worktree Read plans/W12-map-flow-text.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w12-flowtext (git checkout -b agents/w12-flowtext); rename with git branch -m agents/w12-flowtext if auto-named. Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(map): tapered military advance arrow (W12.T1)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W12.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (web/js/effects/{arrows,labels}.js, web/css/{arrows,labels}.css, scripts/map/qa_flowtext.json, map_renderer/docs/fragments/W12.md). Read core/*.js read-only; do NOT edit it (W13 owns it). No placeholders: counters must be deterministic-safe (value derived from runtime t). Run acceptance; paste screenshots/notes.

Context: attach fn.eventMeta to each action (W13's emitter reads it). Icons resolve from assets/icons/<pack>/, flags from circle-flags (provisioned via tools/prepare_assets.py). Token-driven styling only.
```

---

## W14 — Map data catalog (NE discovery + historical + year resolver)

```text
/worktree Read plans/W14-map-catalog.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w14-catalog (git checkout -b agents/w14-catalog); rename with git branch -m agents/w14-catalog if auto-named. Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(map): Natural Earth catalog discovery (W14.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W14.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (map_renderer/data_prep/, map_renderer/resolver.py, map_renderer/tests/test_catalog.py, map_renderer/docs/fragments/W14.md). No placeholders: --discover must actually hit the catalog and list real datasets; --add must actually download + process. READ each historical source's license during implementation and record commercial_ok honestly. Run acceptance end-to-end; paste output.

Context: the manifest is a lockfile — tooling writes it, humans don't hand-edit. Mirror broll/lib/asset_wrapper.py provenance discipline (mandatory license fields). The miss path must raise a typed exception carrying suggestions[] (W20's orchestrator depends on it).
```

---

## W18 — B-roll (env audit, PD sources, link ingest, claude_cli verifier, prompt eval)

```text
/worktree Read plans/W18-broll-expansion.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w18-broll (git checkout -b agents/w18-broll); rename with git branch -m agents/w18-broll if auto-named. Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`. If a fetch/test needs secrets, link .env: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(broll): DVIDS public-domain source (W18.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W18.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (broll/, pipeline/broll.py, .env.example, tests/test_broll_*.py). No placeholders: new sources must really fetch with mocked-HTTP tests; the reference ingest must really split + verify a committed test mp4. Run acceptance; paste output.

Context: the vision verifier DEFAULT backend is `claude_cli` (shells out to `claude -p` using the operator's Claude Code subscription — NO ANTHROPIC_API_KEY). Mark ANTHROPIC_API_KEY OPTIONAL in .env.example. PIXABAY_API_KEY is the one genuinely missing stock key — document it. Provenance for user-supplied links = license "user_provided".
```

---

## W19 — Infra GPU session manager (⚠️ spends real money on the live drill)

```text
/worktree Read plans/W19-infra-sessions.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w19-infra (git checkout -b agents/w19-infra); rename with git branch -m agents/w19-infra if auto-named. Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`. Terraform commands need .env sourced: set -a && source /home/rawline/GeoPoAI/.env && set +a

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(infra): generic GPU session manager (W19.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W19.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md AND infra/OPERATOR_RUNBOOK.md fully first. Touch ONLY your allowlist (pipeline/gpu_session.py, infra/sessions.json, infra/*.sh edits, infra/OPERATOR_RUNBOOK.md, tests/test_gpu_session.py). NEVER touch verda_volume.models or its prevent_destroy guard. No placeholders, but for the live drill use the CHEAPEST GPU tfvars and ALWAYS destroy the instance after. If a real terraform apply would be expensive/risky, do the mock-based tests in full and STOP before the live drill to report — let the operator run it.

Context: this is the one lane that costs money when tested. The whole point is auto up→health→use→auto-destroy with an idle watchdog + hard budget cap (the forgot-the-H100-overnight insurance). Make the models volume untouchable by construction from this tool.
```

---

## W15 — Captions (whisperX → ASS → occupancy-aware burn-in)

```text
/worktree Read plans/W15-captions.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w15-captions (git checkout -b agents/w15-captions); rename with git branch -m agents/w15-captions if auto-named. Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(captions): occupancy-aware ASS placement (W15.T4)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W15.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (composition/captions.py, tools/align_vo.py, tests/test_captions.py, requirements.txt for the whisperX/stable-ts line). No placeholders: actually install the aligner and run it on a committed sample wav; actually burn a 9:16 demo clip. Run acceptance; paste output + screenshots.

Context: develop against docs/contracts/fixtures/ (real layout.json arrives after W10/W13 merge — your build() must accept the schema shape now). Implement the frozen composition.captions.build(...) signature exactly. Captions are TRANSCRIPT (callouts are compression — never duplicate). All styling from config/design_tokens.json (safe_areas caption_band, typography).
```

---

## W16 — Automatic sound pass (events.json → SFX mix + bed + loudness)

```text
/worktree Read plans/W16-sound-pass.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w16-sound (git checkout -b agents/w16-sound); rename with git branch -m agents/w16-sound if auto-named. Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(sound): cooldown + density rules engine (W16.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W16.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (composition/sound.py, assets/sfx/palette.json curation, tests/test_sound.py). No placeholders: actually produce a mix.wav with audible whoosh + bed and measure -14 LUFS. Run acceptance; paste the loudnorm JSON.

Context: develop against docs/contracts/fixtures/events.min.json. Implement the frozen composition.sound.build(...) signature. SFX come from provisioned Kenney packs (assets/sfx/) — curate ≤15 files, replace TODO_CURATE markers. Restraint over spectacle (cooldowns, density cap). Determinism: same input → byte-identical cue list.
```

---

## W17 — Composition engine (assembly, transitions, grading, exports)

```text
/worktree Read plans/W17-composition-engine.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w17-compose (git checkout -b agents/w17-compose); rename with git branch -m agents/w17-compose if auto-named. Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(compose): whoosh motion-cut transition (W17.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W17.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (composition/{engine,transitions,export}.py, composition/README.md, pipeline/compose.py, tests/test_compose.py). Call captions.build / sound.build via the frozen stub signatures — do NOT implement their internals. No placeholders: produce a real playable final mp4 in BOTH export profiles from fixture clips. Run acceptance; paste output + boundary frame dumps.

Context: develop against docs/contracts/fixtures/compose.min.json + the frozen stub signatures (composition is W02's skeleton). Re-encode once at the end. nvenc with libx264 fallback (mirror map_renderer/runner.py detection — reimplement locally, don't cross-import).
```

---

## W20 — Orchestration (episode manifest, stages, QC) — WAIT for all Wave 1 merged

```text
/worktree Read plans/W20-orchestration.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w20-orchestration (git checkout -b agents/w20-orchestration); rename with git branch -m agents/w20-orchestration if auto-named. Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(orchestration): episode manifest + stage runner (W20.T1)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W20.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md and ALL of docs/contracts/*.schema.json first. Touch ONLY your allowlist (orchestration/, pipeline/orchestrate.py, config/show_bible.geopoai.json, tests/test_orchestration.py). No placeholders: the example episode must actually walk every stage to compose with stub clips; QC rules must actually fire on the deliberately-failing fixtures. Run acceptance; paste output.

Context: ZERO LLM API calls — every brain stage HALTS with an instruction + schema for Claude Code to author, then validate advances. Keep the brain interface swappable for future API. Zero geopolitics hardcoded in orchestration/ — everything genre-flavored reads from the show bible (a grep for "geopoli" in stages/ must hit nothing). Selective re-render via content hashing.
```

---

## W21 — Escape hatch (guarded custom-Manim) — WAIT for W10 merged

```text
/worktree Read plans/W21-escape-hatch.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w21-escape (git checkout -b agents/w21-escape); rename with git branch -m agents/w21-escape if auto-named. Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`.

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(manim): escape-hatch guard linter (W21.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W21.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (manim_renderer/escape_hatch/, pipeline/render_manim.py dispatch hook ≤15 lines, scripts/manim/qa_escape.json). No placeholders: the guard linter must actually reject the violating fixtures; the real custom scene must render on-brand. Run acceptance; paste output.

Context: this is a CAGED pressure valve. Guard must hard-fail on disallowed imports, hex literals, and font-name literals (colors/fonts via theme/tokens only). Sandboxed subprocess + timeout. Same output contract as components (mp4 + events.json + meta). Log every use to usage_log.jsonl.
```

---

## W22 — Map 3D models (three.js custom layer) — WAIT for W13 merged

```text
/worktree Read plans/W22-map-3d.md and execute it exactly, checklist items in order.

Branch: first action — create and switch to agents/w22-map3d (git checkout -b agents/w22-map3d); rename with git branch -m agents/w22-map3d if auto-named. Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. Link .env for renders if missing: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item. Conventional-commit prefix with the marker at the END — e.g. `feat(map): glTF model custom WebGL layer (W22.T2)`. Types: feat, fix, docs, refactor, test, chore. DO NOT use "W22.Ty" as the prefix. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (web/js/effects/models3d.js, web/vendor/ for three only, tools/prepare_assets.py + assets/manifest.json model-pack entry, scripts/map/qa_models.json, map_renderer/docs/fragments/W22.md). If you genuinely need a new <script> tag in map.html, STOP and report — the lead adds it (rule 3). No placeholders: models must really render and stay geo-anchored through camera moves, in BOTH realtime and deterministic modes. Run acceptance; paste screenshots.

Context: W13's emitter reads your fn.eventMeta (type "model", intensity 0.7). Add the CC0 low-poly model pack to assets/catalog.py (verify CC0, record license in manifest). Deterministic: model transforms derived purely from runtime t.
```
