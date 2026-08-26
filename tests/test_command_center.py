"""The command center's brain, tested with no socket and no network (Vision §30).

Everything the control center decides — what Jarvis replies, what its live state is,
how tuning the energy budget changes behaviour — is a pure function over a Jarvis, so
it is exercised directly here. The socket in `server.py` only moves these bytes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.perception.companion_perception import CompanionObservation
from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.interface.command_center import handle, route, snapshot


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
    def test_it_grounds_a_belief_and_replies(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        result = handle(jarvis, "say", {"text": "the sky is clear today"})
        assert isinstance(result["reply"], str)
        assert result["reply"].strip() != ""
        assert result["speak"] is True
        assert isinstance(result["confidence"], float)
        state = result["state"]
        assert isinstance(state, dict)
        assert state["episodes"] == 1

    def test_empty_text_is_handled_without_thinking(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        result = handle(jarvis, "say", {"text": "   "})
        assert result["speak"] is False
        state = result["state"]
        assert isinstance(state, dict)
        assert state["episodes"] == 0

    def test_ungrounded_text_is_answered_honestly_not_invented(self) -> None:
        # The default keyword perceiver makes nothing of this, so Jarvis must say so.
        result = handle(Jarvis(), "say", {"text": "zxqw"})
        reply = str(result["reply"]).lower()
        assert "enough" in reply or "evidence" in reply


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
    def test_talking_teaches_jarvis_about_the_companion(self) -> None:
        jarvis = Jarvis()
        jarvis.set_companion_perception(_CompanionReader())
        result = handle(jarvis, "say", {"text": "I went hiking this weekend"})
        # The reply acknowledges what it learned, and the snapshot shows the trait.
        assert "likes hiking" in str(result["reply"])
        assert result["learned"] == ["likes hiking"]
        state = cast("dict[str, object]", result["state"])
        companion = cast("list[dict[str, object]]", state["companion"])
        assert any(row["statement"] == "likes hiking" for row in companion)

    def test_default_jarvis_learns_nothing_and_reply_is_unchanged(self) -> None:
        result = handle(Jarvis(), "say", {"text": "hola jarvis"})
        assert "learned" not in result
        assert "remember this about you" not in str(result["reply"])


class TestReasoning:
    def test_say_carries_provenance_and_a_step_trace(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        result = handle(jarvis, "say", {"text": "the deploy succeeded"})
        prov = cast("dict[str, object]", result["provenance"])
        assert isinstance(prov["confidence"], float)
        supporting = cast("list[object]", prov["supporting"])
        assert len(supporting) >= 1
        first = cast("dict[str, object]", supporting[0])
        assert set(first) == {"content", "source", "weight"}
        trace = cast("list[object]", result["trace"])
        # The episode must at least start and conclude, in order.
        steps = [cast("dict[str, object]", s)["step"] for s in trace]
        assert steps[0] == "started"
        assert steps[-1] == "concluded"

    def test_the_internal_working_label_never_leaks_to_the_user(self) -> None:
        # Grounded and ungrounded replies must both name the subject in plain words,
        # never the internal "Working conclusion about:" identity label.
        grounded = handle(
            Jarvis(perception=_YesPerception()), "say", {"text": "the build passed"}
        )
        assert "Working conclusion about" not in json.dumps(grounded)
        prov = cast("dict[str, object]", grounded["provenance"])
        assert prov["statement"] == "the build passed"
        ungrounded = handle(Jarvis(), "say", {"text": "hola jarvis"})
        assert "Working conclusion about" not in json.dumps(ungrounded)
        assert "hola jarvis" in str(ungrounded["reply"])

    def test_ungrounded_say_still_returns_a_trace_and_empty_grounds(self) -> None:
        # With no evidence Jarvis still forms an (empty) working belief and concludes
        # honestly — the panel shows a real trace with no grounds, not a fabrication.
        result = handle(Jarvis(), "say", {"text": "zxqw"})
        prov = cast("dict[str, object]", result["provenance"])
        assert prov["supporting"] == []
        assert isinstance(result["trace"], list)

    def test_explain_returns_the_grounds_for_a_held_belief(self) -> None:
        jarvis = Jarvis(perception=_YesPerception())
        handle(jarvis, "say", {"text": "coffee helps me focus"})
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

    @staticmethod
    def _isolate_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
        # Record the JARVIS_LLM_* vars so monkeypatch reverts whatever `stage` sets in
        # the real process env — keeping this test from leaking into others.
        for var in ("PROVIDER", "MODEL", "BASE_URL", "API_KEY"):
            monkeypatch.delenv(f"JARVIS_LLM_{var}", raising=False)

    def test_an_api_key_is_saved_to_env_and_never_echoed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._isolate_llm_env(monkeypatch)
        env_file = tmp_path / ".env"
        monkeypatch.setenv("JARVIS_ENV_FILE", str(env_file))
        secret = "gsk_do_not_leak_me"
        result = handle(
            Jarvis(),
            "perceiver",
            {"provider": "groq", "model": "llama-3.3-70b", "api_key": secret},
        )
        # The key is persisted for a restart...
        assert "JARVIS_LLM_API_KEY=" + secret in env_file.read_text(encoding="utf-8")
        # ...but never echoed back anywhere in the reply or the live snapshot.
        assert result["saved"] is True
        assert secret not in json.dumps(result)

    def test_a_key_without_a_model_is_rejected_before_being_saved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._isolate_llm_env(monkeypatch)
        env_file = tmp_path / ".env"
        monkeypatch.setenv("JARVIS_ENV_FILE", str(env_file))
        result = handle(
            Jarvis(), "perceiver", {"provider": "groq", "api_key": "gsk_secret"}
        )
        assert "error" in result
        assert not env_file.exists()  # nothing half-formed was written


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
