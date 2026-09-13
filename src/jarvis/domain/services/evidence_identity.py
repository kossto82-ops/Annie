"""Evidence identity: same observation repeated vs independently confirmed.

The epistemic invariant is strict: a belief must never become stronger merely
because the exact same evidence was injected repeatedly. This module is the
single place that decides whether an incoming piece of evidence is *the same
observation* as one already held (skip it) or an *independent confirmation*
(count it). Beliefs, hypotheses and semantic memories all share it, so the
rule cannot drift between entity kinds.

Identity dimensions (all already on :class:`Evidence`, no parallel system):

* ``id`` -- observation identity. The same event re-injected (retries,
  replays, re-ingestion after a restart -- ids survive persistence) is
  always the same observation.
* ``content`` + ``source`` + ``supports`` + ``context`` -- the claim
  fingerprint: what was observed, by which channel, in which direction,
  with which provenance. A different source (independent channel) or
  different provenance (independent origin story) is a different
  observation, even for identical content.
* ``observed_at`` at **day granularity (UTC)** -- the source-event time.
  The same fingerprint re-recorded on the same day is a re-recording
  (double perception, retries, floods); the same fingerprint on different
  days is genuine temporal replication and counts (it also grows temporal
  stability, the spread axis).

Deliberate limitations, documented so they are not mistaken for bugs:

* Same-day repeats under-count: saying the same thing twice in one day
  counts once. Same-day repetition carries near-zero information, and
  collapsing it is what kills replay floods.
* Sub-day independence must be expressed through ``source`` or ``context``
  (provenance), not bare timestamps: two sensors firing seconds apart about
  the same fact should name their channels.
* ``weight`` is not identity: a stronger re-confirmation the same day does
  not replace the first recording. Strength affects credit, not identity.
* Content matches exactly (D11/D17): near-duplicates count separately.

Skipped duplicates are dropped silently: the observation is already
recorded, so nothing is lost and the trace is not flooded.
"""

from __future__ import annotations

from jarvis.domain.value_objects.evidence import Evidence


def same_observation(first: Evidence, second: Evidence) -> bool:
    """True when ``second`` is the same observation as ``first``.

    Matches the ``(existing, candidate)`` shape of the dedup seam, so this
    function plugs directly into :class:`Belief`, :class:`Hypothesis` and
    :class:`SemanticMemory` as their default policy.
    """
    if first.id == second.id:
        return True
    return (
        first.content == second.content
        and first.source == second.source
        and first.supports == second.supports
        and (first.context or None) == (second.context or None)
        and first.observed_at.date() == second.observed_at.date()
    )
