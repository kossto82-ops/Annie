"""Scheduled honest forgetting (roadmap F2, Vision §10, §22).

Forgetting is *suggested*, never automatic: this service identifies beliefs that
have effectively faded (low effective confidence, stale, or evidence-less) under
an injected weighting policy, holds them back under two honesty gates, and
deletes nothing -- :meth:`ForgettingCandidates.apply` is the only path that
touches the store, and only for statements the caller explicitly named.

Both gates are checked at :meth:`identify` and re-checked at :meth:`apply`
(defense-in-depth: a belief can fade between the dry-run and the apply):

- **grounded companion traits never leave**: a companion trait whose derived
  confidence is at or above the grounded threshold is who the companion says
  they are; suggesting it would nag, deleting it would be destructive.
- **anti-nagging**: a belief whose memory was just renewed (its latest evidence
  landed inside the reaffirm window) is not one that is fading -- surfacing it as
  forgettable right after it was reinforced would be nagging.

The service stays read-only until :meth:`apply`; a health report can be shown
endlessly without deleting a single belief (read-only surfaces stay honest).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.repositories.belief_repository import BeliefRepository
from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
from jarvis.domain.services.memory_consolidation import (
    ForgettingCandidate,
    identify_forgetting_candidates,
)

# A reaffirmed trait stays protected for this long after its last reinforcement:
# it was just agreed on, so even a faded memory is a live one (anti-nagging).
REAFFIRM_WINDOW = timedelta(days=30)
# The default grounded-confidence bar, used when no live knob source is injected.
DEFAULT_GROUNDED_CONFIDENCE = 0.5


@dataclass(frozen=True, slots=True)
class ForgettingProfile:
    """What a dry-run found, split by what may and may not be forgotten.

    ``candidates`` are the beliefs that may be forgotten; ``grounded_protected``
    and ``reaffirmed_excluded`` are the ones the gates held back, so a health
    report can show *why* a faded trait is still around instead of nagging it.
    """

    candidates: tuple[ForgettingCandidate, ...]
    grounded_protected: tuple[str, ...]
    reaffirmed_excluded: tuple[str, ...]
    swept_at: datetime


@dataclass(frozen=True, slots=True)
class ForgettingResult:
    """What an explicit apply actually did, split by outcome."""

    forgotten: tuple[str, ...]
    refused: tuple[str, ...]
    missing: tuple[str, ...]


class ForgettingCandidates:
    """The scheduled-forgetting service behind Jarvis's memory health.

    Composed with the belief repository, the companion model (for the grounded
    gate) and the injected weighting policy (roadmap F2: the root-injectable
    bias is the *same* policy that decays belief confidence), so the health
    report and the actual decision logic agree with the live epistemic stance.
    """

    def __init__(
        self,
        beliefs: BeliefRepository,
        *,
        companion: CompanionModel,
        grounded_confidence: Callable[[], float] = lambda: DEFAULT_GROUNDED_CONFIDENCE,
        weighting_policy: EvidenceWeightingPolicy | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        threshold: float | None = None,
        stale_after: timedelta | None = None,
        reaffirm_window: timedelta = REAFFIRM_WINDOW,
    ) -> None:
        self._beliefs = beliefs
        self._companion = companion
        self._grounded_confidence = grounded_confidence
        self._weighting_policy = weighting_policy
        self._now = now
        from jarvis.domain.services.memory_consolidation import (  # noqa: PLC0415
            FORGETTABLE_THRESHOLD,
            STALE_AFTER,
        )

        self._threshold = FORGETTABLE_THRESHOLD if threshold is None else threshold
        self._stale_after = STALE_AFTER if stale_after is None else stale_after
        self._reaffirm_window = reaffirm_window

    def identify(self) -> ForgettingProfile:
        """A read-only dry-run: which beliefs *may* fade, and which the gates hold."""
        swept_at = self._now()
        companion_statements = {b.statement for b in self._companion.beliefs()}
        grounded_bar = self._grounded_confidence()
        candidates: list[ForgettingCandidate] = []
        protected: list[str] = []
        reaffirmed: list[str] = []

        for cand in identify_forgetting_candidates(
            self._beliefs,
            now=swept_at,
            threshold=self._threshold,
            stale_after=self._stale_after,
            weighting_policy=self._weighting_policy,
        ):
            belief = cand.belief
            # Grounded gate: who the companion says they are never fades away.
            if (
                belief.statement in companion_statements
                and belief.confidence.value >= grounded_bar
            ):
                protected.append(belief.statement)
                continue
            # Anti-nagging gate: recently renewed memories are not fading.
            if (
                cand.last_reinforced is not None
                and swept_at - cand.last_reinforced <= self._reaffirm_window
            ):
                reaffirmed.append(belief.statement)
                continue
            candidates.append(cand)

        candidates.sort(key=lambda c: (c.effective_confidence, c.belief.statement))
        protected.sort()
        reaffirmed.sort()
        return ForgettingProfile(
            candidates=tuple(candidates),
            grounded_protected=tuple(protected),
            reaffirmed_excluded=tuple(reaffirmed),
            swept_at=swept_at,
        )

    def apply(self, statements: Sequence[str]) -> ForgettingResult:
        """Delete exactly the explicitly named beliefs -- and only those.

        This is the only non-read-only path, so "never forgets without an
        explicit apply" holds by construction. The gates are re-checked at apply
        time: a statement the user names but the gates now protect is ``refused``
        (honest decline, Vision §37); an unknown statement is ``missing``; only
        the rest are deleted.
        """
        requested = {s.strip() for s in statements if s.strip()}
        if not requested:
            return ForgettingResult(forgotten=(), refused=(), missing=())
        profile = self.identify()
        forbidden = set(profile.grounded_protected) | set(profile.reaffirmed_excluded)
        store = _known_statements(self._beliefs)

        forgotten: list[str] = []
        refused: list[str] = []
        missing: list[str] = []
        for statement in sorted(requested):
            if statement in forbidden:
                refused.append(statement)
                continue
            if statement not in store:
                missing.append(statement)
                continue
            if self._beliefs.forget(statement):
                forgotten.append(statement)
            else:
                missing.append(statement)

        return ForgettingResult(
            forgotten=tuple(forgotten),
            refused=tuple(refused),
            missing=tuple(missing),
        )


def _known_statements(beliefs: BeliefRepository) -> set[str]:
    return {b.statement for b in beliefs.all_beliefs()}