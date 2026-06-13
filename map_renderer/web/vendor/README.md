# Map renderer vendor bundles (pinned)

| Package        | Version | Source |
|----------------|---------|--------|
| `@turf/turf`   | 6.5.0   | https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js |
| `flubber`      | 0.4.2   | https://cdn.jsdelivr.net/npm/flubber@0.4.2/build/flubber.min.js |

Refresh (same URLs, new file on disk):

```bash
curl -fsSL -o turf.min.js "https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js"
curl -fsSL -o flubber.min.js "https://cdn.jsdelivr.net/npm/flubber@0.4.2/build/flubber.min.js"
```

Current engine logic does not call `turf` / `flubber` yet; they are loaded so later lanes can use morphing / geodesy without editing `map.html`.
