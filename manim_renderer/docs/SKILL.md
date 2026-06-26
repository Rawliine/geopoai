# Manim scene skill — action vocabulary for the LLM author

This file is the **single source of truth** the LLM uses when authoring Manim
scene JSON. Every `action` value the LLM emits must appear here. Adding a new
component or action means appending a section to this file in the same PR.

The schema (`manim_renderer/schema/`) enforces what this doc describes — the
two must stay in sync.

---

## Top-level scene shape

```json
{
  "renderer": "manim",
  "format": "horizontal",        // or "vertical"
  "quality": "preview",          // "preview" | "draft" | "full"
  "scene": {
    "layout": "hero",            // see Layouts section
    "duration": 8,               // seconds, > 0
    "theme": "dark"
  },
  "slots":    { "<slot_name>": <event> },   // primary content, slot positions
  "overlays": [ <event> ],                  // annotations on top of slots
  "timeline": [ <event> ]                   // scene-level events (camera, etc.)
}
```

Event shape:
```json
{ "at": 0.0, "action": "<actionName>", "params": { ... } }
```

Event ordering at equal `at`: slots fire before overlays before timeline. Use
this when an overlay needs to anchor against a slot that fired the same instant.

---

## Coordinates

**Forbidden.** The schema rejects keys `x`, `y`, `position`, `coords`,
`coordinate`, `coordinates` anywhere in the JSON. Position elements with:

- **Slots** — name a slot from the layout (e.g. `"main"`, `"left"`).
- **Anchors** — `"<token>:<id>"` strings where `<id>` is a kebab-case id of an
  earlier event. Tokens (Phase 1):
  - `above:id` — above the target
  - `below:id` — below the target
  - `left-of:id` — to the left
  - `right-of:id` — to the right (auto-flips to `below` in vertical format)
  - `inside:id` — at the target's center

In vertical scenes, `right-of` and `left-of` map to `below` and `above`. Stay
axis-agnostic — the resolver handles it.

---

## Timing

`params.timing` (where supported) is one of:

| name      | seconds |
|-----------|---------|
| instant   | 0.0     |
| snap      | 0.15    |
| fast      | 0.3     |
| normal    | 0.6     |
| slow      | 1.0     |
| dramatic  | 1.6     |
| crawl     | 3.0     |

**Hold times matter more than animation speed.** A 0.6s reveal should hold
1.5–2s after.

---

## Effects vocabulary (Phase 1)

Phase 1 ships a subset of the eventual 35-effect vocabulary. Each component's
schema lists which effects it accepts.

**Entrances:** `fade-in`, `write-in`, `draw-out`, `grow-up`, `grow-down`,
`slide-left`, `slide-right`, `slide-up`, `slide-down`, `level-by-level`,
`count-up` (StatBlock-only).

**Emphasis:** `pulse`, `highlight`.

**Exits:** `fade-out`, `dissolve`.

---

## Value formats

Used by StatBlock / MetricGroup (and BarChart / LineChart in PR 1.3). All are
en-US locale (comma thousands, dot decimals). Negative numbers use the
typographic minus (U+2212 `−`), not hyphen-minus.

| Format       | Example input → output | Extra params |
|--------------|------------------------|--------------|
| `int`        | `1234567` → `"1,234,567"` | — |
| `decimal`    | `3.14159` → `"3.1"` | `decimals` (default 1) |
| `pct`        | `42.5` → `"42.5%"` (value is the percentage, not a fraction) | `decimals` |
| `k`          | `1500` → `"1.5K"` | `decimals` |
| `m`          | `1500000` → `"1.5M"` | `decimals` |
| `currency`   | `1234.5` → `"$1,234.50"`; with `suffix:"auto"` `1500` → `"$1.50K"` | `symbol` (default `$`), `decimals` (default 2), `suffix` (`K`/`M`/`B`/`auto`) |
| `signed`     | `15.3` → `"+15.3"`, `-3.4` → `"−3.4"` | `decimals` |
| `duration`   | `3600` → `"1h"`; `7325` → `"2h 2m"` (seconds in, two largest non-zero units out) | — |
| `ratio`      | `[10,4]` → `"5:2"` (auto-reduces by gcd); `2.5` → `"2.5:1"` | — |
| `scientific` | `1500000` → `"1.50×10⁶"` | `decimals` (default 2) |

---

## Sizes

`params.size` (where supported) is `"small"`, `"medium"`, or `"large"`.
Components resolve sizes per-format internally — same role works in both
horizontal and vertical scenes.

---

## Roles (Phase 2)

Every component has a **role** at every instant. The role drives size,
opacity, z-order, and how the layout solver allocates space. Set on entry
via `params.role`; change later via the `setRole` action.

| Role         | When to use |
|--------------|-------------|
| `hero`       | Single dominant element; takes most of the frame. Use at most one per beat. |
| `primary`    | Main subject(s); large, full opacity. **Default** for every component except `showCalloutBox`. |
| `supporting` | Present but quieter; dimmed, often shrunk. Use for KPIs that have moved past their headline moment. |
| `ambient`    | Context only; small, very dim. Use for sidebar reminders or watermark-style elements. |
| `annotation` | A callout, badge, or label tied to another element. **Default** for `showCalloutBox`. |
| `hidden`     | Present in state but not rendered. Use for components you plan to bring back. |

