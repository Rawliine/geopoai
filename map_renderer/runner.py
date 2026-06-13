#!/usr/bin/env python3
"""
map_renderer/runner.py
─────────────────────────────────────────────────────────────────────────────
Playwright-based renderer. Opens map.html headlessly, injects the Mapbox
token, waits for tiles, fires a scene JSON, records the output as MP4.
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from map_renderer.resolver import _resolve_scene_countries

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RENDERER_PATH = ROOT / "map_renderer" / "web" / "map.html"
TMP_DIR = ROOT / "tmp"
OUTPUT_DIR = ROOT / "output"

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [render_scene] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("render_scene")

# ── Load .env ──────────────────────────────────────────────────────────────
load_dotenv(ROOT / ".env")
MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN", "")

# Ignore IDE sandbox PLAYWRIGHT_BROWSERS_PATH — often points at a partial Chromium tree.
_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if _browsers_path and "cursor-sandbox-cache" in _browsers_path.replace("\\", "/"):
    del os.environ["PLAYWRIGHT_BROWSERS_PATH"]

if not MAPBOX_TOKEN:
    log.warning(
        "MAPBOX_TOKEN not found in environment. "
        "Create a .env file at the project root with MAPBOX_TOKEN=pk.eyJ1..."
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


@lru_cache(maxsize=1)
def _supports_nvenc() -> bool:
    """Return True if ffmpeg reports h264_nvenc support."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "h264_nvenc" in result.stdout


