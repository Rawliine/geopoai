# W27 — Provided media (forced b-roll source)

Operator- or LLM-supplied video bypasses keyword search and stock ranking. The
clip is used as a **forced pick** (`source.name = "provided"`) but still runs the
integrity probe (ffprobe) and, by default, the verifier gate.

## Shot spec field: `provided`

Pop this object from the spec before JSON Schema validation (the schema does not
yet list it; W20 injects it at runtime). Exactly one of `url` or `path` is
required. **`license` is mandatory** — mirror `asset_wrapper` provenance
discipline (`type`, `attribution_required`, `commercial_use_ok`, plus
`attribution_text` when required).

```json
{
  "shot_id": "ep017-broll-003",
  "intent": "aerial container ships at dawn",
  "kind": "establishing",
  "duration_seconds": 4,
  "provided": {
    "url": "https://example.com/clip.mp4",
    "license": {
      "type": "cc-by",
      "attribution_required": true,
      "attribution_text": "Example News / CC BY 4.0",
      "commercial_use_ok": true
    }
  }
}
```

Local file variant:

```json
"provided": {
  "path": "/data/incoming/operator_clip.mp4",
  "license": { "...": "..." }
}
```

Optional `retrieved_at` (ISO 8601 UTC) is echoed into `source.source_metadata`;
defaults to ingest time.

## CLI

```bash
# URL or path on the command line; license still comes from provided.license in the spec
python pipeline/broll.py shot_spec.json --provided https://example.com/clip.mp4

python pipeline/broll.py shot_spec.json --provided /path/to/clip.mp4
```

`--trust-provided` skips the verifier gate (integrity probe still runs). Exit
codes match other b-roll paths: `5` on verifier rejection, `2` on invalid
provided input / missing license.

## W20 routing

Episode manifest `inputs[]` entries with `use: "broll"` map to
`pipeline/broll.py --provided <url>` (or a `provided` block on the shot spec).
Orchestration wiring is out of scope for W27.
