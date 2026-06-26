# W25 — Manim media component (`showMedia`)

SKILL.md additions for the W25 lane. The lead merges these into
`manim_renderer/docs/SKILL.md` at integration; do not hand-edit SKILL.md from
this lane.

---

### Component actions

#### `showMedia`

A layout-sized **media frame** that displays an image **or** a video scaled to
**fit inside without stretching** (`fit: "contain"` → letterboxed bars from
token colors). Optional caption line and attribution chip. Ken Burns drift is
opt-in (`ken_burns: true`).

```json
{
  "at": 0.0,
  "action": "showMedia",
  "params": {
    "id": "media-1",
    "src": "assets/images/episode_photo.jpg",
    "fit": "contain",
    "caption": "Front line, March 2024",
    "attribution": "Maxar / 2024",
    "ken_burns": false,
    "size": "medium",
    "timing": "normal",
    "effect": "fade-in",
    "role": "primary"
  }
}
```

Required: `id`, `src` (image or video path under `assets/images/` or
`assets/videos/`, or repo-root-relative / absolute).

- **`fit`** — `contain` (default, letterbox, never stretch) or `cover` (fill
  frame with matte crop). Prefer `contain` for episode media.
- **`attribution`** — optional credit chip (bottom-right inside the frame).
- **`caption`** — optional line below the frame.
- **`ken_burns`** — slow pan/zoom when true; `direction` + `zoom` tune the drift.
- **`media_type`** — `auto` (extension), `image`, or `video` override.

Effects: `fade-in` (Phase 1). Exits via `hideMedia` / `removeMedia`.

#### `showImageCard` (legacy alias)

Same as before — maps to MediaFrame with Ken Burns on and `image`/`source`
params. Prefer `showMedia` for new scenes.

---

### Generic actions

#### `hideMedia` / `removeMedia`

Clean exit for a `showMedia` frame (same semantics as `removeComponent`).

```json
{
  "at": 6.0,
  "action": "hideMedia",
  "params": { "target": "media-1", "effect": "fade-out", "timing": "fast" }
}
```

Required: `target` (id of an earlier `showMedia` or `showImageCard`).

Demo scenes: `scripts/manim/qa_media.json`, `qa_media_vertical.json`.
