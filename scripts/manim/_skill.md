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

## Layouts

| Name     | Format(s)         | Slots         |
|----------|-------------------|---------------|
| `hero`   | horizontal, vertical | `main`     |

PR 1.1 adds: `split` (horizontal), `stacked` (vertical), `data-left`/`data-top`,
`trio`/`trio-stack`, `title-body`.

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
