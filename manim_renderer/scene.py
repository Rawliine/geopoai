"""JSONScene — the Manim runner that interprets a validated scene dict."""

from manim import MovingCameraScene

from manim_renderer.registry import REGISTRY


class JSONScene(MovingCameraScene):
    """Reads scene dict from self.scene_data, plays its timeline."""

    scene_data: dict = {}

    def construct(self):
        scene = self.scene_data
        fmt = scene.get("format", "horizontal")
        duration = float(scene.get("scene", {}).get("duration", 0.0))

        events = self._collect_events(scene)
        self._id_to_mobject: dict = {}

        cursor = 0.0
        for ev in events:
            at = float(ev["at"])
            if at > cursor:
                self.wait(at - cursor)
                cursor = at

            action = ev["action"]
            params = ev.get("params", {})
            ComponentCls = REGISTRY.get(action)
            if ComponentCls is None:
                raise ValueError(f"Unknown action in registry: {action}")

            component = ComponentCls(params, format=fmt)
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
    def _collect_events(scene: dict) -> list[dict]:
        events: list[dict] = []
        for slot_name, ev in (scene.get("slots") or {}).items():
            events.append(ev)
        events.extend(scene.get("overlays") or [])
        events.extend(scene.get("timeline") or [])
        events.sort(key=lambda e: float(e.get("at", 0.0)))
        return events
