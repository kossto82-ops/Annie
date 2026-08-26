"""A single LIVE round-trip to a real provider (Vision §32).

Skipped unless the environment is configured, so CI and offline runs stay green
with zero network. To exercise it, set the JARVIS_LLM_* variables (a Groq key, or
a local Ollama needs no key) and run the suite:

    JARVIS_LLM_PROVIDER=groq JARVIS_LLM_MODEL=llama-3.3-70b-versatile \
    JARVIS_LLM_API_KEY=... python -m pytest tests/test_live_llm.py

    # or a fully-local SLM, no key:
    JARVIS_LLM_PROVIDER=ollama JARVIS_LLM_MODEL=llama3 python -m pytest tests/test_live_llm.py
"""

from __future__ import annotations

import os

import pytest

from jarvis import Jarvis
from jarvis.infrastructure.env_settings import language_model_from_env
from jarvis.infrastructure.llm_perception import LlmPerception

_PROVIDER = os.environ.get("JARVIS_LLM_PROVIDER", "").strip().lower()
_CONFIGURED = _PROVIDER not in ("", "scripted", "stub") and bool(
    os.environ.get("JARVIS_LLM_MODEL")
)
_skip = pytest.mark.skipif(
    not _CONFIGURED, reason="JARVIS_LLM_* not configured for a live provider"
)


@_skip
def test_a_real_provider_returns_text() -> None:
    model = language_model_from_env()
    reply = model.complete("Reply with exactly one word: pong")
    assert isinstance(reply, str)
    assert reply.strip() != ""


@_skip
def test_perception_grounds_a_belief_from_a_real_model() -> None:
    jarvis = Jarvis(perception=LlmPerception(language_model_from_env()))
    episode = jarvis.perceive(
        "The rocket launched successfully and reached orbit.",
        trigger="did the launch go well?",
    )
    # A real model may or may not return usable claims; either way the episode must
    # complete honestly, never crash.
    assert episode.result is not None
