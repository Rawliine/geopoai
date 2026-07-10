# media_input — operator media drop folder

Drop images and videos you want an episode to use **here**, then reference them
by **bare filename** in the episode's `inputs[]`. No full paths, and this folder
always exists — so you can stage media before the episode is even created.

```jsonc
// inputs.json
[
  { "id": "hk1", "type": "video", "path": "hassan_hook.mp4", "use": "hook",  "clip": [12, 18] },
  { "id": "br1", "type": "video", "path": "walking.mp4",     "use": "broll" },
  { "id": "m1",  "type": "image", "path": "morocco_mask.jpg","use": "map_mask", "region": "Morocco" }
]
```

`ingest` resolves each `path` in this order:

1. the path as given (absolute or repo-relative),
2. the episode's own `episodes/<id>/assets/` folder (episode-specific overrides),
3. this `media_input/` inbox.

So `"path": "walking.mp4"` finds `media_input/walking.mp4`.

Notes:
- `use` (hook / broll / manim_media / map_mask / map_region), `clip: [start,end]`
  (trim a video), and `region` (mask target) still go in `inputs[]` — a folder
  can't express those.
- **Video URLs** are downloaded automatically (yt-dlp); you only need this folder
  for local files and for **images** (image URLs are not fetched yet).
- Contents are gitignored — only this README and `.gitkeep` are tracked.
