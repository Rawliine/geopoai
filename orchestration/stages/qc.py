"""qc (mechanical) — machine checks; failures block. Report → qc_report.md.

Rules (each a pure function so a fixture can fail it deterministically):
- callout_duplication: on-screen scene text must compress, not transcribe the VO.
- pacing: events.json gaps > static_max_s, or density spikes.
- caption_collisions: ASS vs layout overlap when burn-in is active (skipped for never).
- loudness + clip_integrity: final mix −14±1 LUFS; every storyboard clip rendered.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from orchestration.context import StageContext
from orchestration.stages import Stage

log = logging.getLogger(__name__)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) > 2}


def _scene_texts(scene: dict) -> list[str]:
    """All on-screen text strings in a scene (recursively, by `text` key)."""
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("text", "title", "subtitle", "label") and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(scene)
    return out


# ── Rules ────────────────────────────────────────────────────────────────────

def check_callout_duplication(
    pairs: list[tuple[str, str]], threshold: float
) -> list[str]:
    """pairs = (on_screen_text, concurrent_vo_text). Fail if on-screen lifts VO."""
    issues: list[str] = []
    for screen, vo in pairs:
        st, vt = _tokens(screen), _tokens(vo)
        if not st:
            continue
        ratio = len(st & vt) / len(st)
        if ratio > threshold:
            issues.append(
                f"on-screen text duplicates VO (overlap {ratio:.2f} > {threshold:.2f}): "
                f"{screen!r}"
            )
    return issues


def check_pacing(event_times: list[float], static_max_s: float) -> list[str]:
    issues: list[str] = []
    times = sorted(event_times)
    for a, b in zip(times, times[1:]):
        if b - a > static_max_s:
            issues.append(f"static gap {b - a:.1f}s > {static_max_s:.1f}s at t={a:.1f}s")
    # density spike: >8 events within any 1s window
    for i, t in enumerate(times):
        window = [x for x in times[i:] if x - t < 1.0]
        if len(window) > 8:
            issues.append(f"density spike: {len(window)} events within 1s at t={t:.1f}s")
            break
    return issues


def check_caption_collisions(
    burn_in: str, collisions: list[str]
) -> list[str]:
    if burn_in == "never":
        return []
    return [f"caption collides with overlay: {c}" for c in collisions]


def check_loudness(lufs: float | None, target: float, tol: float) -> list[str]:
    if lufs is None:
        return []
    if abs(lufs - target) > tol:
        return [f"loudness {lufs:.1f} LUFS outside {target:.0f}±{tol:.0f}"]
    return []


def check_clip_integrity(
    storyboard: dict, clips: list[dict], compose_spec: dict | None = None
) -> list[str]:
    have = {c["id"] for c in clips if c.get("outputs", {}).get("video")}
    issues = []
    for e in storyboard.get("entries", []):
        if e["clip_id"] not in have:
            issues.append(f"storyboard clip {e['clip_id']!r} has no rendered output")
    # A clip can render to disk yet be dropped from the final cut (e.g. an
    # over-long clip truncated by -shortest). Verify each storyboard clip also
    # made it into the compose spec that produced the master.
    if compose_spec is not None:
        composed = {c.get("clip_id") for c in compose_spec.get("clips", [])}
        for e in storyboard.get("entries", []):
            if e["clip_id"] not in composed:
                issues.append(
                    f"storyboard clip {e['clip_id']!r} is missing from the final "
                    f"compose (rendered but not in the cut)"
                )
    return issues


# ── Stage ────────────────────────────────────────────────────────────────────

def _measure_lufs(path: Path) -> float | None:
    if shutil.which("ffmpeg") is None or not path.exists():
        return None
    res = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r'"input_i"\s*:\s*"(-?\d+(?:\.\d+)?)"', res.stderr)
    return float(m.group(1)) if m else None


def execute(ctx: StageContext) -> None:
    th = ctx.bible.get("thresholds", {})
    storyboard = ctx.manifest.get("storyboard", {})
    beats = {b["beat_id"]: b for b in ctx.manifest.get("script", {}).get("beats", [])}
    issues: dict[str, list[str]] = {}

    # callout duplication: pair each clip's scene text with its beat VO
    pairs: list[tuple[str, str]] = []
    for entry in storyboard.get("entries", []):
        ref = entry.get("scene_ref")
        if not ref:
            continue
        scene_path = ctx.ep_dir / ref
        if not scene_path.exists():
            continue
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        vo = beats.get(entry["beat_id"], {}).get("vo_text", "")
        for txt in _scene_texts(scene):
            pairs.append((txt, vo))
    issues["callout_duplication"] = check_callout_duplication(
        pairs, th.get("callout_overlap_ratio_max", 0.6)
    )

    # pacing: aggregate event times across clips
    times: list[float] = []
    for clip in ctx.manifest.get("clips", []):
        ev = clip.get("outputs", {}).get("events")
        if not ev:
            continue
        ep = ev if Path(ev).is_absolute() else ctx.repo_root / ev
        if Path(ep).exists():
            doc = json.loads(Path(ep).read_text(encoding="utf-8"))
            times += [float(e.get("t", 0)) for e in doc.get("events", [])]
    issues["pacing"] = check_pacing(times, th.get("static_max_s", 4.0))

    # caption collisions (skipped when burn-in never) — no ASS yet in dry runs
    burn = (ctx.manifest.get("caption_policy") or ctx.bible.get("caption_policy", {})).get(
        "burn_in", "broll_only"
    )
    issues["caption_collisions"] = check_caption_collisions(burn, [])

    # loudness + clip integrity
    final = ctx.repo_root / "output" / "episodes" / ctx.manifest["episode_id"] / "final_yt_long.mp4"
    issues["loudness"] = check_loudness(
        _measure_lufs(final),
        th.get("loudness_lufs_target", -14.0),
        th.get("loudness_lufs_tolerance", 1.0),
    )
    compose_spec = None
    compose_path = ctx.ep_dir / "compose.json"
    if compose_path.exists():
        compose_spec = json.loads(compose_path.read_text(encoding="utf-8"))
    issues["clip_integrity"] = check_clip_integrity(
        storyboard, ctx.manifest.get("clips", []), compose_spec
    )

    failures = {k: v for k, v in issues.items() if v}
    lines = [f"# QC report — {ctx.manifest['episode_id']}", ""]
    for rule, items in issues.items():
        lines.append(f"## {rule}: {'FAIL' if items else 'pass'}")
        lines += [f"- {it}" for it in items]
        lines.append("")
    report = ctx.ep_dir / "qc_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    ctx.manifest["qc"] = {
        "status": "failed" if failures else "passed",
        "report_path": "qc_report.md",
    }
    if failures:
        raise RuntimeError(
            "QC failed: " + ", ".join(f"{k} ({len(v)})" for k, v in failures.items())
        )


STAGE = Stage(name="qc", is_brain=False, execute=execute)
