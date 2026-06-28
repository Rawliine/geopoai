# Orchestration (W20)

The episode factory as a **staged state machine** over one persistent artifact,
`episodes/<id>/episode.json` (schema: `docs/contracts/episode.schema.json`). The
manifest stays schema-valid at every transition. This README is the layer's
SKILL equivalent.

## CLI

```bash
python pipeline/orchestrate.py new <show> <episode_id> [--format ...] [--brain ...] [--inputs f.json]
python pipeline/orchestrate.py status   <episode_id>
python pipeline/orchestrate.py next      <episode_id> [--brain <name>]
python pipeline/orchestrate.py validate  <stage> <episode_id>
python pipeline/orchestrate.py run       <stage> <episode_id> [--brain <name>]
python pipeline/orchestrate.py qc        <episode_id>
python pipeline/orchestrate.py invalidate <stage|clip_id> <episode_id>
```

`--brain` overrides the episode's brain for one command (debugging). `next`
returns exit code **3** when a brain stage stops at `awaiting_brain`.

## Stage sequence

`ingest → angle → script → storyboard → scenes → voice → render → compose → qc → publish`

| Stage | Kind | Does |
|---|---|---|
| `ingest` | mechanical | `inputs[]` → `evidence[]` (content) + `media_pool[]` (media), routed by `use`. Offline. |
| `angle` | **brain** | Chosen angle, incentive structure, hook (familiar_schema + broken_variable). |
| `script` | **brain** | VO `beats[]` with emphasis; factual beats cite evidence; reading-time sanity. |
| `storyboard` | **brain** | Beats → clips (renderer, duration, scene_ref, media_ref). Validates durations ≈ script, max consecutive renderer, every media item placed once. |
| `scenes` | **brain** | Per-clip scene JSONs → `scenes/`; validated per renderer. |
| `voice` | mechanical | Verify `vo.wav` is present (S2-pro TTS later). |
| `render` | mechanical | Dispatch each clip; content-hash skip (scene + renderer version). |
| `compose` | mechanical | Build the compose spec (transitions, caption policy, `map_region`→`media_overlays`) → `pipeline/compose.py`. |
| `qc` | mechanical | callout-duplication, pacing, caption collisions, loudness, clip integrity → `qc_report.md`; failures block. |
| `publish` | **brain** | Per-platform metadata + thumbnail brief (no uploads); platform-limit checks. |

## The brain protocol (W24)

The brain is chosen **once per episode** via `episode.json.brain` (bible default
when absent); stages never know which ran. For each brain stage the runner:

1. If `stages/<stage>/artifact.json` already exists → validate (schema + stage
   checks) → merge → `done`. (Idempotent; also how `halt` resumes.)
2. Else resolve the brain (`brains.select_brain`) and `validate_and_repair`:
   - `halt` writes `instruction.md` + `schema.json` to the stage dir and stops at
     `awaiting_brain`; the operator authors `artifact.json`, then re-runs.
   - `claude-cli` / `gemini-cli` / `api` author + validate inline.

## Manifest lifecycle

`new` seeds a fresh manifest (bootstrap fields + every stage `pending`). Each
`run`/`next` flips a stage `pending → running/awaiting_brain → done | failed` and
records the artifact path + `hash`. `invalidate <clip_id>` drops that clip's
record and flips `render`+downstream to `pending` (sibling clips keep their hashes
→ skip at render); `invalidate <stage>` flips that stage + downstream.

## Show bible

Everything genre-flavored — positioning, hook grammar, beat templates, tone,
thresholds, caption policy, platform limits — lives in
`config/show_bible.<show>.json` and is read by stages from there. No
show-specific content is hardcoded in `orchestration/stages/` (enforced by test).

## Example

`episodes/_example/` is a committed dry episode: a fresh manifest plus
hand-authored brain artifacts under `stages/*/` and a stub `vo.wav`. With the
renderer/compose calls stubbed (`ctx.hooks`), it walks end-to-end to `publish`
(see `tests/test_orchestration.py`).
