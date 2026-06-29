#!/usr/bin/env python3
"""S2-Pro text-to-speech client (Fish Audio fish-speech `/v1/tts`).

Synthesizes text → a WAV via a running fish-speech `api_server`. The server is
brought up by the `s2pro` Verda workload (infra/) and reached over an SSH tunnel;
the URL is read from `GEOPOAI_TTS_URL` (matches the workload's env_export).

Request shape mirrors fish-speech `tools/api_client.py`: a msgpack body
(`content-type: application/msgpack`) with the ServeTTSRequest fields; the
response body is the raw encoded audio (wav).
"""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8080"


def _pack(obj: dict[str, Any]) -> bytes:
    """Serialize a request dict to msgpack (ormsgpack preferred, msgpack fallback)."""
    try:
        import ormsgpack  # type: ignore
        return ormsgpack.packb(obj)
    except ImportError:
        pass
    try:
        import msgpack  # type: ignore
        return msgpack.packb(obj, use_bin_type=True)
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "TTS client needs `ormsgpack` (or `msgpack`) — `pip install ormsgpack`"
        ) from exc


def synthesize(
    text: str,
    out_wav: str | Path,
    *,
    url: str | None = None,
    api_key: str | None = None,
    reference_audio: str | Path | None = None,
    reference_text: str | None = None,
    fmt: str = "wav",
    chunk_length: int = 300,
    max_new_tokens: int = 1024,
    top_p: float = 0.8,
    temperature: float = 0.8,
    repetition_penalty: float = 1.1,
    seed: int | None = None,
    timeout: float = 600.0,
) -> Path:
    """Synthesize *text* to *out_wav* via the S2-Pro `/v1/tts` server. Returns the path."""
    base = (url or os.environ.get("GEOPOAI_TTS_URL") or DEFAULT_URL).rstrip("/")
    endpoint = f"{base}/v1/tts"

    references: list[dict[str, Any]] = []
    if reference_audio:
        references = [{
            "audio": Path(reference_audio).read_bytes(),
            "text": reference_text or "",
        }]

    payload: dict[str, Any] = {
        "text": text,
        "references": references,
        "reference_id": None,
        "format": fmt,
        "max_new_tokens": max_new_tokens,
        "chunk_length": chunk_length,
        "top_p": top_p,
        "repetition_penalty": repetition_penalty,
        "temperature": temperature,
        "streaming": False,
        "use_memory_cache": "off",
        "seed": seed,
    }
    headers = {"content-type": "application/msgpack"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"

    log.info("tts: POST %s (%d chars)", endpoint, len(text))
    req = urllib.request.Request(endpoint, data=_pack(payload), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        audio = resp.read()
    if not audio:
        raise RuntimeError("tts: empty audio response from server")

    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    log.info("tts: wrote %s (%d bytes)", out, len(audio))
    return out


def _cli(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Synthesize text to a WAV via S2-Pro /v1/tts.")
    p.add_argument("text")
    p.add_argument("out_wav")
    p.add_argument("--url", default=None, help="TTS base URL (default: $GEOPOAI_TTS_URL).")
    p.add_argument("--api-key", default=os.environ.get("GEOPOAI_TTS_API_KEY"))
    p.add_argument("--reference-audio", default=os.environ.get("GEOPOAI_TTS_REFERENCE"))
    p.add_argument("--reference-text", default=os.environ.get("GEOPOAI_TTS_REFERENCE_TEXT"))
    args = p.parse_args(argv)
    out = synthesize(
        args.text, args.out_wav, url=args.url, api_key=args.api_key,
        reference_audio=args.reference_audio, reference_text=args.reference_text,
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
