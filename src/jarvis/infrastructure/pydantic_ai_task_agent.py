"""PydanticAiTaskAgent: a model-driven tool loop over Jarvis's ToolRegistry (D7, D8).

The model-driven cousin of `ToolRegistryTaskAgent`. Delegation (revised D1) is the
same contract: a *material*, already-decided task goes to an edge agent; the cognitive
cycle stays in the core. The difference is who picks the calls -- here the language
model decides the sequence and adapts to each tool's outcome (retry, redirect, stop),
while the `ToolRegistry` still holds the gate (permission + approval) and the trace
(`ToolCall` events the core can reason over later).

Boundaries held here:
* `pydantic_ai` is a *runtime option*, imported lazily via `importlib`, so offline
  Jarvis stays zero-dependency and the pyright gate stays clean without the package.
* Nothing here decides whether to act. The task and the approval to run its calls are
  decided upstream: ``approved=True`` mirrors `ToolRegistryTaskAgent` (the delegation
  was already gated by the controlled-autonomy policy), and every call still passes the
  registry's policy gate before it runs.
* Each registered `ToolSpec` becomes one function tool whose schema is baked from the
  spec (arg name -> description, all-string required args) -- the model may only choose
  calls the spec declares, never anything else.
* Outcomes are plain text fed back into the loop; a refused or failed call is an honest
  error string, never a fabricated success (Vision §37). The final `TaskResult`
  narrates *what actually ran* from the recorded calls -- the model's own closing words
  are not taken as the account (D6): the truth is derived from the observed act.
* Tools keep their sandboxes and injectable transports (FileSystemTool's `root`/`io`,
  EchoTool), so the loop is fully offline-testable with an injected `FunctionModel`.
"""

from __future__ import annotations

import importlib
from typing import Any, cast

from jarvis.domain.retrieval.task_agent_source import TaskAgent
from jarvis.domain.tools.tool_registry import ToolRegistry
from jarvis.domain.value_objects.task_result import TaskResult
from jarvis.domain.value_objects.tool_spec import ToolSpec
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.infrastructure.usage import Usage, read_run_usage

# What the model is told about its role. Tool-choice only: nothing here lets the model
# decide whether an act should happen -- that decision is upstream, per revised D1.
_INSTRUCTIONS = (
    "You orchestrate agreed tool calls for Jarvis. Given the task, choose and call the "
    "tools you need, in any order, adapting to each outcome. Tool outputs are "
    "authoritative; if a call fails, retry once or choose another way, and never "
    "claim a call succeeded when its output says otherwise."
)

_CallRecord = tuple[str, bool, str]


