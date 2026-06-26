"""Base scene for escape-hatch custom Manim clips.

Wires brand theme, format, safe areas, and events.json emission. Subclasses
implement ``build()``; ``construct()`` handles scene-start/end cues.
"""

from __future__ import annotations

from manim import MovingCameraScene

from manim_renderer.theme.safe_area import resolve_safe_area_policy


class EscapeHatchScene(MovingCameraScene):
    """Class attribute ``scene_data`` is set by the runner before render()."""

    scene_data: dict = {}

    def construct(self) -> None:
        scene = self.scene_data
        self._format = scene.get("format", "horizontal")
        self._duration = float(scene.get("scene", {}).get("duration", 5.0))
        self._safe_margins, self._safe_band = resolve_safe_area_policy(scene)
        self.emitted_events: list[dict] = []
        self._event_clock = 0.0

        self.camera.background_color = self._background_color()

        self.emit("chapter", 0.3, id="scene-start", phase="start", t=0.0)
        self.build()
        self.emit("chapter", 0.3, id="scene-end", phase="end", t=self._duration)
        remaining = self._duration - self._event_clock
        if remaining > 0:
            self.wait(remaining)

    def build(self) -> None:
        """Override in custom scenes — draw bespoke visuals here."""
        raise NotImplementedError

    def _background_color(self) -> str:
        from manim_renderer.theme.palette import UI

        return UI["background"]

    def emit(
        self,
        event_type: str,
        intensity: float,
        *,
        id: str | None = None,
        phase: str = "start",
        t: float | None = None,
    ) -> None:
        """Append one events.json cue. ``t`` defaults to the internal clock."""
        if t is None:
            t = self._event_clock
        ident = id or f"{event_type}-{len(self.emitted_events)}"
        self.emitted_events.append({
            "t": round(float(t), 4),
            "type": event_type,
            "phase": phase,
            "intensity": max(0.0, min(1.0, float(intensity))),
            "id": str(ident),
        })

    def wait(self, duration: float = 1.0) -> None:
        super().wait(duration)
        self._event_clock += float(duration)

    def play(self, *anims, **kwargs) -> None:
        super().play(*anims, **kwargs)
        run_time = kwargs.get("run_time")
        if run_time is None and anims:
            run_time = getattr(anims[0], "run_time", 0.0)
        self._event_clock += float(run_time or 0.0)