Role is purely declarative — the engine maps it to allocation, scale, and
opacity. Authors never set sizes or alphas directly to communicate
role-like meaning.

PR F (this PR) records roles but does not yet move components in response.
Restage (PR G+) consumes the same data without any author-facing changes.

---

## Component actions

### `showTextCard`
Centered text. Used for chapter cards and intro/outro slides.

```json
{
  "at": 0.0,
  "action": "showTextCard",
  "params": {
    "id": "intro",
    "text": "Prisoner's Dilemma",
    "size": "title",         // "title" | "body" | "label" | "caption"
    "timing": "normal",
    "effect": "fade-in"
  }
}
```

Required: `id`, `text`. Effects: `fade-in` only (Phase 1).

---

### `showStatBlock`
Big number with label, optional unit, trend indicator, and inline sparkline. The
go-to component for any quantitative beat in a video.

```json
{
  "at": 0.0,
  "action": "showStatBlock",
  "params": {
    "id": "stat-defection",
    "value": 71.6,
    "label": "Defect rate",
    "value_format": "decimal",     // see Value formats below
    "decimals": 1,
    "unit": "%",
    "color": "actor_b",            // palette key, not hex
    "size": "medium",              // "small" | "medium" | "large"
    "trend": {
      "delta": 8.2,
      "direction": "up",           // "up" | "down" | "flat"
      "unit": "%"
    },
    "sparkline": [38, 45, 52, 58, 65, 69, 72],
    "timing": "normal",
    "effect": "count-up"           // or any standard entrance
  }
}
```

