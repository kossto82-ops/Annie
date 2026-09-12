"""Provider/speech/perceiver handlers — the live-model configuration surface."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from jarvis.infrastructure import llm_config_store
from jarvis.infrastructure.env_settings import speech_perception_from_env
from jarvis.infrastructure.language_model_registry import build_language_model
from jarvis.infrastructure.perceiver_factory import (
    build_companion_perceiver,
    build_document_editor,
    build_embedder,
    build_perceiver,
    build_reasoner,
    build_renderer,
    describe,
)
from jarvis.infrastructure.provider_settings import ProviderSettings
from jarvis.interface._shared import _OFFLINE_PERCEIVERS, _provider_error, _recall_block
from jarvis.jarvis import Jarvis

if TYPE_CHECKING:
    pass

# A reply the UI can render and (optionally) speak; some commands add extra fields.
Reply = dict[str, object]


def _perceiver(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or switch the live perceiver at runtime (Vision §32, §38; Track B).

    With no ``provider`` it just reports (the live perceiver rides in every snapshot).
    With one, it swaps the evidence *producer* -- the keyword rule, or an LLM provider
    from the open registry -- without rebuilding Jarvis.

    An optional ``api_key`` lets the developer hand over a real credential to start
    testing: it is applied to the live process and saved to ``.env`` (so a restart
    resumes), but it is write-only -- never echoed back in the reply or any snapshot.
    Without a key, the factory reads whatever ``JARVIS_LLM_API_KEY`` already holds. A
    misconfigured provider (e.g. real provider, no model) is a clear error, not a crash.
    """
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        return {"reply": "Name a provider to switch the perceiver.", "speak": False}
    # If no model is typed, recall the one this provider used last (per-provider memory),
    # so switching back to a provider doesn't require retyping its model.
    model = str(payload.get("model", "")).strip() or llm_config_store.resolve_model(
        provider.lower(), os.environ
    )
    base_url = str(payload.get("base_url", "")).strip() or None
    # The API key is write-only from the page: it is applied to the live process and
    # saved to .env, but never echoed back in any reply or snapshot.
    api_key = str(payload.get("api_key", "")).strip()
    is_real = provider.lower() not in _OFFLINE_PERCEIVERS
    if is_real and not model:
        # A real provider needs a model — reject before staging/persisting anything.
        return {"error": f"a model id is required for provider {provider!r} (e.g. llama-3.3-70b)"}
    # Apply the choice to the live process and build from it. The key is only-from-env:
    # `stage` sets any provided key (write-only) plus the non-secret provider/model so a
    # bare model fix (no key) also takes effect immediately.
    staged = llm_config_store.stage(provider, model, base_url, api_key)
    try:
        source = build_perceiver(provider, model, base_url)
    except ValueError as error:
        return {"error": str(error)}
    jarvis.set_perception(source)
    # Switch the relational perceiver to the same provider, so talking to Jarvis both
    # reasons about the world and learns about you through one model (Vision §5).
    jarvis.set_companion_perception(build_companion_perceiver(provider, model, base_url))
    # And voice replies in the companion's language through the same model (Vision §40).
    jarvis.set_voice(build_renderer(provider, model, base_url))
    # And reason provisional answers through the same model, so a novel question gets
    # a hedged answer instead of a refusal when a provider is active (Vision §37).
    jarvis.set_reasoner(build_reasoner(provider, model, base_url))
    # And edit documents through the same model, so "hazle este cambio" to a shared
    # file gets a concrete rewrite proposal to apply (Vision §38).
    jarvis.set_document_editor(build_document_editor(provider, model, base_url))
    # Persist on every switch so the choice (and model fixes) survive a restart; the key
    # line is only written when a key was provided, and is never read back into a reply.
    llm_config_store.persist(staged)
    described = describe(jarvis.perception)
    saved = " Key saved to .env." if api_key else ""
    if described.get("kind") == "keyword":
        return {
            "reply": f"Perceiver set to the keyword rule (no LLM in judgment).{saved}",
            "speak": False,
            "saved": bool(api_key),
        }
    named = described.get("model") or described.get("provider")
    return {
        "reply": f"Perceiver set to {described.get('provider')} ({named}).{saved}",
        "speak": False,
        "saved": bool(api_key),
    }


def _provider_health(jarvis: Jarvis, payload: Reply) -> Reply:
    """Probe one provider with a real minimal call and report what happened.

    Builds that provider's model from the UI choice (key read from the
    environment only, never echoed) and runs one tiny ``complete("ok")``,
    timing it. A success reports the latency; a failure reports the
    self-diagnosing provider error. This is a *probe*, not usage: it is not
    recorded in the instrumentation totals, so ``successes`` still counts only
    real work. Offline rules (keyword/scripted/stub) have no live endpoint to
    verify, which is reported honestly instead of faked.
    """
    _ = jarvis
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        return {"error": "Name a provider to probe."}
    if provider.lower() in _OFFLINE_PERCEIVERS:
        return {
            "ok": True,
            "reply": f"{provider} is an offline rule — nothing live to verify (deterministic).",
            "speak": False,
        }
    model = str(payload.get("model", "")).strip() or llm_config_store.resolve_model(
        provider.lower(), os.environ
    )
    if not model:
        return {"error": f"a model id is required to probe {provider!r}"}
    base_url = str(payload.get("base_url", "")).strip() or None
    try:
        timeout = float(os.environ.get("JARVIS_LLM_TIMEOUT", "30"))
    except ValueError:
        timeout = 30.0
    settings = ProviderSettings(
        provider=provider.lower(),
        model=model,
        base_url=base_url,
        api_key=llm_config_store.resolve_api_key(provider.lower(), os.environ),
        timeout=timeout,
        temperature=0.0,
    )
    try:
        model_adapter = build_language_model(settings)
    except ValueError as error:
        return {"ok": False, "reply": str(error), "speak": False}
    started = time.perf_counter()
    try:
        answer = model_adapter.complete("ok")
    except Exception as error:  # noqa: BLE001 - the external-provider boundary
        return {"ok": False, "reply": _provider_error(error), "speak": False}
    latency = round(time.perf_counter() - started, 3)
    head = answer.strip().replace("\n", " ")[:120]
    return {
        "ok": True,
        "reply": f"{provider} ({model}) answered in {latency}s: {head or '(empty reply)'}",
        "speak": False,
        "latency_seconds": latency,
    }


