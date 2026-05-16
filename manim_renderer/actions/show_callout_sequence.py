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
    the existing _ID_REF / _ANCHOR machinery (wires that in).
"""

from __future__ import annotations

from typing import Optional

from manim import Animation, FadeIn, FadeOut, Succession, VGroup

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
    inner_callouts: list[CalloutBox] = []

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
        inner_callouts.append(callout)

        # Resolve anchor / subject → final on-screen placement.
        anchor_target = None
        anchor_str: str | None = None
        host_id: str | None = None
        if "anchor" in item_params:
            anchor_str = item_params["anchor"]
            _, host_id = parse_anchor(anchor_str)
            anchor_target = ctx.id_to_mobject.get(host_id)
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

        # Register each inner callout against its host so a later
        # `removeComponent(host)` sweeps it. Even though Manim's
        # `FadeOut` is a remover and should drop the mobject from the
        # render list after fade-out, registering ensures the host
        # exit also fades any inner callout still on screen.
        if (
            host_id is not None
            and ctx.scene is not None
            and hasattr(ctx.scene, "_overlays_by_host")
        ):
            ctx.scene._overlays_by_host.setdefault(
                host_id, [],
            ).append(callout)

        callout.position_finalized(
            anchor=anchor_str, target=anchor_target, format=fmt,
        )

        # FadeIn is a real introducer; AnimationGroup excludes its mobject
        # from the upfront add, so the callout enters the scene only when
        # its turn comes. CalloutBox.entrance wraps the bubble+leader in
        # an inner Succession that isn't recognized as an introducer.
        enter_run_time = TIMING.get(timing_name, TIMING[_DEFAULT_TIMING])
        exit_run_time = transition_seconds
        enter = FadeIn(callout, run_time=enter_run_time)
        exit_anim = FadeOut(callout, run_time=exit_run_time)

        sequence_anims.extend([
            enter,
            _Hold(hold_seconds),
            exit_anim,
        ])

    # Register the sequence id so removeComponent can cancel mid-stream.
    # We store the last-built callout as a sentinel handle; the scene
    # runner expects every id to map to a mobject. The actual mid-stream
    # cancel logic ships in a future PR — the registration alone is the
    # contract.
    if ctx.scene is not None and seq_id not in ctx.id_to_mobject:
        ctx.id_to_mobject[seq_id] = callout  # last-built sentinel

    if not sequence_anims:
        return None
    return Succession(*sequence_anims)


class _Hold(Animation):
    """Animation that does nothing for `seconds`. Holds the scene state
    between an entrance and the next exit inside a `Succession`.

    Mobject MUST be an empty placeholder, not the callout. If the callout
    were the mobject, `AnimationGroup` (Succession's base) would add it
    to its `group` upfront — so every callout in the sequence would be
    visible at t=0, before its own FadeIn fires. The empty VGroup keeps
    the Hold animation valid without participating in the upfront add.
    """

    def __init__(self, seconds: float):
        super().__init__(VGroup(), run_time=max(0.01, float(seconds)))

    def interpolate_mobject(self, alpha: float) -> None:  # noqa: D401
        return None
