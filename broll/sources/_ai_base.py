"""broll.sources._ai_base — shared scaffolding for AI generation sources.

LTX-2.3 and Wan 2.2 share 90% of their lifecycle:
1. Build a positive/negative prompt via :mod:`broll.lib.prompt_assembly`.
2. Derive a deterministic seed via :mod:`broll.lib.seed_strategy`.
3. Load a workflow JSON template, substitute slot markers, submit via
   :mod:`broll.lib.comfyui_client`.
4. Wait for completion, download the result to a temp path.
5. Hand the file to :mod:`broll.lib.asset_wrapper.finalize` to write the
   final asset + ``.meta.json`` atomically.

This module implements all of that as :class:`BaseAIGenerator`. Concrete
sources only need to declare a class with three knobs (model id, default
workflow filename, default sampling parameters) and they get a working
``generate()`` for free.

Recipe cache
------------
Same prompt + seed + model + LoRA stack = same clip. We hash the recipe
into ``data/.cache/broll/ai_recipes/<sha>.mp4`` and reuse on hit. This
lets reruns be free even when ComfyUI itself doesn't have caching wired
up. Disable with ``BROLL_NO_AI_CACHE=1``.

Spot interrupt recovery
-----------------------
The ComfyUI client retries individual HTTP calls on transport errors. If
the entire job dies (a 3-attempt window of consecutive failures), we
re-submit the WHOLE workflow up to ``BaseAIGenerator.max_resubmits``
times. The seed is preserved across resubmissions so the recipe (and
therefore the cache key) doesn't shift.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from ..lib import asset_wrapper, comfyui_client, prompt_assembly, seed_strategy
from ..lib.errors import BrollError

log = logging.getLogger("broll.sources._ai_base")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "comfyui_workflows"
_AI_CACHE_DIR = _REPO_ROOT / "data" / ".cache" / "broll" / "ai_recipes"


class AIGenerationError(BrollError):
    """Wraps every failure mode of a single shot's AI generation."""


# ── Default sampling params per model ────────────────────────────────────────
@dataclass(slots=True, frozen=True)
class SamplingParams:
    """Per-shot sampling knobs. Defaults come from the source subclass."""

    width: int = 1280
    height: int = 720
    fps: int = 24
    duration_seconds: float = 5.0
    steps: int = 30
    cfg: float = 3.0
    sampler: str = "euler"

    @property
    def num_frames(self) -> int:
        return max(1, int(round(self.fps * self.duration_seconds)))


def _orientation_to_wh(orientation: str | None, *, default_w: int, default_h: int) -> tuple[int, int]:
    """Map a horizontal/vertical/square hint to dimensions (multiples of 32)."""
    if orientation == "vertical":
        return 720, 1280
    if orientation == "square":
        return 1024, 1024
    return default_w, default_h


# ── Slot substitution ────────────────────────────────────────────────────────
def _substitute_slots(template: dict[str, Any], slots: dict[str, Any]) -> dict[str, Any]:
    """Recursively replace ``"<<KEY>>"`` markers with ``slots[KEY]``.

    A node entry whose ``lora_name`` is empty (the default-empty LoRA slot)
    gets its strength forced to 0 so ComfyUI doesn't fail on a missing file.
    """
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and node.startswith("<<") and node.endswith(">>"):
            key = node[2:-2]
            if key not in slots:
                raise AIGenerationError(f"workflow slot {node!r} has no provided value")
            return slots[key]
        return node

    populated = walk(copy.deepcopy(template))

    # If LoRA 0 is empty, disable it so the node doesn't error on a missing file.
    for node_id, node in list(populated.items()):
        if not isinstance(node, dict) or node.get("class_type") != "LoraLoader":
            continue
        if not node.get("inputs", {}).get("lora_name"):
            node["inputs"]["lora_name"] = "none"
            node["inputs"]["strength_model"] = 0.0
            node["inputs"]["strength_clip"] = 0.0
    return populated


