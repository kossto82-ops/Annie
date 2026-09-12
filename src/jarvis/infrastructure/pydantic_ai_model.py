"""PydanticAiModel: a `LanguageModel` backed by a Pydantic AI `Agent` (D7, D8).

An opt-in adapter that lets a Pydantic AI model driver serve Jarvis's perception,
reasoning, recall, and voice through the existing `LanguageModel` seam ("prompt in,
text out"). Nothing above this module knows Pydantic AI exists.

Boundaries held here:
* `pydantic_ai` is a *runtime option*, never a core dependency. It is imported lazily
  via `importlib`, so Jarvis stays offline-first and zero-dependency, and pyright stays
  clean even when the package is not installed. Every other module talks to this one
  through `LanguageModel` only.
* Structured output is our seam to Vision §38: perception hands instructions plus an
  `output_type` (a claim TypedDict), so the model *extracts candidate evidence in
  schema* rather than asserting truth. The decision stays downstream.
* Failures are honest silence (§37): a provider error, a validation failure, or an
  unreadable reply yields `""` -- model retries are capped by the `Agent` -- never a
  fabricated answer.
* Construction reuses `ProviderSettings` as-is: every OpenAI-compatible endpoint Jarvis
  already knows (Groq, Ollama, LM Studio, a local SLM...) becomes a Pydantic AI model
  with the same `base_url` / `api_key`. `ProviderSettings.reasoning_effort` is not
  mapped in this phase: pydantic-ai 2.x `ModelSettings` has no such field.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from typing import Any, cast

from jarvis.infrastructure.guardrail import guard_reply
from jarvis.infrastructure.language_model import LanguageModel
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.usage import Usage, read_run_usage


class PydanticAiModel(LanguageModel):
    """A `LanguageModel` that drives a Pydantic AI `Agent`.

    Construction is lazy: nothing is built until the first call, and building only
    *constructs* an agent (no network). Provide `model=` to inject a Pydantic AI
    `Model` (e.g. a `FunctionModel`) for offline tests; leave it `None` to use an
    OpenAI-compatible model from `settings`.
    """

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        instructions: str | None = None,
        output_type: Any = None,
        model: Any = None,
    ) -> None:
        self._settings = settings
        # Instructions ride the system prompt; output_type (if any) makes the reply
        # structured. Exposed read-only so a surface or test can say what is wired.
        self.instructions = instructions
        self.output_type = output_type
        # Injected pydantic-ai Model for offline tests; None -> OpenAI-compatible.
        self._model = model
        self._agent: Any = None
        self._usage = Usage()

    def usage(self) -> Usage:
        """The tokens consumed through this model so far (Phase 5 bookkeeping)."""
        return self._usage

    def complete(self, prompt: str) -> str:
        """One question in, one answer out -- honest silence (`""`) on failure (§37)."""
        try:
            run = self._build_agent().run_sync(prompt)
            output = run.output
            self._usage = self._usage + read_run_usage(run)
        except Exception:  # any provider/validation/model error -> say nothing
            return ""
        return guard_reply(_serialise(output))

    def stream(self, prompt: str) -> Iterator[str]:
        """Stream a reply's text deltas; end early (honestly) on error."""
        try:
            agent = self._build_agent()
            with agent.run_stream_sync(prompt) as run:
                for piece in run.stream_text():
                    if piece:
                        yield piece
                self._usage = self._usage + read_run_usage(run)
        except Exception:
            return

    def _build_agent(self) -> Any:
        """Build (once) the Pydantic AI `Agent` behind this model."""
        if self._agent is not None:
            return self._agent
        pai = cast(Any, importlib.import_module("pydantic_ai"))
        models_mod = cast(Any, importlib.import_module("pydantic_ai.models.openai"))
        providers_mod = cast(Any, importlib.import_module("pydantic_ai.providers.openai"))
        settings_mod = cast(Any, importlib.import_module("pydantic_ai.settings"))

        if self._model is None:
            chat_model = models_mod.OpenAIChatModel(
                self._settings.model,
                provider=providers_mod.OpenAIProvider(
                    base_url=self._settings.base_url,
                    api_key=self._settings.api_key,
                ),
            )
        else:
            chat_model = self._model

        kwargs: dict[str, Any] = {
            "model": chat_model,
            "model_settings": settings_mod.ModelSettings(
                temperature=self._settings.temperature,
                max_tokens=self._settings.max_tokens,
                timeout=self._settings.timeout,
            ),
        }
        if self.instructions:
            kwargs["system_prompt"] = self.instructions
        if self.output_type is not None:
            kwargs["output_type"] = self.output_type
        try:
            # pydantic-ai >= 2.41: a content-filtered response is a run-ending error
            # that honest-silence then absorbs (§37). Older 2.x has no capabilities.
            content_filter_mod = cast(
                Any, importlib.import_module("pydantic_ai.capabilities.content_filter")
            )
            kwargs["capabilities"] = [content_filter_mod.RaiseContentFilterError()]
        except (ImportError, ModuleNotFoundError):  # missing/older capability module -> no content-filter hook
            pass
        self._agent = pai.Agent(**kwargs)
        return self._agent


def _serialise(output: Any) -> str:
    """Reduce a validated agent output to the text the seam promises.

    Plain-text outputs pass through; structured outputs (TypedDict / list of
    TypedDict / BaseModel) become JSON -- `LlmPerception` already reads claims out of
    a JSON array in text form.
    """
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, ensure_ascii=False, default=_json_default)
    except (TypeError, ValueError):
        return ""


def _json_default(value: Any) -> Any:
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        return dumper()
    raise TypeError(f"cannot serialise ({type(value).__name__}) structured output")