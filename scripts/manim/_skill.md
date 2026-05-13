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
    "color": "highlight",          // optional bubble text color (palette key)
    "timing": "normal",
    "effect": "fade-in"            // bubble fades, then leader draws
  }
}
```

Required: `id`, `text`, `anchor`.
Custom anchors exposed: `head` (leader tip) and `tail` (leader root) — useful
when chaining callouts. Long text auto-wraps to fit `width`.
Format-aware: in vertical scenes, `right-of`/`left-of` flip to `below`/`above`
for both the bubble position AND the leader endpoints.

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

### `removeComponent`
Fade or dissolve an existing component out and unregister its id.

```json
{
  "at": 8.0,
  "action": "removeComponent",
  "params": { "target": "matrix-1", "effect": "fade-out", "timing": "fast" }
}
```

Required: `target` (id of an earlier-declared component).
Default effect: `fade-out`. Default timing: `fast`.

---

### `highlightCell`
Lay a translucent colored overlay on a PayoffMatrix cell. Target must be a
PayoffMatrix.

```json
{
  "at": 6.0,
  "action": "highlightCell",
  "params": { "target": "pd", "index": [1, 1], "color": "highlight", "timing": "fast" }
}
```

Required: `target`, `index` ([row, col]). `color` defaults to `highlight`.
**Phase 1 limit:** the overlay is ephemeral — it has no id, so it can't be
removed via `removeComponent`. To "clear" a highlight, overlay a different
color or design around the limitation.

---

### `crossOut`
Strike a line through a PayoffMatrix row or column. Used for iterated
elimination of strictly dominated strategies (IESDS).

```json
{
  "at": 8.0,
  "action": "crossOut",
  "params": { "target": "pd", "axis": "row", "index": 0, "style": "strike" }
}
```

Required: `target`, `axis` (`"row"` | `"col"`), `index` (0-based).
`style` is `"strike"` (default, solid) or `"dashed"`. Line is `negative` (red).

---

### `bestResponseArrow`
Draw an arrow between two PayoffMatrix cells, colored by actor. Used to
visualize a player's best response ("given opponent plays X, I prefer Y").

```json
{
  "at": 9.0,
  "action": "bestResponseArrow",
  "params": {
    "target": "pd",
    "from": [0, 0], "to": [0, 1],
    "actor": "actor_a", "timing": "normal"
  }
}
```

Required: `target`, `from` ([row, col]), `to` ([row, col]), `actor` (palette key).

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
