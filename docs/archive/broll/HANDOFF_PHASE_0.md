# HANDOFF — B-Roll Phase 0 → Phase 1

Written: 2026-05-20. Author: agent that built Phase 0.
Read this before touching Phase 1. Then read `AGENT(1).md` and `plan(1).md`.

---

## TL;DR

Phase 0 is **complete and tested** (58/58 unit tests passing offline). One
loose end: the real-Pexels end-to-end smoke test is gated on `PEXELS_API_KEY`,
which is not yet set in the repo's `.env`. Add the key and run

```bash
pytest broll/tests/test_phase0_smoke.py -m network
```

to close out the live-network exit criterion ("one shot fetched + tagged with
full provenance"). Everything else — schema validation, wrapper atomicity,
decision matrix, raw-download CI guard — is verified offline.

---

## What was built

### Directory tree

```
broll/
├── __init__.py
├── HANDOFF_PHASE_0.md           ← this file
├── AGENT(1).md                  ← unchanged (pre-existing)
├── plan(1).md                   ← unchanged
├── recap(1).md                  ← unchanged
├── lib/
│   ├── __init__.py
│   ├── asset_wrapper.py         ✅ single path to disk
│   ├── decision.py              ✅ DECISION_TABLE matrix
│   ├── keyword_generator.py     ✅ heuristic + LLM hook
│   └── errors.py                ✅ typed error hierarchy
├── sources/
│   ├── __init__.py              ✅ SOURCES registry (pexels only for now)
│   └── pexels.py                ✅ search + fetch
├── schema/
│   ├── asset_meta_schema.json   ✅ strict, additionalProperties: false
│   └── shot_spec_schema.json    ✅ strict, kind enum locked to matrix
├── comfyui_workflows/           ← created empty, Phase 2 fills it
├── prompts/                     ← created empty, Phase 2 fills it
├── templates/                   ← created empty, Phase 4 fills it
└── tests/
    ├── __init__.py
    ├── conftest.py              ✅ adds repo root to sys.path, registers markers
    ├── test_schemas.py          ✅ both schemas, happy + sad paths
    ├── test_decision.py         ✅ matrix coverage + hint override behaviour
    ├── test_keyword_generator.py
    ├── test_asset_wrapper.py    ✅ local HTTP fixture; atomicity, rollback
    ├── test_no_raw_downloads.py ✅ CI grep guard
    └── test_phase0_smoke.py     ⚠ gated on PEXELS_API_KEY (network mark)

pipeline/
└── broll.py                     ✅ CLI: shot_spec.json → output/broll/*.mp4

scripts/broll/
└── test_shot.json               ✅ sample establishing-shot spec

output/broll/                    ← created, gitignored via top-level rule
```

### Exit criteria mapping

`plan(1).md` Phase 0 exit criteria:

| Criterion | Status | Evidence |
|---|---|---|
| `broll/` directory created with full layout | ✅ | tree above |
| `asset_meta_schema.json` defined | ✅ | `broll/schema/asset_meta_schema.json` |
| `shot_spec_schema.json` defined | ✅ | `broll/schema/shot_spec_schema.json` |
| `asset_wrapper.py` single CLI entry, no raw downloads anywhere | ✅ | wrapper + `test_no_raw_downloads.py` enforces |
| `keyword_generator.py` LLM-driven intent → 3-5 queries | ✅ partial | heuristic shipped; LLM is a Protocol stub — Phase 1 plugs in Claude |
| `decision.py` stock-first vs AI-first taxonomy | ✅ | `DECISION_TABLE` + `decide()` |
| `scripts/broll/test_shot.json` smoke test, end-to-end against Pexels | ✅ scaffold, ⚠ live run gated on key | spec exists, smoke test exists, just needs `PEXELS_API_KEY` |
| **One shot fetched + tagged with full provenance** | ⚠ blocked on key | wrapper proven against local HTTP; real Pexels run waits for the key |
| **Schema rejects malformed shot specs** | ✅ | 8 negative-case parametrized tests + CLI verified to exit 2 |

---

## How to verify locally

```bash
# 1. Offline tests (fast, no creds)
pytest broll/tests/ -m "not network"          # → 58 passed

# 2. Live smoke test (requires Pexels key)
echo "PEXELS_API_KEY=<your_key>" >> .env
pytest broll/tests/test_phase0_smoke.py -m network

# 3. End-to-end CLI
python pipeline/broll.py scripts/broll/test_shot.json --print-meta
# → output/broll/phase0-smoke-001.mp4 + .mp4.meta.json
```

The CLI exits with these codes:
* `0` — success
* `1` — generic BrollError (e.g. shot kind requires AI which is not yet wired)
* `2` — schema validation failure
* `3` — source auth error (PEXELS_API_KEY missing or rejected)
* `4` — no candidates across all queries

---

## Architectural choices made (and why)

### 1. Meta path is `<asset>.meta.json`, not `<asset>.json`

`output/broll/x.mp4` → `output/broll/x.mp4.meta.json`. Appending rather than
replacing the extension means a directory listing groups asset + meta visually
and `rm x.mp4*` cleans both. The audit (Phase 4) can also `glob('*.meta.json')`
and follow `asset_path` back, with no ambiguity if `x.mp4` and `x.png` coexist.

### 2. Atomicity via sibling-tempfile + `os.replace`

Both `download` and `finalize` write to `.<name>.<rand>.tmp` *in the same
directory* as the target, fsync, then `os.replace`. This is the standard POSIX
atomic-write pattern; `os.replace` is atomic on the same filesystem. Critically,
meta is written **after** the asset is in place — if meta validation fails, the
asset is deleted (`test_invalid_meta_rolls_back_asset` enforces this). The
inverse leak (orphan meta with no asset) cannot happen because meta writing
comes last.

### 3. `urllib.request` over `requests`

The project's `requirements.txt` doesn't include `requests`. I didn't add a
dependency just to do `GET`s. `urllib.request` handles everything Phase 0
needs; Phase 1 sources that want session pooling, automatic retries, or
multipart uploads can add `requests` then.

### 4. Heuristic keyword generator ships, LLM is a Protocol

Phase 0 boots with `generate_queries()` working offline so the smoke test and
CI don't need an LLM. The `LLMClient` Protocol defines the slot Phase 1 wires
into. The heuristic is intentionally dumb (stopword stripping, perspective/
time-of-day token picking) — good enough for fallback, not a replacement.

### 5. Decision matrix as data, not branches

`DECISION_TABLE` is a dict in `decision.py`. Adding a new kind = adding a row.
The matrix encodes both the **default strategy** and whether the
orchestrator's `stock_first` hint can override it (locked for `stock_only` and
`ai_only` kinds, flexible for `stock_first` and `ai_first`). This matches the
AGENT.md philosophy: "the LLM hints but the layer enforces".

