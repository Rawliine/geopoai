# Agent dispatch prompts (Cursor Composer)

Copy **one block per agent** into a new Cursor Agent/Composer tab. Each block is
self-contained. The `.cursor/rules/agent-discipline.mdc` rules also load
automatically, but the blocks restate the load-bearing parts so nothing is
missed.

## Commit format — read this once

Every commit message has **THREE parts**:

1. **Subject** — a conventional-commit line with **NO marker**:
   `<type>(<scope>): <summary>`
2. **Body** — bullet points **grouped by file**: one `<path>:` header per file
   you touched, then `- ` bullets describing what changed in that file.
3. **Marker** — the `(Wxx.Ty)` lane/item marker **alone on the final line**,
   after the body (one blank line above it).

Full example (write it to a file and `git commit -F msg.txt` — the body is
multi-line, so a single `-m` won't do):

```
feat(map): static neon border effect

map_renderer/web/js/effects/borders.js:
- border-neon: layered stroke (core + drop-shadow halo), role-driven, no @keyframes
- entrance fade-in <= 0.4s, then fully static
map_renderer/web/css/borders.css:
- .border-neon classes; halo blur from --glow-* tokens

(W11.T1)
```

- ✅ subject `feat(map): static neon border effect`, then the per-file body, then `(W11.T1)` alone on the last line
- ❌ `feat(map): static neon border effect (W11.T1)`  ← marker glued to the subject / no body
- ❌ `W11.T1: static neon border effect`              ← marker used as the prefix

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Always include the
per-file bullet body — no bare one-line commits. No `Co-authored-by`. Never
push — the operator merges and pushes.

## Branch setup — read this once

The operator opens a worktree **before** the first prompt. Common cases:

| How opened | Folder example | Branch you may see |
|------------|----------------|-------------------|
| `git worktree add <path> -b agents/<lane-id>` | `geopoai-w18` | `agents/w18-broll` ✓ |
| **Cursor “create worktree”** | `wk9n`, `.cursor/worktrees/…` | `cursor/feb013b7` ← **normal** |

**Only the git branch name matters** — not the folder name. Each lane prompt
below includes a `Branch (first action)` block with the **exact target branch**.

The agent **never** runs `git worktree` / `git worktree add`.

**Decision table** (target = `agents/<lane-id>` from your lane prompt):

| `git branch --show-current` | Action |
|-----------------------------|--------|
| already `agents/<lane-id>` | continue |
| `cursor/*` or any other feature branch | `git branch -m agents/<lane-id>` — **rename only** |
| `main` | `git checkout -b agents/<lane-id>` |

**Never** `git checkout -b agents/<lane-id>` when already on a feature branch
(including `cursor/*`). That leaves an orphan `cursor/<hash>` ref next to your
real lane branch and causes “two branch names” confusion.

Never commit on `main`.

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
Read plans/W10-manim-quality.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w10-manim. Run `git branch --show-current`.
  • agents/w10-manim → continue.
  • main → `git checkout -b agents/w10-manim`.
  • cursor/* or anything else → `git branch -m agents/w10-manim` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render or test needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `fix(manim): close payoff-matrix label gap` (NO marker), then a per-file bullet body, then `(W10.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY files in your allowlist (manim_renderer/ except escape_hatch/, scripts/manim/, pipeline/render_manim.py). No placeholders, no shortcuts — actually fix the font warning, actually render the QA scenes, paste acceptance output. If blocked or ambiguous, stop and report.

Context: fonts are provisioned to assets/font/ (singular) by tools/prepare_assets.py — load Barlow Condensed/Inter/etc. from there with manim.utils.register_font. You EMIT events.json + layout.json (W15/W16/W17 consume them) — match docs/contracts/{events,layout}.schema.json exactly. Read tokens via tools/tokens.load_tokens; never hardcode colors/fonts.
```

---

## W13 — Map camera, atmosphere, vertical format, emitters (DISPATCH FIRST among map lanes)

```text
Read plans/W13-map-camera-atmosphere.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w13-camera. Run `git branch --show-current`.
  • agents/w13-camera → continue.
  • main → `git checkout -b agents/w13-camera`.
  • cursor/* or anything else → `git branch -m agents/w13-camera` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(map): idle camera drift + swoop easing` (NO marker), then a per-file bullet body, then `(W13.T1)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md and skim W11/W12 so the emitter you build matches what they attach (fn.eventMeta). Touch ONLY your allowlist (map_renderer/runner.py, web/map.html, web/js/core/*, web/js/effects/{camera,atmosphere}.js, web/css/{base,atmosphere}.css, scripts/map/). No placeholders — vertical renders must actually be 1080x1920, emitters must produce schema-valid events.json/layout.json. Run acceptance in both realtime + deterministic modes; paste output.

Context: you own core/runtime.js + the GENERIC events/layout emitters that W11/W12/W22 rely on (they attach fn.eventMeta to their action fns; your emitter reads it, fallback type "label" intensity 0.4). map.html already has script tags for every effects module incl. stubs — DO NOT add/remove script tags. Safe areas + timing come from config/design_tokens.json.
```

---

## W11 — Map territory (border-neon, invasion advanceFront, morph, hatch, masked images)

```text
Read plans/W11-map-territory.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w11-territory. Run `git branch --show-current`.
  • agents/w11-territory → continue.
  • main → `git checkout -b agents/w11-territory`.
  • cursor/* or anything else → `git branch -m agents/w11-territory` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(map): advanceFront invasion modeling` (NO marker), then a per-file bullet body, then `(W11.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (web/js/effects/{fills,borders}.js, web/css/{fills,borders}.css, scripts/map/qa_territory.json, map_renderer/docs/fragments/W11.md). Read core/*.js and registry.js but DO NOT edit them — they belong to W13. No placeholders: advanceFront must work in BOTH realtime and deterministic (stepTo) modes, driven by runtime t, not wall clock. Run acceptance; paste frame screenshots/notes.

Context: attach `fn.eventMeta = {type, intensity}` to each registered action (W13's emitter reads it — do NOT modify registry.js). Effects must be token-driven (config/design_tokens.json) — no hardcoded hex. vendored turf + flubber are already loaded by map.html.
```

---

## W12 — Map flow + text (arrows, arcs, supply lines, leader labels, counters, title cards, stat boxes, icons)

```text
Read plans/W12-map-flow-text.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w12-flowtext. Run `git branch --show-current`.
  • agents/w12-flowtext → continue.
  • main → `git checkout -b agents/w12-flowtext`.
  • cursor/* or anything else → `git branch -m agents/w12-flowtext` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. If a render needs secrets and .env is missing here, link it: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(map): tapered military advance arrow` (NO marker), then a per-file bullet body, then `(W12.T1)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (web/js/effects/{arrows,labels}.js, web/css/{arrows,labels}.css, scripts/map/qa_flowtext.json, map_renderer/docs/fragments/W12.md). Read core/*.js read-only; do NOT edit it (W13 owns it). No placeholders: counters must be deterministic-safe (value derived from runtime t). Run acceptance; paste screenshots/notes.

Context: attach fn.eventMeta to each action (W13's emitter reads it). Icons resolve from assets/icons/<pack>/, flags from circle-flags (provisioned via tools/prepare_assets.py). Token-driven styling only.
```

---

## W14 — Map data catalog (NE discovery + historical + year resolver)

```text
Read plans/W14-map-catalog.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w14-catalog. Run `git branch --show-current`.
  • agents/w14-catalog → continue.
  • main → `git checkout -b agents/w14-catalog`.
  • cursor/* or anything else → `git branch -m agents/w14-catalog` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(map): Natural Earth catalog discovery` (NO marker), then a per-file bullet body, then `(W14.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (map_renderer/data_prep/, map_renderer/resolver.py, map_renderer/tests/test_catalog.py, map_renderer/docs/fragments/W14.md). No placeholders: --discover must actually hit the catalog and list real datasets; --add must actually download + process. READ each historical source's license during implementation and record commercial_ok honestly. Run acceptance end-to-end; paste output.

Context: the manifest is a lockfile — tooling writes it, humans don't hand-edit. Mirror broll/lib/asset_wrapper.py provenance discipline (mandatory license fields). The miss path must raise a typed exception carrying suggestions[] (W20's orchestrator depends on it).
```

---

## W18 — B-roll (env audit, PD sources, link ingest, claude_cli verifier, prompt eval)

```text
Read plans/W18-broll-expansion.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w18-broll. Run `git branch --show-current`.
  • agents/w18-broll → continue.
  • main → `git checkout -b agents/w18-broll`.
  • cursor/* or anything else → `git branch -m agents/w18-broll` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`. If a fetch/test needs secrets, link .env: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(broll): DVIDS public-domain source` (NO marker), then a per-file bullet body, then `(W18.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (broll/, pipeline/broll.py, .env.example, tests/test_broll_*.py). No placeholders: new sources must really fetch with mocked-HTTP tests; the reference ingest must really split + verify a committed test mp4. Run acceptance; paste output.

Context: the vision verifier DEFAULT backend is `claude_cli` (shells out to `claude -p` using the operator's Claude Code subscription — NO ANTHROPIC_API_KEY). Mark ANTHROPIC_API_KEY OPTIONAL in .env.example. PIXABAY_API_KEY is the one genuinely missing stock key — document it. Provenance for user-supplied links = license "user_provided".
```

---

## W19 — Infra GPU session manager (⚠️ spends real money on the live drill)

```text
Read plans/W19-infra-sessions.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w19-infra. Run `git branch --show-current`.
  • agents/w19-infra → continue.
  • main → `git checkout -b agents/w19-infra`.
  • cursor/* or anything else → `git branch -m agents/w19-infra` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`. Terraform commands need .env sourced: set -a && source /home/rawline/GeoPoAI/.env && set +a

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(infra): generic GPU session manager` (NO marker), then a per-file bullet body, then `(W19.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md AND infra/OPERATOR_RUNBOOK.md fully first. Touch ONLY your allowlist (pipeline/gpu_session.py, infra/sessions.json, infra/*.sh edits, infra/OPERATOR_RUNBOOK.md, tests/test_gpu_session.py). NEVER touch verda_volume.models or its prevent_destroy guard. No placeholders, but for the live drill use the CHEAPEST GPU tfvars and ALWAYS destroy the instance after. If a real terraform apply would be expensive/risky, do the mock-based tests in full and STOP before the live drill to report — let the operator run it.

Context: this is the one lane that costs money when tested. The whole point is auto up→health→use→auto-destroy with an idle watchdog + hard budget cap (the forgot-the-H100-overnight insurance). Make the models volume untouchable by construction from this tool.
```

---

## W15 — Captions (whisperX → ASS → occupancy-aware burn-in)

```text
Read plans/W15-captions.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w15-captions. Run `git branch --show-current`.
  • agents/w15-captions → continue.
  • main → `git checkout -b agents/w15-captions`.
  • cursor/* or anything else → `git branch -m agents/w15-captions` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(captions): occupancy-aware ASS placement` (NO marker), then a per-file bullet body, then `(W15.T4)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (composition/captions.py, tools/align_vo.py, tests/test_captions.py, requirements.txt for the whisperX/stable-ts line). No placeholders: actually install the aligner and run it on a committed sample wav; actually burn a 9:16 demo clip. Run acceptance; paste output + screenshots.

Context: develop against docs/contracts/fixtures/ (real layout.json arrives after W10/W13 merge — your build() must accept the schema shape now). Implement the frozen composition.captions.build(...) signature exactly. Captions are TRANSCRIPT (callouts are compression — never duplicate). All styling from config/design_tokens.json (safe_areas caption_band, typography).
```

---

## W16 — Automatic sound pass (events.json → SFX mix + bed + loudness)

```text
Read plans/W16-sound-pass.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w16-sound. Run `git branch --show-current`.
  • agents/w16-sound → continue.
  • main → `git checkout -b agents/w16-sound`.
  • cursor/* or anything else → `git branch -m agents/w16-sound` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(sound): cooldown + density rules engine` (NO marker), then a per-file bullet body, then `(W16.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (composition/sound.py, assets/sfx/palette.json curation, tests/test_sound.py). No placeholders: actually produce a mix.wav with audible whoosh + bed and measure -14 LUFS. Run acceptance; paste the loudnorm JSON.

Context: develop against docs/contracts/fixtures/events.min.json. Implement the frozen composition.sound.build(...) signature. SFX come from provisioned Kenney packs (assets/sfx/) — curate ≤15 files, replace TODO_CURATE markers. Restraint over spectacle (cooldowns, density cap). Determinism: same input → byte-identical cue list.
```

---

## W17 — Composition engine (assembly, transitions, grading, exports)

```text
Read plans/W17-composition-engine.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w17-compose. Run `git branch --show-current`.
  • agents/w17-compose → continue.
  • main → `git checkout -b agents/w17-compose`.
  • cursor/* or anything else → `git branch -m agents/w17-compose` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(compose): whoosh motion-cut transition` (NO marker), then a per-file bullet body, then `(W17.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (composition/{engine,transitions,export}.py, composition/README.md, pipeline/compose.py, tests/test_compose.py). Call captions.build / sound.build via the frozen stub signatures — do NOT implement their internals. No placeholders: produce a real playable final mp4 in BOTH export profiles from fixture clips. Run acceptance; paste output + boundary frame dumps.

Context: develop against docs/contracts/fixtures/compose.min.json + the frozen stub signatures (composition is W02's skeleton). Re-encode once at the end. nvenc with libx264 fallback (mirror map_renderer/runner.py detection — reimplement locally, don't cross-import).
```

---

## W20 — Orchestration (episode manifest, stages, QC) — WAIT for all Wave 1 merged

```text
Read plans/W20-orchestration.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w20-orchestration. Run `git branch --show-current`.
  • agents/w20-orchestration → continue.
  • main → `git checkout -b agents/w20-orchestration`.
  • cursor/* or anything else → `git branch -m agents/w20-orchestration` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/test command with `conda run -n geopo`.

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(orchestration): episode manifest + stage runner` (NO marker), then a per-file bullet body, then `(W20.T1)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md and ALL of docs/contracts/*.schema.json first. Touch ONLY your allowlist (orchestration/, pipeline/orchestrate.py, config/show_bible.geopoai.json, tests/test_orchestration.py). No placeholders: the example episode must actually walk every stage to compose with stub clips; QC rules must actually fire on the deliberately-failing fixtures. Run acceptance; paste output.

Context: ZERO LLM API calls — every brain stage HALTS with an instruction + schema for Claude Code to author, then validate advances. Keep the brain interface swappable for future API. Zero geopolitics hardcoded in orchestration/ — everything genre-flavored reads from the show bible (a grep for "geopoli" in stages/ must hit nothing). Selective re-render via content hashing.
```

---

## W21 — Escape hatch (guarded custom-Manim) — WAIT for W10 merged

```text
Read plans/W21-escape-hatch.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w21-escape. Run `git branch --show-current`.
  • agents/w21-escape → continue.
  • main → `git checkout -b agents/w21-escape`.
  • cursor/* or anything else → `git branch -m agents/w21-escape` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`.

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(manim): escape-hatch guard linter` (NO marker), then a per-file bullet body, then `(W21.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (manim_renderer/escape_hatch/, pipeline/render_manim.py dispatch hook ≤15 lines, scripts/manim/qa_escape.json). No placeholders: the guard linter must actually reject the violating fixtures; the real custom scene must render on-brand. Run acceptance; paste output.

Context: this is a CAGED pressure valve. Guard must hard-fail on disallowed imports, hex literals, and font-name literals (colors/fonts via theme/tokens only). Sandboxed subprocess + timeout. Same output contract as components (mp4 + events.json + meta). Log every use to usage_log.jsonl.
```

---

## W22 — Map 3D models (three.js custom layer) — WAIT for W13 merged

```text
Read plans/W22-map-3d.md and execute it exactly, checklist items in order.

Branch (first action): target agents/w22-map3d. Run `git branch --show-current`.
  • agents/w22-map3d → continue.
  • main → `git checkout -b agents/w22-map3d`.
  • cursor/* or anything else → `git branch -m agents/w22-map3d` (rename ONLY; never checkout -b).
  Do not run git worktree. Worktree folder name is irrelevant.
Never work on main.

Env: prefix every Python/render/test command with `conda run -n geopo`. Link .env for renders if missing: ln -sf /home/rawline/GeoPoAI/.env ./.env

Commits: ONE per checklist item, in the 3-part format from "Commit format" above — subject `feat(map): glTF model custom WebGL layer` (NO marker), then a per-file bullet body, then `(W22.T2)` alone on the final line. Types: feat, fix, docs, refactor, test, chore. NEVER use the marker as the prefix or glue it to the subject. No Co-authored-by. Do NOT push.

Discipline: read plans/PLAN.md first. Touch ONLY your allowlist (web/js/effects/models3d.js, web/vendor/ for three only, tools/prepare_assets.py + assets/manifest.json model-pack entry, scripts/map/qa_models.json, map_renderer/docs/fragments/W22.md). If you genuinely need a new <script> tag in map.html, STOP and report — the lead adds it (rule 3). No placeholders: models must really render and stay geo-anchored through camera moves, in BOTH realtime and deterministic modes. Run acceptance; paste screenshots.

Context: W13's emitter reads your fn.eventMeta (type "model", intensity 0.7). Add the CC0 low-poly model pack to assets/catalog.py (verify CC0, record license in manifest). Deterministic: model transforms derived purely from runtime t.
```

