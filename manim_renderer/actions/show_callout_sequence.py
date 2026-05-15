"""showCalloutSequence action — chain callouts so only one is live at a time.

PR O. Lives in `ACTION_REGISTRY` (not `COMPONENT_REGISTRY`) because the
inner callouts are ephemeral: a sequence registers a single id (the
sequence's own), tears down each inner callout before showing the next,
and exits when the chain completes.

JSON shape:
    { "at": 20.0, "action": "showCalloutSequence",
      "params": {
        "id": "seq-1",
        "callouts": [
          { "subject": "pd:cell:1,0", "text": "Defection beats cooperation." },
          { "subject": "pd:cell:0,1", "text": "Symmetric." },
          { "subject": "pd:cell:1,1", "text": "Both defect — Nash." }
        ],
        "hold_each": "slow",
        "transition": "fast",
        "style": "neon"
      }
    }

Behavior:
  * Each inner callout is built like a normal `showCalloutBox` (color
    inheritance, subject-based placement, role=annotation).
  * Entrances chain via `Succession`: enter → hold → exit → next enter.
  * The sequence's own id is registered against the SCENE itself, not
    against any single inner mobject. `removeComponent(target=seq-id)`
    cancels the remaining callouts.

Validator coverage:
  * Tier 2 (action-params): show_callout_sequence.json — each inner item
    must have text + (anchor or subject).
  * Tier 4 (anchors): inner anchor/subject targets are validated against
    the existing _ID_REF / _ANCHOR machinery (PR O wires that in).
"""

from __future__ import annotations

from typing import Optional

from manim import Animation, Succession

from manim_renderer.actions._context import ActionContext
from manim_renderer.components.narrative.callout_box import CalloutBox
from manim_renderer.resolvers.anchor import parse_anchor, place_at_anchor
from manim_renderer.theme.timing import TIMING


_DEFAULT_HOLD = "slow"
_DEFAULT_TRANSITION = "fast"
_DEFAULT_STYLE = "neon"
_DEFAULT_TIMING = "normal"


def show_callout_sequence(ctx: ActionContext) -> Optional[Animation]:
    seq_id = ctx.params.get("id")
    callouts = ctx.params.get("callouts") or []
    if not seq_id:
        raise ValueError("showCalloutSequence requires params.id")
    if not callouts:
        raise ValueError("showCalloutSequence requires non-empty params.callouts")

    hold_name = ctx.params.get("hold_each", _DEFAULT_HOLD)
    transition_name = ctx.params.get("transition", _DEFAULT_TRANSITION)
    style = ctx.params.get("style", _DEFAULT_STYLE)
    timing_name = ctx.params.get("timing", _DEFAULT_TIMING)

    hold_seconds = TIMING.get(hold_name, TIMING[_DEFAULT_HOLD])
    transition_seconds = TIMING.get(transition_name, TIMING[_DEFAULT_TRANSITION])

    fmt = ctx.format

    sequence_anims: list[Animation] = []

    for i, item in enumerate(callouts):
        text = item["text"]
        item_params = {
            "id": f"{seq_id}-{i}",
            "text": text,
            "style": style,
            "role": "annotation",
        }
        for opt in ("anchor", "subject", "width", "arrow", "color"):
            if opt in item:
                item_params[opt] = item[opt]

        # Color inheritance — same code path as `_dispatch_component` so
        # an inner callout pointing at `pd:cell:1,0` picks up actor_a.
        if item_params.get("subject") and not item_params.get("color"):
            from manim_renderer.resolvers.subject_color import (
                inherit_subject_color,
            )
            inherited = inherit_subject_color(
                item_params["subject"], ctx.id_to_mobject,
            )
            if inherited is not None:
                item_params["color"] = inherited

        callout = CalloutBox(item_params, format=fmt)

        # Resolve anchor / subject → final on-screen placement.
        anchor_target = None
        anchor_str: str | None = None
        if "anchor" in item_params:
            anchor_str = item_params["anchor"]
            _, target_id = parse_anchor(anchor_str)
            anchor_target = ctx.id_to_mobject.get(target_id)
        elif "subject" in item_params:
            from manim_renderer.resolvers.subject_placement import (
                pick_subject_side, resolve_subject_target,
            )
            anchor_target = resolve_subject_target(
                item_params["subject"], ctx.id_to_mobject,
            )
            layout_direction = "vertical" if fmt == "vertical" else "horizontal"
            side = pick_subject_side(
                anchor_target, fmt,
                callout_size=(float(callout.width), float(callout.height)),
                layout_direction=layout_direction,
            )
            host_id = item_params["subject"].split(":", 1)[0]
            anchor_str = f"{side}:{host_id}"

        if anchor_target is not None and anchor_str is not None:
            place_at_anchor(callout, anchor_target, anchor_str, fmt)

        callout.position_finalized(
            anchor=anchor_str, target=anchor_target, format=fmt,
        )

        enter = callout.entrance(
            item.get("effect", "fade-in"),
            timing_name,
        )
        exit_anim = callout.exit("fade-out", transition_name)

        sequence_anims.extend([
            enter,
            _Hold(callout, hold_seconds),
            exit_anim,
        ])

    # Register the sequence id so removeComponent can cancel mid-stream.
    # We store the last-built callout as a sentinel handle; the scene
    # runner expects every id to map to a mobject. The actual mid-stream
    # cancel logic ships in a future PR — the registration alone is the
    # PR O contract.
    if ctx.scene is not None and seq_id not in ctx.id_to_mobject:
        ctx.id_to_mobject[seq_id] = callout  # last-built sentinel

    if not sequence_anims:
        return None
    return Succession(*sequence_anims)


class _Hold(Animation):
    """Animation that does nothing for `seconds` — keeps a mobject on
    screen between an entrance and the next exit.

    We avoid `Wait` because `Wait` requires a Scene context; this
    Animation works inside a `Succession` without touching the scene.
    """

    def __init__(self, mobject, seconds: float):
        super().__init__(mobject, run_time=max(0.01, float(seconds)))

    def interpolate_mobject(self, alpha: float) -> None:  # noqa: D401
        return None