### 6. CI grep guard for raw downloads

`test_no_raw_downloads.py` parametrizes over every `.py` under `broll/`
(except an allowlist of the wrapper itself + this test file + the wrapper's
own test fixture) and asserts that none of these patterns appear:

* `urllib.urlretrieve` / `urllib.request.urlretrieve`
* `requests.get(...).content` / `requests.post(...).content`
* `requests.get(stream=True)`
* `open(..., 'wb') ... urlopen` (DOTALL)

Add new sources → the grep test automatically covers them. If a legitimate
exception is needed, edit `ALLOWLIST` *and* document why.

### 7. Schema enforces the stock↔ai_metadata coupling

The asset_meta schema uses JSON Schema `if/then/allOf` to enforce: `kind:
stock_video` ⇒ `ai_metadata: null`; `kind: ai_video|ai_image` ⇒ `ai_metadata`
present and an object. This is double-belt-and-braces with the wrapper's
runtime check (`_build_meta` raises before validation), but the schema is the
canonical source of truth so external producers can validate without our code.

---

## Known issues / gotchas for Phase 1

### 1. The 3 `.md` files in `broll/` are named `AGENT(1).md`, `plan(1).md`, `recap(1).md`

Pre-existing on `main`. They were not renamed because they're the user's
content. The docs reference each other by the un-suffixed names (`AGENT.md`,
`plan.md`, `recap.md`). Either rename them (low risk) or just be aware of the
mismatch when reading cross-references.

### 2. `pipeline/broll.py` does its own `sys.path` insert

When the file is invoked as `python pipeline/broll.py …`, the import `from
broll …` only works because we prepend the repo root. The same trick is in
`broll/tests/conftest.py`. If the project ever gets a real package install,
both can be removed. Not blocking Phase 1 — just don't be surprised.

### 3. `output/broll/` is gitignored (via top-level `output/` rule)

That's correct — clips don't belong in git. But it also means the directory
won't appear on a fresh clone. The pipeline creates it at runtime. If you want
a placeholder, add `output/broll/.gitkeep` with a `!output/broll/.gitkeep`
exception in `.gitignore`. Phase 0 doesn't bother.

### 4. The smoke test in `test_phase0_smoke.py` skips silently without the key

That's deliberate (the rest of the suite is hermetic), but it means CI will
pass without ever exercising the real Pexels integration. **Add `PEXELS_API_KEY`
to the CI environment** if you want this enforced before merging Phase 1.

### 5. `download()` keeps the entire transfer in memory? — no, but worth noting

It streams in 64 KiB chunks. There's a `max_bytes` cap (default 512 MiB) and
oversize transfers raise mid-stream — but they do *not* clean up the partial
tempfile written so far. The `_atomic_writer` context manager catches the
exception and deletes the tempfile, so disk is clean. `test_download_size_cap_enforced`
verifies. Worth re-checking if you ever add resumable downloads.

### 6. Pexels HLS files are filtered out

