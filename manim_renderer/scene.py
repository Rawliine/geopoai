"""JSONScene — the Manim runner that interprets a validated scene dict."""

from __future__ import annotations

from manim import MovingCameraScene

from manim_renderer.layouts.resolver import resolve_layout
from manim_renderer.registry import REGISTRY


class JSONScene(MovingCameraScene):
    """Class attribute scene_data is set by the wrapper before render()."""

    scene_data: dict = {}

    def construct(self):
        scene = self.scene_data
        fmt = scene.get("format", "horizontal")
        duration = float(scene.get("scene", {}).get("duration", 0.0))
        layout_name = scene.get("scene", {}).get("layout", "hero")

        self._layout = resolve_layout(layout_name, fmt)
        self._id_to_mobject: dict = {}

        events = self._collect_events(scene)

        cursor = 0.0
        for slot_name, ev in events:
            at = float(ev["at"])
            if at > cursor:
                self.wait(at - cursor)
                cursor = at

            action = ev["action"]
            params = ev.get("params", {})
            ComponentCls = REGISTRY.get(action)
            if ComponentCls is None:
                raise ValueError(f"unknown action in registry: {action!r}")

            component = ComponentCls(params, format=fmt)

            if slot_name is not None:
                rect = self._layout.slot(slot_name)
                component.move_to(rect.center)

            if component.id:
                self._id_to_mobject[component.id] = component

            anim = component.entrance(
                params.get("effect", "fade-in"),
                params.get("timing", "normal"),
            )
            self.play(anim)
            cursor = at + (anim.run_time or 0.0)

        if duration > cursor:
            self.wait(duration - cursor)

    @staticmethod
    def _collect_events(scene: dict) -> list[tuple[str | None, dict]]:
        """Yield (slot_name_or_None, event) tuples sorted by 'at'."""
        events: list[tuple[str | None, dict]] = []
        for slot_name, ev in (scene.get("slots") or {}).items():
            events.append((slot_name, ev))
        for ev in scene.get("overlays") or []:
            events.append((None, ev))
        for ev in scene.get("timeline") or []:
            events.append((None, ev))
        events.sort(key=lambda pair: float(pair[1].get("at", 0.0)))
        return events