# ── Recipe cache ─────────────────────────────────────────────────────────────
def _recipe_key(
    *,
    model: str,
    prompt: str,
    negative: str,
    seed: int,
    params: SamplingParams,
    lora_stack: list[dict[str, Any]],
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "negative": negative,
            "seed": seed,
            "params": {
                "width": params.width, "height": params.height,
                "fps": params.fps, "duration_seconds": params.duration_seconds,
                "steps": params.steps, "cfg": params.cfg, "sampler": params.sampler,
            },
            "lora_stack": [{"name": l.get("name"), "strength": l.get("strength")} for l in lora_stack],
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cache_path_for(key: str) -> Path:
    return _AI_CACHE_DIR / f"{key}.mp4"


def _cache_disabled() -> bool:
    return os.environ.get("BROLL_NO_AI_CACHE") == "1"


# ── Base generator ──────────────────────────────────────────────────────────
class BaseAIGenerator:
    """Shared lifecycle for AI sources. Subclasses override the three class
    variables and inherit a working :meth:`generate`."""

    NAME: ClassVar[str] = "ai_base"          # source name, e.g. "ltx-2.3"
    MODEL_VERSION: ClassVar[str] = "0"        # written to meta.source.version
    WORKFLOW_FILENAME: ClassVar[str] = ""     # in broll/comfyui_workflows/
    DEFAULTS: ClassVar[SamplingParams] = SamplingParams()
    max_resubmits: ClassVar[int] = 2
    # Output artifact: video (mp4) vs still image (png) for ComfyUI SaveImage workflows.
    OUTPUT_SUFFIX: ClassVar[str] = ".mp4"
    FINALIZE_KIND: ClassVar[str] = "ai_video"

    @classmethod
    def _load_workflow(cls) -> dict[str, Any]:
        path = _WORKFLOWS_DIR / cls.WORKFLOW_FILENAME
        if not path.exists():
            raise AIGenerationError(f"workflow template missing: {path}")
        with path.open("r", encoding="utf-8") as fp:
            doc = json.load(fp)
        # Strip documentation key.
        doc.pop("_doc", None)
        return doc

    @classmethod
    def _sampling_params_for(cls, shot_spec: dict[str, Any]) -> SamplingParams:
        d = cls.DEFAULTS
        # ``shot_spec.format_hint`` overrides; ``format`` adjusts orientation.
        hint = shot_spec.get("format_hint") or {}
        w, h = _orientation_to_wh(
            shot_spec.get("format"),
            default_w=d.width,
            default_h=d.height,
        )
        if isinstance(hint.get("width"), int):
            w = hint["width"]
        if isinstance(hint.get("height"), int):
            h = hint["height"]
        fps = int(hint.get("fps") or d.fps)
        duration = float(shot_spec.get("duration_seconds") or d.duration_seconds)
        return SamplingParams(
            width=w, height=h, fps=fps,
            duration_seconds=duration,
            steps=d.steps, cfg=d.cfg, sampler=d.sampler,
        )

    @classmethod
    def _build_slots(
        cls,
        *,
        positive: str,
        negative: str,
        seed: int,
        params: SamplingParams,
        lora_stack: list[dict[str, Any]],
        filename_prefix: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Only LORA_0 is supported by the base template. Multi-LoRA requires
        # extending the workflow JSON; see HANDOFF_PHASE_2.md.
        first_lora = lora_stack[0] if lora_stack else {"name": "", "strength": 0.0}
        # Pad LoRA file extension to whatever the user stored it as.
        lora_name = first_lora.get("name") or ""
        if lora_name and not lora_name.endswith((".safetensors", ".pt", ".ckpt")):
            lora_name = f"{lora_name}.safetensors"
        slots: dict[str, Any] = {
            "PROMPT": positive,
            "NEGATIVE_PROMPT": negative,
            "SEED": int(seed),
            "STEPS": int(params.steps),
            "CFG": float(params.cfg),
            "SAMPLER": str(params.sampler),
            "WIDTH": int(params.width),
            "HEIGHT": int(params.height),
            "NUM_FRAMES": int(params.num_frames),
            "FPS": int(params.fps),
            "LORA_0_NAME": str(lora_name),
            "LORA_0_STRENGTH": float(first_lora.get("strength") or 0.0),
            "FILENAME_PREFIX": filename_prefix,
        }
        if extra:
            slots.update(extra)
        return slots

    @classmethod
    def _extra_slots(cls, shot_spec: dict[str, Any]) -> dict[str, Any]:
        """Hook for I2V / chained pipelines (INPUT_IMAGE, KEYFRAME_PATH, etc.)."""
        return {}

    # ── Public API ──────────────────────────────────────────────────────────
    @classmethod
    def generate(
        cls,
        shot_spec: dict[str, Any],
        target_path: str | os.PathLike[str],
        *,
        verification: dict[str, Any] | None = None,
        client: comfyui_client.ComfyUIClient | None = None,
    ) -> dict[str, Any]:
        """Generate a clip for ``shot_spec`` and finalize via asset_wrapper.

        Returns the validated meta dict written to disk.

        The flow:
        1. Assemble the prompt + LoRA stack.
        2. Derive the seed (recipe-deterministic unless ``_seed`` override).
        3. Check the recipe cache; on hit, ``asset_wrapper.finalize`` from
           the cached file. No ComfyUI traffic.
        4. On miss, submit the workflow with up to ``max_resubmits`` retries
           on spot interrupts.
        5. Download the result to a temp path, then ``finalize`` to
           ``target_path``. Cache the temp file by recipe hash for future
           reuse.
        """
        shot_id = shot_spec["shot_id"]
        target = Path(target_path)

        assembled = prompt_assembly.build_prompt(shot_spec, model=cls.NAME)
        params = cls._sampling_params_for(shot_spec)
        seed = seed_strategy.seed_from_spec(
            shot_spec,
            model=cls.NAME,
            prompt=assembled.positive,
            lora_stack=assembled.lora_stack,
        )
        recipe_key = _recipe_key(
            model=cls.NAME,
            prompt=assembled.positive,
            negative=assembled.negative,
            seed=seed,
            params=params,
            lora_stack=assembled.lora_stack,
        )

        cached = None if _cache_disabled() else _cache_path_for(recipe_key)
        if cached is not None and cached.exists():
            log.info("ai cache hit shot_id=%s recipe=%s reusing %s", shot_id, recipe_key[:12], cached)
            return cls._finalize(
                local_path=cached,
                target_path=target,
                shot_id=shot_id,
                params=params,
                assembled=assembled,
                seed=seed,
                verification=verification,
                cache_path=cached,
                from_cache=True,
            )

        comfy = client or comfyui_client.ComfyUIClient()
        slots = cls._build_slots(
            positive=assembled.positive,
            negative=assembled.negative,
            seed=seed,
            params=params,
            lora_stack=assembled.lora_stack,
            filename_prefix=f"broll/{shot_id}",
            extra=cls._extra_slots(shot_spec),
        )
        workflow = _substitute_slots(cls._load_workflow(), slots)

        # Stage the download into the AI cache so we can serve future runs
        # from it directly. The cache file is the canonical artifact;
        # ``finalize`` copies (not moves) it into the target path.
        if not _cache_disabled():
            _AI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            staging = _AI_CACHE_DIR / f"{recipe_key}{cls.OUTPUT_SUFFIX}"
        else:
            staging = _AI_CACHE_DIR.parent / f".uncached-{uuid.uuid4().hex}{cls.OUTPUT_SUFFIX}"

        last_exc: Exception | None = None
        for attempt in range(cls.max_resubmits + 1):
            try:
                log.info(
                    "ai generate shot_id=%s model=%s seed=%d attempt=%d/%d url=%s",
                    shot_id, cls.NAME, seed, attempt + 1, cls.max_resubmits + 1, comfy.url,
                )
                result = comfy.run(
                    workflow,
                    download_to=staging,
                    prefer_image=cls.OUTPUT_SUFFIX != ".mp4",
                )
                log.info("ai generate OK shot_id=%s prompt_id=%s", shot_id, result.prompt_id)
                break
            except comfyui_client.ComfyJobError as exc:
                last_exc = exc
                log.warning(
                    "ai generate attempt %d/%d failed for shot_id=%s: %s",
                    attempt + 1, cls.max_resubmits + 1, shot_id, exc,
                )
                if attempt >= cls.max_resubmits:
                    raise AIGenerationError(
                        f"AI generation failed for shot_id={shot_id} after "
                        f"{cls.max_resubmits + 1} attempts: {exc}"
                    ) from exc
                time.sleep(2.0 * (attempt + 1))
        else:  # pragma: no cover - loop always exits via break or raise
            raise AIGenerationError(f"AI generation exhausted retries: {last_exc}")

        return cls._finalize(
            local_path=staging,
            target_path=target,
            shot_id=shot_id,
            params=params,
            assembled=assembled,
            seed=seed,
            verification=verification,
            cache_path=staging if not _cache_disabled() else None,
            from_cache=False,
        )

    # ── Finalize helper ─────────────────────────────────────────────────────
    @classmethod
    def _finalize(
        cls,
        *,
        local_path: Path,
        target_path: Path,
        shot_id: str,
        params: SamplingParams,
        assembled: prompt_assembly.AssembledPrompt,
        seed: int,
        verification: dict[str, Any] | None,
        cache_path: Path | None,
        from_cache: bool,
    ) -> dict[str, Any]:
        # When the cache is enabled, ``local_path`` IS the cache file — both
        # for the fresh-gen path (we downloaded directly to the cache) and the
        # cache-hit path (we're re-reading it). In both cases we want the
        # cache file to survive the finalize, so we copy rather than move.
        # When the cache is disabled, ``local_path`` is a one-off temp file
        # and a plain move is the right thing.
        move_flag = cache_path is None

        meta = asset_wrapper.finalize(
            local_path,
            target_path,
            shot_id=shot_id,
            kind=cls.FINALIZE_KIND,
            source={
                "name": cls.NAME,
                "version": cls.MODEL_VERSION,
                "url": f"comfyui://{cls.NAME}/{shot_id}",
                "source_metadata": {
                    "from_recipe_cache": from_cache,
                    "fps": params.fps,
                    "num_frames": params.num_frames,
                    "resolution": [params.width, params.height],
                },
            },
            license={
                "type": "ai_generated",
                "attribution_required": False,
                "attribution_text": f"Generated with {cls.NAME} (recipe seed {seed})",
                "commercial_use_ok": True,
            },
            verification=verification,
            ai_metadata={
                **assembled.to_metadata(),
                "model": cls.NAME,
                "seed": int(seed),
                "sampler": params.sampler,
                "steps": int(params.steps),
                "resolution": [int(params.width), int(params.height)],
                "duration_seconds": float(params.duration_seconds),
            },
            modifications=[],
            move=move_flag,
        )
        return meta