The Pexels API sometimes returns `.m3u8` HLS playlists alongside progressive
mp4s. `_pick_video_file` in `sources/pexels.py` drops anything whose
`file_type` ends with `mpegurl` because the wrapper expects a single-file
GET. If a video offers *only* HLS, we return `None` for it and the cascade
sees fewer candidates. Phase 1's cascade should not treat this as a Pexels
failure — it's a candidate-quality issue.

### 7. The `verification` field is `null` for everything Phase 0 produces

Schema accepts `null`. Phase 1 wires `verify.py` (CLIP + vision-LLM) into the
cascade and starts populating this field. Don't add a runtime requirement
elsewhere that `verification` is non-null until Phase 1 ships it.

### 8. `.env` already contains `VERDA_CLIENT_ID` / `VERDA_CLIENT_SECRET`

Phase 0 doesn't touch them. Phase 2's AI sources will. Confirm they're still
valid before standing up the ComfyUI clients.

### 9. Pexels API rate limit is 200 req/hour by default

Search calls eat into it. The smoke test makes 1 search + 1 download (download
URL goes to a CDN, not the API). Phase 1's cascade will multiply this. Cache
or back off accordingly.

---

## What's ready for Phase 1 to plug into

Phase 1 should:

1. **Implement the cascade walker** (`broll/lib/cascade.py`). Interface:
   ```python
   def walk(shot_spec: dict, *, max_candidates: int = 3) -> list[SearchResult]
   ```
   Reuse the `SearchResult` dataclass from `sources/pexels.py` (or hoist it to
   `broll/sources/__init__.py` since every source needs it).
2. **Add Wikimedia, LoC, NARA, Archive.org, Pixabay clients** following the
   contract laid out in AGENT.md §"How to add a stock source". Each new
   source automatically gets covered by the no-raw-downloads grep.
3. **Add `broll/lib/verify.py`** with CLIP prefilter + vision-LLM stages.
4. **Wire an LLMClient implementation** for `keyword_generator`. The Protocol
   is in `broll/lib/keyword_generator.py:LLMClient`.
5. **Update `pipeline/broll.py`** to call `cascade.walk` + `verify` instead of
   the Pexels-direct call. Keep the CLI surface identical.

The schemas, wrapper, decision matrix, and CI guards should not need to change
for Phase 1. Schema additions (e.g. new license types) require a coordinated
update in `broll/schema/asset_meta_schema.json` *and* a bump of
`schema_version`.

---

## Open questions surfaced during Phase 0

None of these are blockers; they're things Phase 1 will probably need to
answer.

* **Should the wrapper hash assets?** Computing `sha256` on the body stream is
  cheap and makes dedup + tamper detection trivial. The schema doesn't have a
  slot yet — easy add. Skipped in Phase 0 to keep the surface small.
* **Should `source.url` always be the *fetch* URL or the *canonical* URL?**
  Pexels has a "page URL" (`https://www.pexels.com/video/12345/`) and a
  "download URL" (CDN). I store the page URL in `source.url` and the CDN URL
  in `source.source_metadata`. Attribution wants the page; debugging wants the
  CDN. Confirm this convention with attribution slate work in Phase 4.
* **Schema enum vs free-form for `source.name`.** Currently free-form. Adding
  every future source would be enum churn. Probably fine to leave free-form
  and let the audit (Phase 4) enforce known-set membership.
* **Should `kind` on the asset meta include `stock_image`?** Phase 0 has only
  `stock_video`, `ai_video`, `ai_image`. AGENT.md doesn't show photo support.
  `plan(1).md` §"What we're not building" explicitly says: video-only. So
  this is intentional — but the schema should reject stock photos cleanly if
  someone tries. It does (the enum doesn't include it).
* **`shot_id` collision policy.** The wrapper happily overwrites an existing
  asset with the same target path. The orchestrator is responsible for shot_id
  uniqueness. If we ever want write-once semantics, add an `overwrite=False`
  guard to `download`/`finalize`.

---

## Files added (full list)

```
broll/__init__.py
broll/HANDOFF_PHASE_0.md
broll/lib/__init__.py
broll/lib/asset_wrapper.py
broll/lib/decision.py
broll/lib/errors.py
broll/lib/keyword_generator.py
broll/schema/asset_meta_schema.json
broll/schema/shot_spec_schema.json
broll/sources/__init__.py
broll/sources/pexels.py
broll/tests/__init__.py
broll/tests/conftest.py
broll/tests/test_asset_wrapper.py
broll/tests/test_decision.py
broll/tests/test_keyword_generator.py
broll/tests/test_no_raw_downloads.py
broll/tests/test_phase0_smoke.py
broll/tests/test_schemas.py
pipeline/broll.py
scripts/broll/test_shot.json
```

Empty placeholder dirs (no files yet): `broll/comfyui_workflows/`,
`broll/prompts/`, `broll/templates/`.

No existing files in the repo were modified.

---

## Test counts

```
58 unit tests pass offline.
 1 smoke test deselected (network marker, needs PEXELS_API_KEY).
 0 modifications to existing tests or production code outside broll/.
```

Good luck with Phase 1.
