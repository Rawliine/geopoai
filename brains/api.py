"""API brain — LangGraph author → validate → repair loop over LLM providers."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from langgraph.graph import END, StateGraph

from .base import Brain, BrainValidationError
from .cli_agent import build_authoring_prompt, extract_first_json_object

log = logging.getLogger("brains.api")

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_TEMPERATURE = 0.0
_DEFAULT_MAX_REPAIRS = 2

# Rough USD / 1M tokens (input, output) for QC cost estimates.
_MODEL_COST_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
    "gemini-2.5-pro": (1.25, 10.0),
}


@dataclass(slots=True)
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def estimate_cost_usd(self) -> float:
        rates = _MODEL_COST_PER_MTOK.get(self.model, (3.0, 15.0))
        return (self.input_tokens * rates[0] + self.output_tokens * rates[1]) / 1_000_000


class LLMProvider(Protocol):
    name: str
    model: str
    temperature: float

    def complete(self, prompt: str) -> ProviderResponse: ...


class AnthropicProvider:
    """Anthropic Messages API — default api-brain provider."""

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float = _DEFAULT_TEMPERATURE,
        api_key: str | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("anthropic package required for api brain") from exc

        self.model = model or os.environ.get("BRAIN_API_MODEL", _DEFAULT_MODEL)
        self.temperature = temperature
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set (required for api brain)")
        self._client = anthropic.Anthropic(api_key=key)

    def complete(self, prompt: str) -> ProviderResponse:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        text = "\n".join(text_blocks).strip()
        usage = response.usage
        return ProviderResponse(
            text=text,
            input_tokens=int(usage.input_tokens),
            output_tokens=int(usage.output_tokens),
            model=self.model,
            provider=self.name,
        )


class GeminiProvider:
    """Optional Gemini provider for the api brain."""

    name = "gemini"

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float = _DEFAULT_TEMPERATURE,
        api_key: str | None = None,
    ) -> None:
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("google-generativeai package required for Gemini api brain") from exc

        key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GOOGLE_API_KEY not set (required for Gemini api brain)")
        genai.configure(api_key=key)
        self.model = model or os.environ.get("BRAIN_API_MODEL", "gemini-2.5-pro")
        self.temperature = temperature
        self._genai = genai
        self._client = genai.GenerativeModel(self.model)

    def complete(self, prompt: str) -> ProviderResponse:
        response = self._client.generate_content(
            prompt,
            generation_config=self._genai.types.GenerationConfig(temperature=self.temperature),
        )
        text = (response.text or "").strip()
        usage = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        return ProviderResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            provider=self.name,
        )


def load_provider(
    provider_name: str | None = None,
    *,
    model: str | None = None,
    temperature: float = _DEFAULT_TEMPERATURE,
) -> LLMProvider:
    pref = (provider_name or os.environ.get("BRAIN_API_PROVIDER", "anthropic")).strip().lower()
    if pref in ("anthropic", "api", "claude"):
        return AnthropicProvider(model=model, temperature=temperature)
    if pref in ("gemini", "google"):
        return GeminiProvider(model=model, temperature=temperature)
    raise ValueError(f"unknown api brain provider {pref!r}")


class _GraphState(TypedDict):
    instruction: str
    schema: dict[str, Any]
    context: dict[str, Any]
    artifact: dict[str, Any] | None
    validation_error: str | None
    repair_count: int
    max_repairs: int
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


def _validate_node(state: _GraphState) -> dict[str, Any]:
    artifact = state.get("artifact")
    if not isinstance(artifact, dict):
        return {"validation_error": "author did not return a JSON object"}

    validator = Draft202012Validator(state["schema"])
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    if not errors:
        return {"validation_error": None}

    detail = "\n".join(
        f"  - {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors
    )
    return {"validation_error": detail}


def _build_graph(provider: LLMProvider) -> Any:
    def author_node(state: _GraphState) -> dict[str, Any]:
        prompt = build_authoring_prompt(state["instruction"], state["schema"], state["context"])
        if state.get("validation_error"):
            prompt += (
                "\n\nYour previous JSON response failed schema validation. Fix it and respond "
                f"with valid JSON only.\n\nValidation errors:\n{state['validation_error']}\n"
            )

        response = provider.complete(prompt)
        artifact = extract_first_json_object(response.text)
        return {
            "artifact": artifact,
            "validation_error": None,
            "input_tokens": state["input_tokens"] + response.input_tokens,
            "output_tokens": state["output_tokens"] + response.output_tokens,
            "model": response.model,
            "provider": response.provider,
        }

    def repair_node(state: _GraphState) -> dict[str, Any]:
        return {"repair_count": state["repair_count"] + 1}

    def route_after_validate(state: _GraphState) -> Literal["repair", "done"]:
        if state.get("validation_error") is None:
            return "done"
        if state["repair_count"] < state["max_repairs"]:
            return "repair"
        return "done"

    graph: StateGraph = StateGraph(_GraphState)
    graph.add_node("author", author_node)
    graph.add_node("validate", _validate_node)
    graph.add_node("repair", repair_node)
    graph.set_entry_point("author")
    graph.add_edge("author", "validate")
    graph.add_conditional_edges("validate", route_after_validate, {"repair": "repair", "done": END})
    graph.add_edge("repair", "author")
    return graph.compile()


@dataclass(slots=True)
class ApiBrain:
    """Programmatic brain backed by a LangGraph validate-and-repair loop."""

    provider: LLMProvider
    max_repairs: int = _DEFAULT_MAX_REPAIRS

    @property
    def name(self) -> str:
        return "api"

    def author(self, instruction: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        load_dotenv()
        graph = _build_graph(self.provider)
        final = graph.invoke(
            {
                "instruction": instruction,
                "schema": schema,
                "context": context,
                "artifact": None,
                "validation_error": None,
                "repair_count": 0,
                "max_repairs": self.max_repairs,
                "input_tokens": 0,
                "output_tokens": 0,
                "model": self.provider.model,
                "provider": self.provider.name,
            }
        )

        input_tokens = int(final.get("input_tokens", 0))
        output_tokens = int(final.get("output_tokens", 0))
        model = str(final.get("model", self.provider.model))
        provider_name = str(final.get("provider", self.provider.name))
        usage = ProviderResponse(
            text="",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            provider=provider_name,
        )
        context["_brain_usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": usage.total_tokens,
            "cost_usd": usage.estimate_cost_usd(),
            "model": model,
            "provider": provider_name,
        }

        artifact = final.get("artifact")
        if final.get("validation_error") is not None or not isinstance(artifact, dict):
            err = final.get("validation_error") or "author did not return a JSON object"
            raise BrainValidationError(f"api brain failed schema validation:\n{err}")
        return artifact


def make_api_brain(
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_repairs: int = _DEFAULT_MAX_REPAIRS,
    provider_instance: LLMProvider | None = None,
) -> ApiBrain:
    llm = provider_instance or load_provider(provider, model=model, temperature=temperature)
    return ApiBrain(provider=llm, max_repairs=max_repairs)
