"""The command center's brain, tested with no socket and no network (Vision §30).

Everything the control center decides — what Jarvis replies, what its live state is,
how tuning the energy budget changes behaviour — is a pure function over a Jarvis, so
it is exercised directly here. The socket in `server.py` only moves these bytes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.perception.companion_perception import CompanionObservation
from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.interface.command_center import handle, route, snapshot, stream_say


class _YesPerception(PerceptionSource):
    """A perceiver that reads any observation as one supporting piece of evidence."""

    def perceive(self, observation: str) -> tuple[Evidence, ...]:
        return (
            Evidence(
                content=observation,
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(1.0),
                supports=True,
            ),
        )


class TestSnapshot:
    def test_a_fresh_jarvis_is_all_empty(self) -> None:
        state = snapshot(Jarvis())
        assert state["episodes"] == 0
        assert state["self"] == []
        assert state["companion"] == []
        assert state["goals"] == []
        energy = state["energy"]
        assert isinstance(energy, dict)
        assert energy["spent"] == 0
        assert energy["remaining"] is None

    def test_it_reflects_a_set_budget(self) -> None:
        jarvis = Jarvis(energy_budget=10)
        energy = snapshot(jarvis)["energy"]
        assert isinstance(energy, dict)
        assert energy["remaining"] == 10


class TestSay:
    def test_it_replies_without_grounding_ordinary_conversation(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        result = handle(jarvis, "say", {"text": "the sky is clear today"})
        assert isinstance(result["reply"], str)
        assert result["reply"].strip() != ""
        assert result["speak"] is True
        assert "confidence" not in result
        assert jarvis.beliefs.all_beliefs() == ()
        state = result["state"]
        assert isinstance(state, dict)
        assert state["episodes"] == 0

    def test_empty_text_is_handled_without_thinking(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        result = handle(jarvis, "say", {"text": "   "})
        assert result["speak"] is False
        state = result["state"]
        assert isinstance(state, dict)
        assert state["episodes"] == 0

    def test_ungrounded_text_is_answered_honestly_not_invented(self) -> None:
        # Nothing to reason or recall: Jarvis stays in the conversation and invites more,
        # never fabricating an answer or exposing internal state.
        result = handle(Jarvis(), "say", {"text": "zxqw"})
        reply = str(result["reply"]).lower()
        assert "tell me more" in reply
        assert "confidence" not in result


class _CompanionReader:
    """A stand-in companion perceiver: reads any utterance as one learned trait."""

    def read_companion(self, utterance: str) -> tuple[CompanionObservation, ...]:
        return (
            CompanionObservation(
                trait="likes hiking",
                evidence=Evidence(
                    content=utterance,
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(0.9),
                    supports=True,
                ),
            ),
        )


class TestCompanionChannel:
    def test_talking_does_not_teach_without_an_explicit_memory_request(self) -> None:
        jarvis = Jarvis()
        jarvis.set_companion_perception(_CompanionReader())
        result = handle(jarvis, "say", {"text": "I went hiking this weekend"})
        assert "learned" not in result
        state = cast("dict[str, object]", result["state"])
        assert cast("list[dict[str, object]]", state["companion"]) == []

    def test_default_jarvis_learns_nothing_and_reply_is_unchanged(self) -> None:
        result = handle(Jarvis(), "say", {"text": "hola jarvis"})
        assert "learned" not in result
        assert "remember this about you" not in str(result["reply"])


class _MultiTraitReader:
    """A companion perceiver that reads a document into two fixed traits (offline)."""

    def read_companion(self, utterance: str) -> tuple[CompanionObservation, ...]:
        def obs(trait: str) -> CompanionObservation:
            return CompanionObservation(
                trait=trait,
                evidence=Evidence(
                    content=utterance,
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(0.8),
                    supports=True,
                ),
            )

        return (obs("works in customer service and IT"), obs("values honesty"))


class TestLearn:
    def test_it_folds_a_profile_into_the_companion_model(self) -> None:
        jarvis = Jarvis()
        jarvis.set_companion_perception(_MultiTraitReader())
        doc = (
            "## Work\nRaúl works in customer service and IT.\n\n"
            "## Values\nRaúl values honesty and clear thinking above all else."
        )
        result = handle(jarvis, "learn", {"text": doc})
        learned = cast("list[str]", result["learned"])
        assert len(learned) == 2
        assert "Learned 2 things" in str(result["reply"])
        # The traits are now real companion beliefs the snapshot exposes.
        state = cast("dict[str, object]", result["state"])
        assert len(cast("list[object]", state["companion"])) == 2

    def test_learning_with_no_llm_reports_it_cannot_extract(self) -> None:
        result = handle(Jarvis(), "learn", {"text": "## Me\nI am a curious person who builds."})
        assert result["learned"] == []
        assert "LLM perceiver" in str(result["reply"])

    def test_empty_text_just_asks(self) -> None:
        result = handle(Jarvis(), "learn", {"text": "   "})
        assert result["speak"] is False
        assert "learned" not in result


class TestGreeting:
    def test_offline_greeting_is_warm_not_robotic(self) -> None:
        result = handle(Jarvis(), "greeting", {})
        reply = str(result["reply"])
        assert reply.strip() != ""
        assert result["speak"] is False
        # The old robotic opener is gone.
        assert "reason from evidence, not invent" not in reply

    def test_greeting_shifts_once_it_knows_you(self) -> None:
        jarvis = Jarvis()
        jarvis.set_companion_perception(_CompanionReader())
        handle(jarvis, "learn", {"text": "I went hiking"})
        result = handle(jarvis, "greeting", {})
        assert "again" in str(result["reply"]).lower()


class _UpperVoice:
    """A stand-in renderer: proves the reply is passed through jarvis.voice."""

    def phrase(self, reply: str, like: str) -> str:
        return reply.upper()

    def phrase_stream(self, reply: str, like: str) -> Iterator[str]:
        yield reply.upper()


class TestVoice:
    def test_say_replies_are_voiced_through_the_renderer(self) -> None:
        jarvis = Jarvis()
        jarvis.set_voice(_UpperVoice())
        result = handle(jarvis, "say", {"text": "hola"})
        assert str(result["reply"]) == str(result["reply"]).upper()

    def test_the_default_voice_leaves_the_reply_untouched(self) -> None:
        result = handle(Jarvis(), "say", {"text": "the deploy definitely succeeded"})
        # IdentityRenderer default: the canonical English reply passes through unchanged.
        assert "tell me more and we'll reason it through together" in str(result["reply"])


class TestStreamSay:
    def test_it_emits_meta_then_chunks_then_done(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        events = list(stream_say(jarvis, {"text": "the deploy passed"}))
        kinds = [name for name, _ in events]
        assert kinds[0] == "meta"
        assert kinds[-1] == "done"
        assert "chunk" in kinds
        # Meta carries the reasoning + live state; the reply is assembled from chunks.
        meta = dict(events[0][1])
        assert "state" in meta and "provenance" in meta
        full = "".join(str(d["text"]) for name, d in events if name == "chunk")
        assert full.strip() != ""
        assert str(events[-1][1]["reply"]) == full

    def test_chunks_are_voiced_through_the_renderer(self) -> None:
        jarvis = Jarvis()
        jarvis.set_voice(_UpperVoice())
        events = list(stream_say(jarvis, {"text": "hola"}))
        full = "".join(str(d["text"]) for name, d in events if name == "chunk")
        assert full == full.upper() and full.strip() != ""

    def test_empty_text_yields_a_single_done(self) -> None:
        events = list(stream_say(Jarvis(), {"text": "   "}))
        assert [name for name, _ in events] == ["done"]


class TestReasoning:
    def test_say_keeps_internal_provenance_out_of_ordinary_conversation(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        result = handle(jarvis, "say", {"text": "the deploy succeeded"})
        assert result["provenance"] is None
        assert result["trace"] == []
        assert jarvis.beliefs.all_beliefs() == ()
        assert jarvis.episodes.history() == ()

    def test_the_internal_working_label_never_leaks_to_the_user(self) -> None:
        reply = handle(Jarvis(), "say", {"text": "hola jarvis"})
        assert "Working conclusion about" not in json.dumps(reply)
        assert str(reply["reply"]).strip() != ""

    def test_explain_returns_the_grounds_for_explicit_cognition(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        jarvis.perceive("coffee helps me focus")
        result = handle(jarvis, "explain", {"topic": "coffee helps me focus"})
        prov = result["provenance"]
        assert isinstance(prov, dict)
        assert prov["statement"]

    def test_explain_is_honest_about_an_unknown_topic(self) -> None:
        result = handle(Jarvis(), "explain", {"topic": "the meaning of life"})
        assert result["provenance"] is None
        assert "don't hold a view" in str(result["reply"])


class TestState:
    def test_state_command_returns_only_the_snapshot(self) -> None:
        result = handle(Jarvis(), "state", {})
        assert set(result) == {"state"}


class TestReflect:
    def test_it_runs_the_cycle_and_reports(self) -> None:
        # Two beliefs resting on the same observation give Reflect something to find.
        jarvis = Jarvis()
        shared = Evidence(
            content="the same reading appears twice",
            source=EvidenceSource.SYSTEM_OBSERVATION,
            weight=Confidence(1.0),
        )
        jarvis.think("topic one", evidence=[shared])
        jarvis.think("topic two", evidence=[shared])
        result = handle(jarvis, "reflect", {})
        assert isinstance(result["reply"], str)
        assert "cycle" in result

    def test_nothing_to_reflect_on_is_honest(self) -> None:
        result = handle(Jarvis(), "reflect", {})
        assert result["cycle"] is None
        assert "nothing" in str(result["reply"]).lower()


class TestIntrospectAndWonder:
    def test_introspect_returns_a_self_account(self) -> None:
        result = handle(Jarvis(), "introspect", {})
        assert "myself" in str(result["reply"]).lower()

    def test_wonder_is_calm_when_nothing_pulls(self) -> None:
        result = handle(Jarvis(), "wonder", {})
        assert "curiosity" in str(result["reply"]).lower()


class TestTuning:
    def test_setting_a_budget_makes_state_show_it(self) -> None:
        jarvis = Jarvis()
        result = handle(jarvis, "energy_budget", {"budget": 12})
        state = result["state"]
        assert isinstance(state, dict)
        energy = cast("dict[str, object]", state["energy"])
        assert energy["remaining"] == 12

    def test_clearing_the_budget_returns_to_unbounded(self) -> None:
        jarvis = Jarvis(energy_budget=5)
        result = handle(jarvis, "energy_budget", {"budget": None})
        state = result["state"]
        assert isinstance(state, dict)
        energy = cast("dict[str, object]", state["energy"])
        assert energy["remaining"] is None

    def test_rest_refills_after_spending(self) -> None:
        jarvis = Jarvis(energy_budget=6)
        jarvis.think("spend some energy")
        handle(jarvis, "rest", {})
        assert jarvis.energy_remaining() == 6


class TestPerceiver:
    @pytest.fixture(autouse=True)
    def _isolate_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Every switch now stages into the process env and persists to .env; point that
        # file at a temp path and revert the JARVIS_LLM_* vars so no test leaks config.
        monkeypatch.setenv("JARVIS_ENV_FILE", str(tmp_path / ".env"))
        for var in (
            "PROVIDER", "MODEL", "BASE_URL", "API_KEY",
            "KEY_GROQ", "KEY_NVIDIA", "MODEL_GROQ", "MODEL_NVIDIA", "MODEL_OLLAMA",
        ):
            monkeypatch.delenv(f"JARVIS_LLM_{var}", raising=False)

    def test_snapshot_reports_the_live_perceiver_and_available_ones(self) -> None:
        # A default Jarvis reads the world with the keyword rule.
        state = snapshot(Jarvis())
        perceiver = cast("dict[str, object]", state["perceiver"])
        assert perceiver["kind"] == "keyword"
        available = cast("list[str]", perceiver["available"])
        assert "keyword" in available
        assert "groq" in available

    def test_no_provider_just_asks(self) -> None:
        result = handle(Jarvis(), "perceiver", {})
        assert result["speak"] is False
        assert "provider" in str(result["reply"]).lower()

    def test_switching_to_a_real_provider_swaps_the_perceiver(self) -> None:
        jarvis = Jarvis()
        result = handle(jarvis, "perceiver", {"provider": "groq", "model": "llama-3.3-70b"})
        state = cast("dict[str, object]", result["state"])
        perceiver = cast("dict[str, object]", state["perceiver"])
        assert perceiver["kind"] == "llm"
        assert perceiver["provider"] == "groq"
        assert perceiver["model"] == "llama-3.3-70b"

    def test_switching_back_to_keyword(self) -> None:
        jarvis = Jarvis()
        handle(jarvis, "perceiver", {"provider": "groq", "model": "llama-3.3-70b"})
        result = handle(jarvis, "perceiver", {"provider": "keyword"})
        state = cast("dict[str, object]", result["state"])
        perceiver = cast("dict[str, object]", state["perceiver"])
        assert perceiver["kind"] == "keyword"

    def test_a_real_provider_without_a_model_is_a_clear_error(self) -> None:
        result = handle(Jarvis(), "perceiver", {"provider": "groq"})
        assert "error" in result
        assert "model" in str(result["error"]).lower()

    def test_an_api_key_is_saved_to_env_and_never_echoed(self, tmp_path: Path) -> None:
        secret = "gsk_do_not_leak_me"
        result = handle(
            Jarvis(),
            "perceiver",
            {"provider": "groq", "model": "llama-3.3-70b", "api_key": secret},
        )
        # The key is persisted for a restart, under the provider's own slot...
        assert "JARVIS_LLM_KEY_GROQ=" + secret in (tmp_path / ".env").read_text(encoding="utf-8")
        # ...but never echoed back anywhere in the reply or the live snapshot.
        assert result["saved"] is True
        assert secret not in json.dumps(result)

    def test_a_key_without_a_model_is_rejected_before_being_saved(self, tmp_path: Path) -> None:
        result = handle(
            Jarvis(), "perceiver", {"provider": "groq", "api_key": "gsk_secret"}
        )
        assert "error" in result
        assert not (tmp_path / ".env").exists()  # nothing half-formed was written

    def test_switching_the_model_persists_per_provider(self, tmp_path: Path) -> None:
        # Fixing just the model (no key) must take effect AND survive a restart,
        # stored under the provider's own slot.
        handle(Jarvis(), "perceiver", {"provider": "groq", "model": "some-model"})
        env_text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "JARVIS_LLM_MODEL_GROQ=some-model" in env_text
        assert "JARVIS_LLM_PROVIDER=groq" in env_text

    def test_switching_back_recalls_the_saved_model(self) -> None:
        jarvis = Jarvis()
        handle(jarvis, "perceiver", {"provider": "groq", "model": "gpt-oss"})
        handle(jarvis, "perceiver", {"provider": "keyword"})
        # Switch back to groq WITHOUT typing a model — it recalls the saved one.
        result = handle(jarvis, "perceiver", {"provider": "groq"})
        state = cast("dict[str, object]", result["state"])
        perceiver = cast("dict[str, object]", state["perceiver"])
        assert perceiver["model"] == "gpt-oss"
        # The snapshot exposes saved models so the UI can auto-fill the field.
        models = cast("dict[str, str]", perceiver["models"])
        assert models.get("groq") == "gpt-oss"


class TestUnknownCommand:
    def test_it_is_a_clear_error_with_live_state(self) -> None:
        result = handle(Jarvis(), "does-not-exist", {})
        assert "error" in result
        assert "state" in result


class TestRoute:
    def test_root_serves_the_console_page(self) -> None:
        response = route(Jarvis(), "GET", "/", b"")
        assert response.status == 200
        assert "text/html" in response.content_type
        assert b"command center" in response.body.lower()

    def test_get_state_returns_json(self) -> None:
        response = route(Jarvis(), "GET", "/api/state", b"")
        assert response.status == 200
        assert "application/json" in response.content_type
        assert b"episodes" in response.body

    def test_post_say_reasons_and_returns_json(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        response = route(jarvis, "POST", "/api/say", b'{"text": "the light is on"}')
        assert response.status == 200
        assert b"reply" in response.body

    def test_unknown_path_is_404(self) -> None:
        response = route(Jarvis(), "GET", "/nope", b"")
        assert response.status == 404

    def test_unknown_command_is_400(self) -> None:
        response = route(Jarvis(), "POST", "/api/bogus", b"{}")
        assert response.status == 400

    def test_malformed_body_is_tolerated(self) -> None:
        response = route(Jarvis(), "POST", "/api/say", b"not json at all")
        assert response.status == 200

    def test_non_utf8_body_is_tolerated(self) -> None:
        # A body that isn't valid UTF-8 must not 500 (Latin-1 "ñ" = 0xf1).
        response = route(Jarvis(), "POST", "/api/say", b'{"text": "monta\xf1a"}')
        assert response.status == 200
