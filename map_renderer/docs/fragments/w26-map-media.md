# W26 — Reserved-region media (post-composition box)

Screen-anchored media (a top-half video, a lower-third, a PiP box) is **composited
in post**, never decoded in the headless browser. The map renderer's only jobs are
(1) keep its own screen-fixed text out of the reserved region, and (2) emit the
reserved windows so composition knows where/when to drop the media. **Nothing is
drawn on the map** for a reserved region — no box, no placeholder.

> Clip-to-border media (a flag/image clipped to a country shape) is a *different*
> feature — see `maskImage` (W11), unchanged. Clip-to-border **video** is out of scope.

## Actions

### `reserveRegion`
Reserve a screen region for a bounded time window. Draws nothing; deterministic
(the in/out ramp is a pure function of scene time).

```json
{ "at": 2.0, "action": "reserveRegion",
  "params": { "id": "media-top", "region": "top", "duration": 4, "ramp": 0.5 } }
```

| param | meaning |
|---|---|
| `id` | band id (used by `releaseRegion` and the sidecar) |
| `region` | `"top"` (top half) · `"bottom"` (bottom half) · `"lower-third"` · or `{ "rect": { "x","y","w","h" } }` (values ≤ 1 are fractions of the frame) |
| `at` | window start (s) |
| `duration` | window length (s); the band ramps in at `at`, holds, ramps out at `at+duration` |
| `ramp` | in/out ramp length (s), default `0.4` |

### `releaseRegion`
End a band early — the out-ramp begins at `at`.

```json
{ "at": 5.0, "action": "releaseRegion", "params": { "id": "media-top" } }
```

## Behavior — active safe-area enforcement
While a band is active, the renderer keeps **screen-fixed text** (titles, labels,
the caption band) out of it: each non-geo `.effect-label` is shifted clear of the
band along its inline `top`, eased by the band ramp, and restored when the band
releases. This is a generalization of the caption-band exclusion.

The **globe** is *not* moved by the renderer — framing the map into the
complementary area is an **authoring** decision: pair every reserve window with a
camera move so the geography sits outside the band. The 2 Hz layout sidecar lets QC
flag geography that bleeds in.

> **Authoring note.** A reserve window should coincide with a camera move that frames
> the globe into the complementary area. Put a **single** title in the reserved area
> if any — enforcement clears each label from the band but does not de-overlap
> multiple labels that get pushed to the same edge.

## Sidecar — `{clip}.regions.json`
Emitted by `runner.py` for every render:

```json
{ "clip_id": "…", "format": "horizontal", "frame": [1920, 1080],
  "regions": [ { "id": "media-top", "region": "top", "edge": "top",
                 "rect": [0, 0, 1920, 540], "start": 2, "end": 6, "ramp": 0.5 } ] }
```

`rect` is `[x, y, w, h]` in frame pixels — the exact region the map kept clear.

## Compose side — `media_overlays[]`
The actual media is overlaid in post (`compose.schema.json` → `media_overlays[]`,
applied by `composition/media_overlay.py`):

```json
"media_overlays": [
  { "id": "media-top", "src": "broll/clip.mp4", "region": "top",
    "start": 2, "end": 6, "fit": "contain", "border": true, "caption": "…" }
]
```

`start`/`end` are **episode-time** seconds. A named `region` is **inset** (side +
edge padding) and edge-anchored — the media is contain-fit inside that padded box
(no stretch) and the **map shows around it** (no black letterbox). An explicit
`rect` is used verbatim, centered. The token border is **off by default**
(`"border": true` to draw it). `flags.media: false` skips the pass.

> Pair the box with a camera that frames the globe into the complementary area
> (e.g. a high pitch so land sits low and the box floats over sky) — otherwise the
> media overlaps the globe.

## Demo
- `scripts/map/qa_reserve_region.json` — horizontal; a `top` reserve window `[2, 6]`,
  text easing out of the band and re-flowing, window in `qa_reserve_region.regions.json`.
- `scripts/map/qa_reserve_region_v.json` — vertical; globe pitched low, a `flyTo`
  panning the map *under* the screen-anchored box, one label easing out.

Overlay media with a compose spec carrying the matching `media_overlays[]` entry.