class PydanticAiTaskAgent:
    """A `TaskAgent` whose tool sequence is decided by a language model."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        settings: ProviderSettings,
        approved: bool = True,
        model: Any = None,
        instructions: str | None = None,
        fallback: TaskAgent | None = None,
    ) -> None:
        self._registry = registry
        self._settings = settings
        # Upstream approval for risky levels, mirroring ToolRegistryTaskAgent: the
        # delegation (and this task) were approved before the agent ever ran.
        self._approved = approved
        # Injected pydantic-ai Model for offline tests; None -> OpenAI-compatible.
        self._model = model
        self._instructions = instructions or _INSTRUCTIONS
        # On a provider/loop failure, an honest delegation may still land through a
        # fallback agent (Phase 5) -- the decided task simply executes another way,
        # still behind the TaskAgent seam.
        self._fallback = fallback
        self._agent: Any = None
        self._recorded: list[_CallRecord] = []
        self._usage = Usage()

    def usage(self) -> Usage:
        """The tokens consumed deciding this agent's tool loop so far (Phase 5)."""
        return self._usage

    def run_task(self, task: str) -> TaskResult:
        """Let the model drive the tool loop and narrate what actually ran (D6)."""
        text = task.strip()
        if not text:
            return TaskResult(task=task, summary="no tool calls ran", success=False)
        self._recorded = []
        try:
            run = self._build_agent().run_sync(text)
        except Exception:  # provider/loop failure -> an honest failed account
            if self._fallback is not None:
                return self._fallback.run_task(task)
            return TaskResult(
                task=task,
                summary="delegated task failed: the agent errored",
                success=False,
            )
        self._usage = self._usage + read_run_usage(run)
        calls = self._recorded
        if not calls:
            return TaskResult(task=task, summary="no tool calls ran", success=False)
        narration = "; ".join(
            f"{name} ok: {detail}" if ok else f"{name} failed: {detail}"
            for name, ok, detail in calls
        )
        return TaskResult(
            task=task,
            summary=narration,
            success=any(ok for _, ok, _ in calls),
        )

    # -- edge plumbing ---------------------------------------------------------

    def _build_agent(self) -> Any:
        """Build (once) the pydantic-ai `Agent` with one tool per registered `ToolSpec`."""
        if self._agent is not None:
            return self._agent
        pai = cast(Any, importlib.import_module("pydantic_ai"))
        tools_mod = cast(Any, importlib.import_module("pydantic_ai.tools"))
        models_mod = cast(Any, importlib.import_module("pydantic_ai.models.openai"))
        providers_mod = cast(Any, importlib.import_module("pydantic_ai.providers.openai"))
        settings_mod = cast(Any, importlib.import_module("pydantic_ai.settings"))

        if self._model is None:
            entry_model = models_mod.OpenAIChatModel(
                self._settings.model,
                provider=providers_mod.OpenAIProvider(
                    base_url=self._settings.base_url,
                    api_key=self._settings.api_key,
                ),
            )
        else:
            entry_model = self._model

        tools = [
            tools_mod.Tool(
                self._tool_function(spec),
                name=spec.name,
                description=spec.description,
                prepare=self._baking_prepare(spec),
            )
            for spec in self._specs()
        ]
        self._agent = pai.Agent(
            entry_model,
            system_prompt=self._instructions,
            model_settings=settings_mod.ModelSettings(
                temperature=self._settings.temperature,
                max_tokens=self._settings.max_tokens,
                timeout=self._settings.timeout,
            ),
            tools=tools,
        )
        return self._agent

    def _specs(self) -> tuple[ToolSpec, ...]:
        return tuple(
            spec
            for name in self._registry.tool_names()
            if (spec := self._registry.spec(name)) is not None
        )

    def _tool_function(self, spec: ToolSpec) -> Any:
        # No RunContext parameter: pydantic-ai builds the function schema from string
        # annotations only, so a closure-scoped annotation would not resolve. The
        # prepared schema (below) already pins the accepted arguments.
        async def function(**arguments: Any) -> str:
            result = self._registry.run(spec.name, arguments, approved=self._approved)
            if result.ok:
                self._recorded.append((spec.name, True, result.value))
                return result.value
            self._recorded.append((spec.name, False, result.error))
            return f"ERROR: {result.error}"

        return function

    def _baking_prepare(self, spec: ToolSpec) -> Any:
        def prepare(ctx: Any, tool_def: Any) -> Any:
            del ctx
            # Bake the spec's declared contract so the model can only choose calls the
            # tool declares -- names, descriptions, all-string required args.
            tool_def.parameters_json_schema = {
                "type": "object",
                "properties": {
                    name: {"type": "string", "description": note}
                    for name, note in spec.args.items()
                },
                "required": list(spec.args),
                "additionalProperties": False,
            }
            tool_def.description = spec.description
            return tool_def

        return prepare


def build_ai_task_agent(
    settings: ProviderSettings,
    *,
    approved: bool = True,
    model: Any = None,
    fallback: TaskAgent | None = None,
) -> PydanticAiTaskAgent | None:
    """Build the model-driven agent over the sandboxed tool set, or ``None``.

    Mirrors `build_default_task_agent`: the sandboxed `ToolRegistry` (FileSystemTool
    under ``JARVIS_AGENT_ROOT`` plus EchoTool) drives a model-chosen sequence instead of
    a decided script. The deterministic decided-script agent is the natural ``fallback``
    for decided script-shaped tasks on a provider outage. ``None`` when directory
    configuration is missing, so a Jarvis built from this keeps working offline.
    """
    from jarvis.infrastructure.task_agent_source import build_sandboxed_registry

    registry = build_sandboxed_registry()
    if registry is None:
        return None
    return PydanticAiTaskAgent(
        registry,
        settings=settings,
        approved=approved,
        model=model,
        fallback=fallback,
    )