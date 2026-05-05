#!/usr/bin/env python3
"""
pipeline/render_scene.py
─────────────────────────────────────────────────────────────────────────────
Playwright-based renderer. Opens map.html headlessly, injects the Mapbox
token, waits for tiles, fires a scene JSON, records the output as MP4.

Usage (CLI):
    python pipeline/render_scene.py scripts/test_scene.json hook_clip
    → output/hook_clip.mp4

Usage (programmatic):
    from pipeline.render_scene import render_scene
    path = asyncio.run(render_scene(scene_dict, "hook_clip"))
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
RENDERER_PATH = ROOT / "renderer" / "map.html"
TMP_DIR      = ROOT / "tmp"
OUTPUT_DIR   = ROOT / "output"

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

if not MAPBOX_TOKEN:
    log.warning(
        "MAPBOX_TOKEN not found in environment. "
        "Create a .env file at the project root with MAPBOX_TOKEN=pk.eyJ1..."
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def _webm_to_mp4(webm_path: Path, output_path: Path) -> bool:
    """
    Convert .webm → .mp4 using ffmpeg.
    Returns True on success.
    Encoding flags:
      -c:v libx264      standard H.264 — universally compatible
      -pix_fmt yuv420p  required for QuickTime / most players
      -crf 18           near-lossless quality
      -preset fast      good speed/quality balance
      -movflags +faststart  web-optimised
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(webm_path),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        "-preset", "fast",
        "-movflags", "+faststart",
        str(output_path),
    ]
    log.info("FFmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("FFmpeg failed:\n%s", result.stderr[-2000:])
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

    duration = scene.get("duration", 10)
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
            ],
        )

        context = await browser.new_context(
            record_video_dir=str(TMP_DIR),
            record_video_size={"width": 1920, "height": 1080},
            viewport={"width": 1920, "height": 1080},
        )

        page = await context.new_page()

        page.on("console", lambda msg: log.debug("[browser %s] %s", msg.type, msg.text))
        page.on("pageerror", lambda err: log.error("[browser error] %s", err))

        renderer_url = RENDERER_PATH.as_uri()
        log.info("Loading renderer: %s", renderer_url)
        await page.goto(renderer_url, wait_until="domcontentloaded")

        log.info("Injecting Mapbox token and initialising map…")
        await page.evaluate(f"window.init('{MAPBOX_TOKEN}')")

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

        log.info("Starting scene (%.1fs)…", duration)
        await page.evaluate("scene => window.playScene(scene)", scene)

        tail = scene.get("_tail_buffer", 0.8)
        await asyncio.sleep(duration + tail)

        video_path_obj = await page.video.path() if page.video else None
        await context.close()
        await browser.close()

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

    output_path = OUTPUT_DIR / f"{clip_name}.mp4"
    success = _webm_to_mp4(webm_path, output_path)

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


if __name__ == "__main__":
    _cli()