def _reasoner(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or switch the reasoner seam at runtime (Vision §37, §38).

    With no ``provider`` it reports whether provisional reasoning is live
    (``can_do``) or silent-offline. With one it swaps only the reasoner --
    perception, voice and companion stay as they are -- so the companion can
    aim provisional answers at a different model. Runtime-only: unlike the
    perceiver switch this is not persisted to ``.env`` (the saved config names
    one shared provider), and a restart resumes the perceiver's model.
    """
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        live = jarvis.can_do("reason with a language model")
        state = "live" if live else "silent (offline)"
        return {"reply": f"The reasoner is currently {state}.", "speak": False, "live": live}
    model = str(payload.get("model", "")).strip() or llm_config_store.resolve_model(
        provider.lower(), os.environ
    )
    base_url = str(payload.get("base_url", "")).strip() or None
    try:
        reasoner = build_reasoner(provider, model, base_url)
    except ValueError as error:
        return {"error": str(error)}
    jarvis.set_reasoner(reasoner)
    live = jarvis.can_do("reason with a language model")
    named = model or provider
    return {
        "reply": f"Reasoner set to {provider} ({named}) — "
        + ("live." if live else "silent (offline)."),
        "speak": False,
        "live": live,
    }


def _provider_reset(jarvis: Jarvis, _payload: Reply) -> Reply:
    """Forget every recorded provider call and count from zero (bookkeeping only)."""
    jarvis.reset_provider_stats()
    return {
        "reply": "Provider stats cleared — counting from zero.",
        "speak": False,
    }


def _embeddings(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or rewire meaning-based recall from ``JARVIS_EMBED_*`` (F9).

    With no action it reports whether recall runs by meaning or stays lexical.
    ``reload`` re-reads the environment and, when an embedder is configured,
    upgrades recall to it at runtime (lexical stays the fallback); when nothing
    is configured it says so honestly instead of pretending. Runtime-only: a
    restart rebuilds from the environment again.
    """
    action = str(payload.get("action", "")).strip().lower()
    if action and action != "reload":
        return {"reply": "Use embeddings with action 'reload' or none.", "speak": False}
    if not action:
        mode = _recall_block(jarvis)["mode"]
        detail = (
            "recall by meaning is live"
            if mode == "meaning"
            else "recall is lexical (set JARVIS_EMBED_MODEL, then reload)"
        )
        return {"reply": f"Recall mode: {mode} — {detail}.", "speak": False, "mode": mode}
    embedder = build_embedder()
    if embedder is None:
        return {
            "reply": "No embedder configured (JARVIS_EMBED_MODEL is empty) — recall stays lexical.",
            "speak": False,
        }
    jarvis.enable_embedding_recall(embedder)
    live = jarvis.can_do("recall by meaning")
    if live:
        return {"reply": "Recall upgraded to meaning-based.", "speak": False}
    return {
        "reply": "Embedder wired but the capability is not earned yet — "
        "recall stays lexical until acquired.",
        "speak": False,
    }


def _speech(jarvis: Jarvis, payload: Reply) -> Reply:
    """Report or rewire the ear from ``JARVIS_STT_*`` (F9).

    With no action it reports which ear hears (a live transcriber or the
    browser echo) and which model it claims. ``reload`` re-reads the
    environment and swaps the ear at runtime; secrets stay in ``.env``
    (this command never takes or echoes a key). Runtime-only.
    """
    action = str(payload.get("action", "")).strip().lower()
    if action and action != "reload":
        return {"reply": "Use speech with action 'reload' or none.", "speak": False}
    if not action:
        from jarvis.interface._state import _speech_block

        return {"reply": _speech_status(jarvis), "speak": False, **_speech_block(jarvis)}
    try:
        jarvis.set_speech_perception(speech_perception_from_env())
    except ValueError as error:
        return {"reply": f"Couldn't rewire the ear: {error}", "speak": False}
    from jarvis.interface._state import _speech_block

    return {"reply": _speech_status(jarvis), "speak": False, **_speech_block(jarvis)}


def _speech_status(jarvis: Jarvis) -> str:
    """One honest line about which ear hears right now."""
    source = jarvis.speech_perception
    if source is None:
        return "No ear wired — voice input is off."
    if source.can_hear_audio:
        model = f" ({source.model})" if source.model else ""
        return f"Live ear: {source.provider or 'server'}{model} — the mic records to it."
    return "Browser ear (Web Speech) — transcription happens in the page."