Required: `id`, `value`, `label`.
Custom anchors: `value`, `label`, `unit`, `trend`, `sparkline` — point a
callout at a specific part of the stat (e.g. `right-of:stat-defection.value`
is NOT supported; the stat's own custom anchors are exposed when JSON code
references the stat's id directly via `right-of:stat-defection`).
Effects: any entrance, plus `count-up` (animates value from 0 → target).

Value formats: see the **Value formats** section below.

---

### `showMetricGroup`
A row or column of StatBlocks under one id, with shared styling. Use when you
want 2–6 KPIs to appear together.

```json
{
  "at": 0.0,
  "action": "showMetricGroup",
  "params": {
    "id": "kpis",
    "orientation": "row",          // "row" | "column" (defaults from format)
    "spacing": 0.6,
    "color_scheme": "actors",      // "actors" | "semantic" | "accent"
    "size": "small",
    "value_format": "decimal",     // shared default for child stats
    "effect": "staggered",         // or any standard entrance
    "stagger": "normal",           // "dense" | "normal" | "dramatic"
    "child_effect": "count-up",    // entrance applied to each stat
    "timing": "normal",
    "stats": [
      { "id": "k-coop",   "value": 28.4, "label": "Cooperate",  "unit": "%" },
      { "id": "k-defect", "value": 71.6, "label": "Defect",     "unit": "%" },
      { "id": "k-loss",   "value": 1200000, "label": "Loss",
        "value_format": "currency", "symbol": "$", "suffix": "auto" }
    ]
  }
}
```

Required: `id`, `stats` (2–6 items, each requiring `value` + `label`).
Each stat's own optional `id` is exposed as a top-level anchor target — you
can write `right-of:k-defect` from a callout or another anchored event.

Color schemes:
- `actors` — rotates `actor_a/b/c/d/e`
- `semantic` — rotates `positive/neutral/negative`
- `accent` — all `highlight`

Effects: any standard entrance, plus `staggered` (LaggedStart of each child's
entrance, tunable via `stagger` + `child_effect`).

---

### `showBarChart`
Categorical bar chart with themed axes. Use for side-by-side numeric comparison
(country GDP, party seat counts, scenario payoffs). Y-axis starts at 0 by
default — bar charts with truncated y-axes are misleading.

```json
{
  "at": 0.0,
  "action": "showBarChart",
  "params": {
    "id": "gdp",
    "data": [
      { "label": "USA",   "value": 23000, "color": "actor_a" },
      { "label": "China", "value": 17000, "color": "actor_b" }
    ],
    "size": "medium",
    "value_format": "k",        // labels show "23.0K" etc.
    "show_value_labels": true,
    "y_axis": { "min": 0, "max": 25000, "ticks": 5, "label": "GDP ($B)" },
    "x_axis": { "label": "Country" },
    "timing": "slow",
    "effect": "count-up"        // bar grows + value label counts up, per-bar
  }
}
```

Required: `id`, `data` (1–12 items, each `{label, value, color?}`).
Color defaults rotate through `actor_a..e` if omitted. Auto y-range: 0 to
1.15× max value when `y_axis.min`/`max` are not given.
Custom anchors: `bar:<i_or_label>` — top-center of that bar. Index is 0-based.
Effects: `fade-in`, `grow-up`, `level-by-level`, `count-up`.

---

### `showLineChart`
Multi-series continuous-x line chart. Use for trends over time and projections.

```json
{
  "at": 0.0,
  "action": "showLineChart",
  "params": {
    "id": "trade",
    "series": [
      {
        "label": "USA", "color": "actor_a",
        "points": [[2010, 14], [2015, 18], [2020, 21]]
      },
      {
        "label": "China", "color": "actor_b",
        "points": [[2010, 6], [2015, 11], [2020, 17]]
      }
    ],
    "size": "medium",
    "value_format": "decimal",  // y-axis tick format
    "x_format": "int",          // x-axis tick format (default 'int')
    "show_points": true,
    "x_axis": { "min": 2010, "max": 2020, "ticks": 6, "label": "Year" },
    "y_axis": { "min": 0,    "max": 25,   "ticks": 5, "label": "GDP ($T)" },
    "timing": "slow",
    "effect": "draw-out"        // Create() draws each polyline path
  }
}
```

Required: `id`, `series` (1–8 series, each with `points` of length ≥ 2).
Points are **`[x, y]` arrays**, not `{x, y}` objects — this keeps the
project-wide "no coordinate keys" rule (AGENT.md rule 1) simple, since the
validator's coords-banned tier rejects `x`/`y` keys anywhere in the JSON.
Color defaults rotate `actor_a..e`. Auto ranges from union of points with 5% padding.
Custom anchors:
  * `series:<i_or_label>.end`   — right-most point of a series (great for trailing labels).
  * `series:<i_or_label>.start` — left-most point.
Effects: `fade-in`, `draw-out`, `level-by-level`.

---

### Callout style choice guide (Phase 2)

| Style       | When to use |
|-------------|-------------|
| `neon`      | **Default.** Punchy accent border with halo, perceptible at preview resolution. Best general-purpose. |
| `neon-bold` | When the callout needs to dominate visually — headline moments, the punchline of an explanation. Use sparingly. |
| `card`      | Neutral annotation that doesn't compete for attention — sidebar notes, calm context. |
| `glass`     | Translucent emphasis over busy backgrounds — call out a region without blocking it. |
| `pull-quote`| No bubble. Large accent quote marks bracket the text. Use for thematic emphasis (single-sentence summary of a beat). |
| `inline-tag`| Chip-style label (no leader). Use for short labels: "Equilibrium", "Cooperate", country names. 1-line max. |

### `showCalloutBox`
Text bubble + leader line pointing at an anchor target. The first component
that uses the anchor resolver — `params.anchor` is required.

```json
{
  "at": 4.5,
  "action": "showCalloutBox",
  "params": {
    "id": "callout-1",
    "text": "Defection dominates: best responses erode cooperation.",
    "anchor": "right-of:k-defect",
    "width": 4.5,                  // max bubble width in Manim units (1.0–8.0)
    "arrow": true,                 // arrowhead at leader tip
    "color": "highlight",          // accent color (palette key) — drives border
                                   //   stroke for neon/glass, text for card
    "style": "neon",               // "neon" (default) | "card" | "glass"
    "timing": "normal",
    "effect": "fade-in"            // overrides style's signature animation when set
                                   //   to a generic entrance (fade-in, grow-up, etc.)
  }
}
```

Required: `id`, `text`, `anchor`.
Custom anchors exposed: `head` (leader tip) and `tail` (leader root) — useful
when chaining callouts. Long text auto-wraps to fit `width`.
Format-aware: in vertical scenes, `right-of`/`left-of` flip to `below`/`above`
for both the bubble position AND the leader endpoints.

**Side override (`strict_axis`):**
By default in vertical scenes, anchor tokens `right-of` and `left-of`
auto-flip to `below` and `above` so authors stay axis-agnostic. When you
*specifically* want a side-of-target callout in a vertical scene (e.g. to
demo callouts to the right/left of a stat in a `trio-stack` row), pass
`"strict_axis": true` alongside the explicit `anchor`. The flip is
suppressed for both bubble placement AND the leader line.

```json
{ "action": "showCalloutBox", "params": {
    "id": "side", "slot": "A",
    "anchor": "right-of:trio-a", "strict_axis": true,
    "text": "Right side of the row.", "style": "neon", "width": 2.4 } }
```

Leave `strict_axis` unset (or `false`) for axis-agnostic authoring — the
default flip keeps callouts placed inside the active layout's main axis.

**Style (Phase 1.5 + 2.0):**
- `neon` (default) — no fill; **three-layer** accent stroke (outer glow +
  mid glow + tight border) traces in via `Create`, then text fades. Exit
  reverses: text fades, border erases via `Uncreate`. Use for highlight
  callouts, dramatic emphasis.
- `card` — surface fill + thin border, bubble + text fade together (legacy).
  Use for neutral annotations.
- `glass` — translucent dark fill + brighter accent border. Lower-third feel.

(Phase 2.0 — PR E: dropped `bracket`. New variants `neon-bold`, `pull-quote`,
`inline-tag` are scheduled for PR P alongside the roles+restaging system.)

Text color auto-contrasts against the scene background for the transparent
styles (neon, glass): light text on dark backgrounds. Card style honors
explicit `color` or uses `text_primary`.

Example with style variants:
```json
{ "action": "showCalloutBox", "params": {
    "id": "cb-neon", "text": "Accent border traces in.",
    "anchor": "above:bars", "width": 5.0, "style": "neon", "color": "highlight" } }

{ "action": "showCalloutBox", "params": {
    "id": "cb-card", "text": "Neutral reference annotation.",
    "anchor": "right-of:pd", "width": 3.0, "style": "card" } }
```

---

### `showTimeline`
Single-axis timeline of dated events. Format-aware: horizontal runs L→R with
labels alternating above/below the axis; vertical runs T→B with labels right
of dots and dates left. Same JSON for both formats.

```json
{
  "at": 0.0,
  "action": "showTimeline",
  "params": {
    "id": "tl",
    "events": [
      { "id": "wwii", "at_label": "1939", "label": "WWII begins" },
      { "id": "vj",   "at_label": "1945", "label": "VJ Day",
        "color": "highlight" }
    ],
    "size": "medium",
    "max_visible": 8,      // vertical-only cap (default 8)
    "timing": "normal",
    "effect": "level-by-level"
  }
}
```

Required: `id`, `events` (1–20 items, each `{label, id?, at_label?, color?}`).
Custom anchors:
  * `event:<i_or_id>`       — that event's dot center
  * `event:<i_or_id>.label` — label text center
  * `event:<i_or_id>.date`  — date text center (only when `at_label` set)
Each event's own optional `id` is also exposed as a top-level anchor target —
write `below:wwii` to anchor against the wwii event's dot.
Effects: `fade-in`, `level-by-level`.

---

### `showGameTree`
Recursive decision-tree visualization. Horizontal format renders root on the
left, leaves on the right (uses 16:9 width well). Vertical format renders root
on top, leaves on bottom, with a depth cap (`max_depth`, default 4).

```json
{
  "at": 0.0,
  "action": "showGameTree",
  "params": {
    "id": "tree",
    "nodes": {
      "label": "P1",
      "children": [
        { "label": "Cooperate", "edge": "C", "children": [
          { "label": "(3,3)", "edge": "C" },
          { "label": "(0,5)", "edge": "D" }
        ]},
        { "label": "Defect", "edge": "D" }
      ]
    },
    "size": "large",
    "max_depth": 4,
    "timing": "normal",
    "effect": "level-by-level"
  }
}
```

Required: `id`, `nodes` (recursive `{label, edge?, color?, children?}`).
`edge` is the label rendered on the connection from PARENT to this node
(not on its outgoing edges).
Custom anchors:
  * `node:<path>` — dot-separated 0-based indices: `node:root`, `node:root.0`,
    `node:root.1.0` (root → its 2nd child → that child's 1st child).
Effects: `fade-in`, `level-by-level` (reveals depth by depth).

---

### `showAllianceWeb`
Geopolitical relations graph. Nodes (countries/actors) placed on a deterministic
circle; edges colored by kind (`alliance`/`rivalry`/`neutral`). `seed` rotates
the whole ring deterministically — same JSON renders identically across runs.

```json
{
  "at": 0.0,
  "action": "showAllianceWeb",
  "params": {
    "id": "web",
    "nodes": [
      { "id": "usa", "label": "USA",    "color": "actor_a" },
      { "id": "rus", "label": "Russia", "color": "actor_b" },
      { "id": "chn", "label": "China",  "color": "actor_c" }
    ],
    "edges": [
      { "from": "usa", "to": "rus", "kind": "rivalry" },
      { "from": "rus", "to": "chn", "kind": "alliance" },
      { "from": "usa", "to": "chn", "kind": "neutral" }
    ],
    "size": "medium",
    "seed": 42,
    "timing": "slow",
    "effect": "level-by-level"
  }
}
```

Required: `id`, `nodes` (2–12 items, each `{id, label?, color?}`).
Edges optional, max 64.
Each node's `id` is exposed as a top-level anchor target — `below:usa` works.
Custom anchors:
  * `node:<id>` — that node's center.
Edge kinds:
  * `alliance` — `positive` color, solid stroke
  * `rivalry`  — `negative` color, dashed stroke
  * `neutral`  — `neutral` color, thin stroke
Effects: `fade-in`, `level-by-level` (nodes first staggered, then edges).

---

### `showPayoffMatrix`
The signature game-theory component. N×N normal-form matrix with player names,
strategy labels, and payoff pairs. Cells colored by player (row player's
payoff in their color, column player's in theirs).

```json
{
  "at": 0.0,
  "action": "showPayoffMatrix",
  "params": {
    "id": "pd",
    "players": [
      { "name": "P1", "color": "actor_a" },
      { "name": "P2", "color": "actor_b" }
    ],
    "strategies": [
      ["Cooperate", "Defect"],
      ["Cooperate", "Defect"]
    ],
    "cells": [
      [{ "a": 3, "b": 3 }, { "a": 0, "b": 5 }],
      [{ "a": 5, "b": 0 }, { "a": 1, "b": 1 }]
    ],
    "size": "medium",
    "timing": "normal",
    "effect": "level-by-level"
  }
}
```

Required: `id`, `players` (exactly 2), `strategies` (2 lists), `cells`
(2D array of `{a, b}` payoffs). Supported sizes: 2×2 through 6×6.
Custom anchors:
  * `cell:i,j` — center of cell (row i, col j). 0-based.
  * `row:i`    — left edge of row i (next to its strategy label).
  * `col:j`    — top edge of column j.
Effects: `fade-in`, `level-by-level` (reveals row by row).

This is the target of the three mutation actions below.

---

## Generic actions (mutate or remove existing components)

**Overlay tracking (Phase 1.5):** all three mutation actions below
(`highlightCell`, `crossOut`, `bestResponseArrow`) auto-register their
overlay against the host id. When you `removeComponent(target=host)` the
host fades AND every overlay attached to it fades in the same animation.
You do NOT have to clean up overlays manually. If you want to remove an
overlay BEFORE its host, pass an optional `id` on the mutation — that
exposes the overlay as a top-level id so `removeComponent(target=<id>)`
works on it directly.

### `removeComponent`
Fade or dissolve an existing component out and unregister its id. Also
fades any overlays registered against this id (PR B / Phase 1.5).

```json
{
  "at": 8.0,
  "action": "removeComponent",
  "params": { "target": "matrix-1", "effect": "fade-out", "timing": "fast" }
}
```

Required: `target` (id of an earlier-declared component OR an overlay
id from a mutation with opt-in `id`).
Default effect: `fade-out`. Default timing: `fast`.

---

### `highlightCell`
Lay a translucent colored overlay on a PayoffMatrix cell. Target must be a
PayoffMatrix.

```json
{
  "at": 6.0,
  "action": "highlightCell",
  "params": {
    "id": "hl-1",                  // optional — exposes overlay as top-level id
    "target": "pd",
    "index": [1, 1],
    "color": "highlight",
    "timing": "fast"
  }
}
```

Required: `target`, `index` ([row, col]). `color` defaults to `highlight`.
Optional `id` makes the overlay individually removable. Auto-cleanup with
host applies in either case.

---

### `crossOut`
Strike a line through a PayoffMatrix row or column. Used for iterated
elimination of strictly dominated strategies (IESDS).

```json
{
  "at": 8.0,
  "action": "crossOut",
  "params": {
    "id": "x-row0",                // optional
    "target": "pd", "axis": "row", "index": 0, "style": "strike"
  }
}
```

Required: `target`, `axis` (`"row"` | `"col"`), `index` (0-based).
`style` is `"strike"` (default, solid) or `"dashed"`. Line is `negative` (red).
Optional `id` exposes the line as a top-level id.

---

### `showCalloutSequence`
Chain multiple callouts so only one is on screen at a time. Each item
fades in, holds, fades out, then the next enters. Use for IESDS-style
explanations (one cell at a time), step-by-step reveals on the same
subject, or any narrative beat that needs several callouts that
shouldn't crowd each other spatially.

```json
{
  "at": 20.0,
  "action": "showCalloutSequence",
  "params": {
    "id": "iesds",
    "callouts": [
      { "subject": "pd:cell:1,0", "text": "Defection beats cooperation." },
      { "subject": "pd:cell:0,1", "text": "Symmetric on P2's side." },
      { "subject": "pd:cell:1,1", "text": "Both defect — Nash equilibrium." }
    ],
    "hold_each": "slow",
    "transition": "fast",
    "style": "neon"
  }
}
```

Required: `id`, `callouts` (1–12 items; each needs `text` plus `anchor`
or `subject`). Optional `hold_each` / `transition` (timing keys),
`style` (one of the six callout styles), `timing`, `role`.

The sequence's `id` is the top-level handle — `removeComponent(target=id)`
cancels remaining callouts. Inner callouts auto-inherit color from
their subject if no `color` is given.

---

### `setRole`
Change the role of an existing component. The new role takes effect on the
next event; restage moves the cast accordingly (Phase 2 / PR G+).

```json
{
  "at": 6.0,
  "action": "setRole",
  "params": { "target": "kpis", "role": "supporting", "timing": "fast" }
}
```

Required: `target` (id of an earlier-declared component), `role` (one of
the six role values). Optional `timing` controls the restage motion. See
the **Roles** section for the role vocabulary and when to use each.

---

### `bestResponseArrow`
Draw an arrow between two PayoffMatrix cells, colored by actor. Used to
visualize a player's best response ("given opponent plays X, I prefer Y").

```json
{
  "at": 9.0,
  "action": "bestResponseArrow",
  "params": {
    "id": "br-a",                  // optional
    "target": "pd",
    "from": [0, 0], "to": [0, 1],
    "actor": "actor_a", "timing": "normal"
  }
}
```

Required: `target`, `from` ([row, col]), `to` ([row, col]), `actor` (palette key).
Optional `id` exposes the arrow as a top-level id.

---

## Layouts

Pick a layout that fits the composition. Format-only layouts come in pairs —
use the right name for the format. The validator rejects mismatches.

| Name         | Format(s)            | Slots                  | Use for |
|--------------|----------------------|------------------------|---------|
| `hero`       | horizontal, vertical | `main`                 | One focal element |
| `split`      | horizontal           | `left`, `right`        | Two side-by-side panels |
| `stacked`    | vertical             | `top`, `bottom`        | Vertical twin of `split` |
| `data-left`  | horizontal           | `data` (small), `body` (large) | Stat sidebar + main content |
| `data-top`   | vertical             | `data` (top), `body` (rest) | Vertical twin of `data-left` |
| `trio`       | horizontal           | `A`, `B`, `C` (3 columns) | Three parallel comparisons |
| `trio-stack` | vertical             | `A`, `B`, `C` (3 rows) | Vertical twin of `trio` |
| `title-body` | horizontal, vertical | `title` (top strip), `body` | Chapter card + content beneath |

**Picking the right layout:** for two-element compositions in horizontal use
`split`; in vertical use `stacked`. The format-only design forces explicit
choice — anchors auto-flip lateral direction (`right-of` → `below` in vertical),
but layout *names* don't.

**Anti-pattern — two sequential TextCards in `title-body`.**
A `title-body` scene with a TextCard in `title` AND a sequential TextCard
in `body` reads jarringly: while only one slot is occupied (the title
appears first or the body appears alone), the lone-slot auto-reflow
centers the surviving text in the full frame. When the second text fades
in, the first jumps to its real slot to make room. When the second
fades out, the first jumps back to center. With two text elements the
positional flicker is visible.

Prefer one of these patterns for sequential intro text:

1. **Sequential cards in a single `hero` slot** (recommended for clean
   intro/outro pairs):
   ```json
   { "slots": { "main": { "at": 0.0, "action": "showTextCard",
       "params": { "id": "title", "text": "Title", "size": "title" } } },
     "overlays": [
       { "at": 5.0, "action": "removeComponent", "params": { "target": "title" } },
       { "at": 6.0, "action": "showTextCard", "params": {
           "id": "subtitle", "slot": "main",
           "text": "Subtitle.", "size": "body" } },
       { "at": 10.0, "action": "removeComponent", "params": { "target": "subtitle" } }
     ] }
   ```

2. **Title-body kept with non-text body content.** The reflow looks fine
   when the body element is a stat, chart, or matrix — the visual weight
   difference between the title strip and the body block masks the
   transition. The flicker is only painful with two text-on-text beats.

3. **A `title-body` chapter card** (title pinned for a long beat as
   multiple body components cycle below it) is the original use case —
   keep using `title-body` here.

---

## How to add a new action to this file

When a new component or action lands:

1. Append a section under the right heading (`Component actions` or
   `Generic actions`).
2. Show one minimal JSON example.
3. List required params in prose.
4. Note any non-default behaviors (auto-flips, format-only restrictions, etc.).

The schema is the contract; this file is the LLM's reference. Both must say
the same thing.


---

## Placement reference

Every show event needs a slot binding so the layout solver can place it.

### `params.slot` — explicit slot binding

Any show event (slots block, overlays, timeline) can set `slot` to
target a named slot of the active layout:

```json
{ "action": "showStatBlock",
  "params": { "id": "kpi", "value": 42, "label": "USA", "slot": "data" } }
```

Required when:
- The component is in `overlays` or `timeline` and you want it in a
  slot OTHER than the layout's default content slot.
- Multiple overlay components in a single beat each go to different
  slots (e.g. a LineChart in `left` and a GameTree in `right` under
  the `split` layout).

### Auto-bind to PRIMARY_SLOT

When an overlay show event has no `slot`, no `anchor`, AND no
`subject`, the runner auto-binds it to the layout's primary content
slot:

| Layout       | Primary slot |
|--------------|--------------|
| `hero`       | `main`       |
| `split`      | `left`       |
| `stacked`    | `top`        |
| `data-left`  | `body`       |
| `data-top`   | `body`       |
| `trio`       | `A`          |
| `trio-stack` | `A`          |
| `title-body` | `body`       |

So a bare `showStatBlock` overlay in a `hero` layout lands in `main`
without any extra params.

### Callouts: `anchor` vs `subject`

Both `showCalloutBox` modes now produce the same reflow + color +
leader behavior. Pick whichever fits the source:

- **`anchor: "right-of:pd"`** — author commits to a side. The token
  determines which side the callout takes.
- **`subject: "pd"` or `subject: "pd:cell:1,0"`** — author commits to
  a target. The solver picks the side based on layout direction
  (horizontal → right/left; vertical → below/above). Refined subjects
  like `pd:cell:1,0` also drive color inheritance (cell dominance
  determines actor color).

Both modes:
- inherit the host's slot (host shrinks to make room),
- inherit the host's `palette_color` for the border,
- re-anchor the leader after every restage.

### `setLayout` swaps the active layout

```json
{ "at": 12.0, "action": "setLayout",
  "params": { "layout": "split", "timing": "normal" } }
```

Components from the slots block whose slot disappears on the new
layout are auto-hidden (role=hidden, slot=None). To bring them back,
swap to a layout with that slot and `setRole(target, primary)`.

### Lone primary doesn't scale

When a slot has exactly one visible primary or hero member and no
subject annotation, the runner centers the mobject at the slot's
center WITHOUT scaling it. This stops tall titles from being shrunk
to fit short slots. Supporting/ambient roles, multi-member slots, and
slots with subject annotations all flex normally.

### Auto-reflow when one slot is occupied

If exactly one slot of a multi-slot layout has visible members (e.g.
`title-body` with the title removed), the content reflows into the
full frame minus a 0.4-unit padding. Authors don't need to switch
layouts mid-scene when they remove a slot's content — the lone slot
expands automatically.

### Debug from the terminal

```bash
# Manim-free dry-run — see every event's solver plan
python scripts/manim/debug_replay.py scripts/manim/<scene>.json

# Full render with per-event trace
GEOPOAI_DEBUG=1 python pipeline/render.py scripts/manim/<scene>.json <name>

# Filter the trace (Manim's progress bars use \r)
GEOPOAI_DEBUG=1 python pipeline/render.py <scene> <name> 2> trace.log
tr '\r' '\n' < trace.log | grep -E "^(\[restage\]|    )"
```

---

# Wave-1 additions (W10)

## W10 — manim quality fragment

SKILL.md additions for the W10 lane. The lead merges these into the matching
sections of `manim_renderer/docs/SKILL.md` at integration; do not hand-edit
SKILL.md from a feature lane.

---

### Component actions

#### `showIcon`

A provisioned SVG glyph or country flag, brand-tinted with an optional glow.
Icons are loaded from packs under `assets/icons/<pack>/` (provisioned via
`tools/prepare_assets.py`); they are never downloaded ad hoc.

```json
{
  "at": 1.0,
  "action": "showIcon",
  "params": {
    "id": "ic-shield",
    "icon": "shield",          // bare name -> lucide pack; "flag:ma" -> circle-flags (ma.svg)
    "color": "highlight",      // palette role/key; tints single-color glyphs (ignored for flags)
    "glow": true,              // optional soft halo using token glow radii/opacity
    "size": "large",           // small | medium | large (FONT_SCALE-relative height)
    "timing": "normal",
    "effect": "fade-in",
    "role": "primary"
  }
}
```

- **Addressing.** `icon: "globe"` → the default `lucide` outline pack;
  `icon: "flag:ma"` → the `circle-flags` pack (`ma.svg`). The loader searches the
  pack recursively, so packs that nest under a subdir (lucide → `icons/`) work.
- **Tint.** `color` is a palette role token (`highlight` / `contested` /
  `neutral`, which also carry a matched glow hue) or any palette key
  (`actor_a`, `positive`, …). Flags are intentionally multi-color and are **not**
  tinted.
- **Glow.** `glow: true` renders a halo behind the glyph from `tokens.glow`
  (`halo_px` / `halo_opacity`). Pairs naturally with role tokens.
- **Size.** Glyph height is a multiple of the format's title type size, so icons
  sit consistently beside text. Place via `slot` or `anchor` like any component.

#### `showImageCard`

A framed raster image with a slow, continuous Ken Burns drift and a mandatory
attribution chip. Episode images live under repo-root `assets/images/`; `image`
also accepts an absolute or repo-root-relative path.

```json
{
  "at": 0.0,
  "action": "showImageCard",
  "params": {
    "id": "img-1",
    "image": "assets/images/ukraine_front.jpg",  // path (assets/images/ is the episode convention)
    "source": "Maxar / 2024",   // REQUIRED — rendered as a small credit chip
    "width": 7.0,               // frame size in Manim units (height follows image aspect if omitted)
    "direction": "in",          // in | out | left | right | up | down (drift direction)
    "zoom": 0.08,               // Ken Burns punch amount (fraction)
    "size": "medium",           // small | medium | large (default frame height when width/height omitted)
    "mask": "country:ukraine",  // OPTIONAL — accepted but deferred to the map renderer; here frame is rounded
    "timing": "slow",
    "effect": "fade-in",
    "role": "primary"
  }
}
```

- **Never static.** The image continuously pans/zooms (ping-pong) for the whole
  time it is on screen — there is no static-image mode.
- **`source` is mandatory.** Every image is credited; the string renders as a
  caption-size chip in the bottom-right of the frame.
- **`mask: "country:<name>"`** is accepted for forward-compat but is handled by
  the map renderer; the Manim card frames rectangular/rounded only.
- The overscan from the drift is hidden by an internal matte, so the image never
  bleeds past its frame.

---

### Safe areas (platform margins + caption band)

Short-form platforms overlay UI on the video. Two **independent** reserved
regions are derived from `tokens.safe_areas[format]`:

| Region | Protects against | Token |
|---|---|---|
| `platform_margins` | platform UI chrome (e.g. the 9:16 right rail) | `safe_areas[fmt].platform_margins` |
| `caption_band` | layout reservation during render (keep components out of the strip) | `safe_areas[fmt].caption_band` |

The renderer keeps **every** component (slot-placed, subject/anchored callouts
included) out of the enabled regions, at stage time, on top of the layout
solver. Geometry lives in the tokens; whether each region applies is **policy**:

- **Defaults are format-derived:** vertical (Shorts) → both on; horizontal
  (long-form) → both off (full-frame symmetry preserved).
- **Per-scene override** (escape hatch):

  ```json
  "scene": { "layout": "hero", "duration": 30,
             "safe_areas": { "platform_margins": true, "caption_band": false } }
  ```

**Independent of caption burn-in:** episode `caption_policy` (W15/W17/W20)
controls whether ASS subtitles are burned in post — default `broll_only`.
`caption_band` does **not** auto-toggle with caption policy; operators set
each independently (e.g. reserve the band on vertical even when burn-in is
`broll_only`, or disable the band on a scene that uses full-frame layout).

---

### Pacing lint (validator warnings)

`schema/validator.py` now emits non-fatal **warnings** (stderr during validate;
also returned by `pacing_warnings(scene)`). They never change the valid/invalid
verdict — a scene can be valid yet poorly paced. Thresholds come from the timing
tokens (`BEATS`):

| Warning | Fires when |
|---|---|
| `[pacing-static]` | a gap with no visual change exceeds `static_max_s` |
| `[pacing-callout]` | a callout is on screen shorter than `max(callout_min_s, chars / read_rate_cps)` |
| `[pacing-entrances]` | more than 3 components enter at the same `at` |
| `[pacing-stagger]` | two entrances are spaced by a positive gap smaller than `stagger_ms` |

`scripts/manim/qa_pacing_bad.json` is a committed scene that deliberately fires
all four.

---

### Sidecar files (events + layout)

Every Manim render writes two sidecars next to the MP4
(`output/manim/<clip>.mp4`), consumed by the composition lanes:

- **`<clip>.events.json`** — one cue per dispatched action
  (`docs/contracts/events.schema.json`). Action → event `type` is mapped
  (show* → `label`/`counter`/`callout`/`image`, mutations → `highlight`/`arrow`,
  `removeComponent` → `remove`, `setLayout` → `camera`). `intensity` is derived
  from role (hero/primary 0.8, supporting 0.5, ambient 0.2). Feeds W16 sound.
- **`<clip>.layout.json`** — normalized component bounding boxes
  (`docs/contracts/layout.schema.json`), top-left origin, resampled to a fixed
  `sample_hz` (2) grid over the clip, captured at every composition change.
  Feeds W15 occupancy-aware captions.

Escape-hatch clips also write **`<clip>.meta.json`** (`reason`, `file_hash`,
`duration`, `class`) and **skip `layout.json`** (no slot occupancy).

---

## Escape hatch — guarded custom Manim (last resort)

Use only when **no component action** can express the visual (e.g. a bespoke
circular flywheel with curved inter-node arrows). The component-JSON path
(`slots` / `overlays` / `timeline`) stays the default; an escape scene
**replaces** that model — do not mix them.

```json
{
  "renderer": "manim",
  "format": "horizontal",
  "quality": "preview",
  "scene": { "duration": 8 },
  "escape_hatch": {
    "file": "escape_hatch/custom_scenes/<name>.py",
    "class": "<SceneClassName>",
    "reason": "Mandatory — why components were insufficient"
  }
}
```

Optional `escape_hatch.timeout_s` (default 300). Render and outputs are normal:
`python pipeline/render.py scripts/manim/<scene>.json <clip>` →
`output/manim/<clip>.mp4` + `.events.json` + `.meta.json`.

**Author** `manim_renderer/escape_hatch/custom_scenes/<name>.py`:

- Subclass `EscapeHatchScene` (`manim_renderer.escape_hatch.base`).
- Implement `build()` — **not** `construct()`; scene start/end chapter cues are
  automatic. Use Manim mobjects/animations (`Circle`, `CurvedArrow`, `FadeIn`, …).
- Colors via `manim_renderer.theme.palette` (`UI`, `SEMANTIC`) — **no hex literals**.
- Fonts via `manim_renderer.theme.typography.FONTS` — **no font-name strings**.
- Timing via `manim_renderer.theme.timing.TIMING`.
- Extra sound cues: `self.emit("insight", 0.6, id="my-cue")`.

**Guard** (`guard.py`) statically lints the file before render and hard-fails on
hex/font literals, a class that doesn't subclass `EscapeHatchScene`, or any import
outside `{manim, manim_renderer.theme, manim_renderer.escape_hatch, tools.tokens,
math, numpy, json}` (bans `os`, `sys`, `subprocess`, `pathlib`, networking, …). The
scene then renders in a subprocess (temp cwd, `timeout_s` cap) and each use is logged
to `escape_hatch/usage_log.jsonl` (`reason` + file hash).

> The guard enforces brand discipline + hygiene; it is **not** an adversarial
> sandbox — author escape scenes yourself, don't run untrusted code through it.

**Promotion rule:** if the same bespoke pattern recurs in **3+ episodes**, promote
it to a real component — don't keep growing the hatch.

Example: `scripts/manim/qa_escape.json` → `escape_hatch/custom_scenes/incentive_flywheel.py`.
Full operator notes: `manim_renderer/escape_hatch/README.md`.

