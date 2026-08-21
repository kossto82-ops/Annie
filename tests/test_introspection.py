"""Tests for Jarvis narrating itself from real state (Vision §29, §30, §40)."""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(weight: float, *, at: datetime | None = None) -> Evidence:
    kwargs: dict[str, object] = {
        "content": "an observation",
        "source": EvidenceSource.USER_STATEMENT,
        "weight": Confidence(weight),
    }
    if at is not None:
        kwargs["observed_at"] = at
    return Evidence(**kwargs)  # type: ignore[arg-type]


class TestIntrospect:
    def test_a_fresh_jarvis_admits_it_knows_little(self) -> None:
        text = Jarvis().introspect()
        assert "have not yet noticed any consistent tendencies" in text
        assert "do not yet know much about them" in text
        assert "0 past episode(s)" in text

    def test_it_surfaces_a_recognised_self_tendency(self) -> None:
        jarvis = Jarvis()
        for topic in ("a", "b", "c"):
            # grounded but same-instant evidence -> overconfidence
            jarvis.think(f"q {topic}", evidence=[_ev(0.9, at=_EPOCH), _ev(0.9, at=_EPOCH)])
        text = jarvis.introspect()
        assert "overconfident on thin evidence" in text

    def test_it_surfaces_what_it_believes_about_its_companion(self) -> None:
        jarvis = Jarvis()
        jarvis.observe_companion("prefers simplicity", _ev(0.9))
        text = jarvis.introspect()
        assert "prefers simplicity" in text

    def test_it_invents_nothing_it_does_not_hold(self) -> None:
        # A trait never observed must not appear in the self-account.
        text = Jarvis().introspect()
        assert "prefers simplicity" not in text
