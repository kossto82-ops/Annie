"""Topic resolution: derived topic identity for episodes (Cognitive Repair §A).

The conceptual-signature abstraction (``abstraction.conceptual_tokens``) answers
*what an episode is about* in canonical tokens -- its topic identity.  The raw
trigger is only ever *display* metadata: "the kitchen lights" and "the overhead
light in the kitchen" are the same topic if they resolve to the same concepts,
and they remain visually distinct because each episode keeps its own trigger.

Everything here is derived per read from a set of episodes: reversible,
deterministic, and never a second authoritative learning state.

Topic identity is *historical*: ``resolve_episodes`` groups every episode it is
given, in first-seen order, and a topic's canonical signature is fixed by its
chronological founder.  Identity never depends on the attention window (bounded
attention is the attention service's concern, not this module's): whether older
episodes are still inside the 50-episode attention horizon cannot change what a
topic is.

Compatibility rule: a new signature ``S`` joins an existing topic ``T`` when
    - ``S == T.canonical_signature`` (exact identity), or
    - ``S`` and ``T`` share at least two concepts and are nested
      (``|S ∩ T| >= 2 and (S ⊆ T or T ⊆ S)``).

The containment is symmetric: a narrower follow-up ("supplier failed to deliver"
after "the vendor missed the delivery deadline") joins the same topic family as
a broader follow-up.  A single-concept ``S`` can never absorb another topic (the
intersection cannot reach two).  A signature compatible with more than one
existing topic starts a new topic: ambiguity is safer than erroneous merging
(uncertainty stays representable, hypotheses are not collapsed prematurely).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.abstraction import conceptual_tokens
from jarvis.domain.value_objects.episode_record import EpisodeRecord

# Ordering separator for a canonical-signature topic id, e.g. "DELIVER > FAIL".
_SIGNATURE_JOIN = " > "


def signature_of(trigger: str) -> frozenset[str]:
    """The canonical concept set of a trigger (entity-independent)."""
    return conceptual_tokens(trigger)


def topic_id_of(trigger: str) -> str:
    """Stable topic id for a lone episode: its canonical signature, or the
    trigger itself when the trigger resolves to no concepts (so two concept-free
    episodes never collapse into the same topic)."""
    signature = signature_of(trigger)
    if not signature:
        return trigger
    return _SIGNATURE_JOIN.join(sorted(signature))


@dataclass(frozen=True, slots=True)
class ResolvedTopic:
    """One topic discovered in a set of episodes.

    ``topic_id`` is the stable identity (the topic's canonical signature, or the
    bootstrap trigger for concept-free topics).  ``canonical_signature`` is the
    concept set that bootstrapped the topic; it never changes as later episodes
    join, keeping the identity stable across the episode history and restarts.
    ``representative_trigger`` is *display* metadata only -- the most recent
    episode's trigger, meant to be shown, never used as identity.
    """

    topic_id: str
    canonical_signature: frozenset[str]
    representative_trigger: str
    source_episode_ids: tuple[str, ...]
    triggers: tuple[str, ...]
    external_count: int


def _compatible(signature: frozenset[str], topic: ResolvedTopic) -> bool:
    """Compatibility rule: exact identity, or symmetric nested containment.

    ``S`` joins ``T`` when it shares at least two concepts and one signature is
    contained in the other -- narrower and broader follow-ups both join the
    topic family.  Concept-free "signatures" never match anything: an episode
    that resolves to no concepts has no topic identity beyond its own trigger,
    so concept-free episodes never collapse into one topic.
    """
    canonical = topic.canonical_signature
    if not signature or not canonical:
        return False
    if signature == canonical:
        return True
    return len(signature & canonical) >= 2 and (
        signature <= canonical or canonical <= signature
    )


def resolve_episodes(
    episodes: Sequence[EpisodeRecord],
) -> tuple[ResolvedTopic, ...]:
    """Group episodes into topics, in first-seen order.

    Resolution covers *everything* passed in -- the caller decides the scope.
    The attention service passes the complete external history, so identity is
    historical and stable under eviction: an episode leaving the attention
    window cannot change a topic's canonical signature, membership, or
    provenance (it is never deleted from the episode store).  A caller that
    wants a smaller scope slices before calling.

    Pure and reversible: the same episodes always resolve to the same topics,
    and nothing is mutated.  ``external_count`` counts the episodes that came
    from the companion (self-generated episodes never count toward attention
    signals, so attention cannot become a self-reinforcing loop).
    """
    if not episodes:
        return ()

    topics: list[ResolvedTopic] = []
    for record in episodes:
        signature = signature_of(record.trigger)
        candidates = [t for t in topics if _compatible(signature, t)]
        if len(candidates) == 1:
            topic = candidates[0]
            topics[topics.index(topic)] = _join(topic, record)
        else:
            topics.append(
                ResolvedTopic(
                    topic_id=(
                        _SIGNATURE_JOIN.join(sorted(signature))
                        if signature
                        else record.trigger
                    ),
                    canonical_signature=signature,
                    representative_trigger=record.trigger,
                    source_episode_ids=(record.episode_id,),
                    triggers=(record.trigger,),
                    external_count=(
                        1 if record.origin is TriggerOrigin.COMPANION else 0
                    ),
                )
            )
    return tuple(topics)


def _join(topic: ResolvedTopic, record: EpisodeRecord) -> ResolvedTopic:
    """Return ``topic`` extended by one more episode (order preserved)."""
    return ResolvedTopic(
        topic_id=topic.topic_id,
        canonical_signature=topic.canonical_signature,
        representative_trigger=record.trigger,
        source_episode_ids=(*topic.source_episode_ids, record.episode_id),
        triggers=(*topic.triggers, record.trigger),
        external_count=topic.external_count
        + (1 if record.origin is TriggerOrigin.COMPANION else 0),
    )