def _webm_to_mp4(
    webm_path: Path,
    output_path: Path,
    fps: int = 30,
    nvenc_qp: int = 16,
    x264_crf: int = 15,
) -> bool:
    """
    Convert .webm → .mp4 using ffmpeg.
    Returns True on success.
    """
    fps_filter = f"fps={fps}"
    if _supports_nvenc():
        cmd = [
            "ffmpeg", "-y",
            "-i", str(webm_path),
            "-vf", fps_filter,
            "-c:v", "h264_nvenc",
            "-preset", "p7",
            "-tune", "hq",
            "-rc", "constqp",
            "-qp", str(nvenc_qp),
            "-spatial-aq", "1",
            "-temporal-aq", "1",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(webm_path),
            "-vf", fps_filter,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", str(x264_crf),
            "-preset", "slow",
            "-movflags", "+faststart",
            str(output_path),
        ]
    log.info("FFmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("FFmpeg failed:\n%s", result.stderr[-2000:])
        return False
    return True


def _frames_to_mp4(
    frames_dir: Path,
    output_path: Path,
    fps: int = 30,
    nvenc_qp: int = 16,
    x264_crf: int = 15,
) -> bool:
    """Encode frame_%06d.png sequence to mp4."""
    input_pattern = str(frames_dir / "frame_%06d.png")
    if _supports_nvenc():
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", input_pattern,
            "-c:v", "h264_nvenc",
            "-preset", "p7",
            "-tune", "hq",
            "-rc", "constqp",
            "-qp", str(nvenc_qp),
            "-spatial-aq", "1",
            "-temporal-aq", "1",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", input_pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", str(x264_crf),
            "-preset", "slow",
            "-movflags", "+faststart",
            str(output_path),
        ]
    log.info("FFmpeg (frames): %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("FFmpeg frame encode failed:\n%s", result.stderr[-2000:])
        return False
    return True


def _latest_webm(directory: Path) -> Path | None:
    """Return the most recently modified .webm in directory, or None."""
    files = sorted(directory.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None


# ── Core render function ───────────────────────────────────────────────────

async def render_scene(scene: dict, clip_name: str) -> Path:
    """
    Render a single scene JSON to an MP4 clip.
    """
    if not RENDERER_PATH.exists():
        raise FileNotFoundError(f"Renderer not found: {RENDERER_PATH}")

    if not _check_ffmpeg():
        raise FileNotFoundError(
            "ffmpeg not found on PATH. Install with: "
            "sudo apt install ffmpeg  /  brew install ffmpeg"
        )

    scene = _resolve_scene_countries(scene)
    duration = scene.get("duration", 10)
    fps = int(scene.get("_fps", 60))
    nvenc_qp = int(scene.get("_nvenc_qp", 16))
    x264_crf = int(scene.get("_x264_crf", 15))
    deterministic = bool(scene.get("_deterministic", False))
    map_style = scene.get("map_style", "dark")
    tile_timeout = scene.get("_tile_timeout", 20_000)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Rendering clip '%s' (%.1fs, style=%s)", clip_name, duration, map_style)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--ignore-certificate-errors",
                "--ignore-gpu-blocklist",
                "--enable-gpu-rasterization",
                "--enable-zero-copy",
                "--use-angle=vulkan",
            ],
        )

        context_kwargs = {
            "viewport": {"width": 1920, "height": 1080},
        }
        if not deterministic:
            context_kwargs.update(
                {
                    "record_video_dir": str(TMP_DIR),
                    "record_video_size": {"width": 1920, "height": 1080},
                }
            )
        context = await browser.new_context(**context_kwargs)

        page = await context.new_page()

        page.on("console", lambda msg: log.debug("[browser %s] %s", msg.type, msg.text))
        page.on("pageerror", lambda err: log.error("[browser error] %s", err))

        renderer_url = RENDERER_PATH.as_uri()
        log.info("Loading renderer: %s", renderer_url)
        await page.goto(renderer_url, wait_until="domcontentloaded")

        log.info("Injecting Mapbox token and initialising map…")
        await page.evaluate(
            """args => window.init(args.token, { renderMode: true })""",
            {"token": MAPBOX_TOKEN},
        )

        log.info("Waiting for map tiles (timeout=%dms)…", tile_timeout)
        try:
            await page.wait_for_function(
                "window.sceneReady === true",
                timeout=tile_timeout,
            )
        except PWTimeout:
            await context.close()
            await browser.close()
            raise RuntimeError(
                f"Map tiles did not load within {tile_timeout}ms. "
                "Check your MAPBOX_TOKEN and internet connection."
            )
        log.info("Map ready.")

        video_path_obj = None
        frames_dir = TMP_DIR / clip_name / "frames"
        if deterministic:
            total_frames = max(1, int(round(duration * fps)))
            log.info(
                "Deterministic render: %d frames at %dfps (%.2fs).",
                total_frames,
                fps,
                total_frames / fps,
            )
            if frames_dir.parent.exists():
                shutil.rmtree(frames_dir.parent, ignore_errors=True)
            frames_dir.mkdir(parents=True, exist_ok=True)

            scene_meta = await page.evaluate("scene => window.loadScene(scene)", scene)
            log.info("Deterministic scene meta: %s", scene_meta)
            for i in range(total_frames):
                t = min(duration, i / fps)
                state = await page.evaluate("t => window.stepTo(t)", t)
                frame_path = frames_dir / f"frame_{i:06d}.png"
                await page.screenshot(path=str(frame_path))
                if i % max(1, fps * 2) == 0:
                    log.info(
                        "Captured frame %d/%d hash=%s monotonic=%s",
                        i + 1,
                        total_frames,
                        state.get("hash"),
                        state.get("monotonic"),
                    )
        else:
            log.info("Starting scene (%.1fs)…", duration)
            camera_duration = scene.get("camera", {}).get("duration", 2.0) if isinstance(scene.get("camera"), dict) else 2.0
            default_scene_timeout = duration + camera_duration + 20
            scene_timeout = scene.get("_scene_timeout", default_scene_timeout)
            try:
                await asyncio.wait_for(
                    page.evaluate("scene => window.playScene(scene)", scene),
                    timeout=scene_timeout,
                )
            except asyncio.TimeoutError:
                await context.close()
                await browser.close()
                raise RuntimeError(
                    f"Scene playback timed out after {scene_timeout:.1f}s while waiting "
                    "for window.playScene() to finish. Check map style/camera event "
                    "listeners in map_renderer/web/map.html."
                )

            # playScene() already waits for camera + timeline completion.
            # Keep only a tiny tail so the final effect frame is captured.
            tail = float(scene.get("_tail_buffer", 0.25))
            if tail > 0:
                await asyncio.sleep(tail)
            video_path_obj = await page.video.path() if page.video else None

        await context.close()
        await browser.close()

    output_path = OUTPUT_DIR / f"{clip_name}.mp4"
    if deterministic:
        if not frames_dir.exists():
            raise RuntimeError("Deterministic frames directory missing; capture failed.")
        success = _frames_to_mp4(
            frames_dir=frames_dir,
            output_path=output_path,
            fps=fps,
            nvenc_qp=nvenc_qp,
            x264_crf=x264_crf,
        )
        if success:
            expected_seconds = max(0, int(round(duration * fps))) / fps
            log.info("Deterministic output runtime target: %.2fs", expected_seconds)
            shutil.rmtree(frames_dir.parent, ignore_errors=True)
    else:
        if video_path_obj and Path(str(video_path_obj)).exists():
            webm_path = Path(str(video_path_obj))
        else:
            webm_path = _latest_webm(TMP_DIR)

        if not webm_path or not webm_path.exists():
            raise RuntimeError(
                "No .webm recording found in tmp/. "
                "Playwright may have failed to record."
            )

        log.info("Recording saved: %s (%.1f MB)", webm_path.name, webm_path.stat().st_size / 1e6)
        success = _webm_to_mp4(
            webm_path,
            output_path,
            fps=fps,
            nvenc_qp=nvenc_qp,
            x264_crf=x264_crf,
        )

        try:
            webm_path.unlink()
        except OSError:
            pass

    if not success:
        raise RuntimeError(f"FFmpeg conversion failed for clip '{clip_name}'.")

    log.info("Done: %s", output_path)
    return output_path


async def render_scenes(scenes: list[tuple[dict, str]]) -> list[Path]:
    """Render multiple scenes sequentially."""
    results = []
    for i, (scene, name) in enumerate(scenes):
        log.info("─── Clip %d/%d: %s ───", i + 1, len(scenes), name)
        path = await render_scene(scene, name)
        results.append(path)
    return results


def _cli():
    if len(sys.argv) < 3:
        print("Usage: python pipeline/render_scene.py <scene.json> <clip_name>")
        sys.exit(1)

    scene_file = Path(sys.argv[1])
    clip_name = sys.argv[2]

    if not scene_file.exists():
        log.error("Scene file not found: %s", scene_file)
        sys.exit(1)

    scene = json.loads(scene_file.read_text(encoding="utf-8"))
    output = asyncio.run(render_scene(scene, clip_name))
    print(f"\n✓ Rendered: {output}")
