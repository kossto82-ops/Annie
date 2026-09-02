"""capability_gap_observation: Jarvis noticing what it keeps failing to answer.

Odysseus normally starts from a *need someone voices* (:func:`recognise_need`).
This is the self-initiated half (Vision §34): when Jarvis keeps completing
episodes without a grounded conclusion about the same subject, those failures
are evidence of a *capability gap* -- a place where it plainly could not answer.
Each failed episode is grouped with the others that mention the same subject
words, and each recurring cluster is reported as a gap. The function only
*detects*: turning a gap into an evidence-grounded need belief is the caller's
job, so detection stays read-only and repeatable without side effects.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.value_objects.episode_record import EpisodeRecord

# Below this conclusion confidence an episode counts as "I could not answer".
# Mirrors the executive's GROUNDED_CONFIDENCE_THRESHOLD (D14), like the
# self-observation module which keeps the same constant at the same level.
_GROUNDED_CONFIDENCE: float = 0.5

# A subject must fail more than once before it is a *recurring* gap worth naming.
_MINIMUM_RECURRENCE: int = 2

_WORD = re.compile(r"\w+")

# Function words that carry no subject meaning (English + the Spanish the core
# already listens for). Exact keyword matching is deliberately shallow, like the
# scout: it names the recurring topic, it does not model it (D11).
_STOPWORDS = frozenset(
    {
        "about", "above", "after", "again", "all", "also", "am", "an", "and",
        "any", "are", "as", "at", "be", "because", "been", "before", "being",
        "but", "by", "can", "cant", "cannot", "could", "did", "do", "does",
        "doing", "down", "during", "each", "for", "from", "had", "has", "have",
        "having", "he", "her", "here", "hers", "him", "his", "how", "i", "if",
        "in", "into", "is", "it", "its", "just", "me", "more", "most", "my",
        "no", "not", "now", "of", "off", "on", "or", "our", "ours", "out",
        "over", "own", "she", "should", "so", "some", "than", "that", "the",
        "their", "them", "then", "there", "these", "they", "this", "those",
        "through", "to", "too", "under", "until", "up", "us", "very", "was",
        "we", "were", "what", "when", "where", "which", "while", "who", "whom",
        "why", "will", "with", "you", "your", "yours",
        "de", "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o",
        "u", "que", "en", "con", "por", "para", "se", "su", "sus", "es",
        "son", "hay", "como", "hacia", "sobre", "entre", "del", "al", "ante",
        "pero", "mas", "muy", "este", "esta", "esto", "ese", "esa", "eso",
        "otro", "otra", "tambien", "ya", "cuando", "donde", "quien",
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityGap:
    """A subject Jarvis keeps failing to answer about, with the episodes that
    failed it. ``subject`` is the content word naming the gap (the one appearing
    in the most failed episodes); the episodes are the evidence it is grounded
    in."""

    subject: str
    episodes: tuple[EpisodeRecord, ...]


def _content_words(trigger: str) -> frozenset[str]:
    """The words of a trigger that could name a subject (no function words,
    no bare digits, nothing too short to be meaningful). Common plural endings
    (English ``s``/``es``/``ies`` and the Spanish ``s``/``es``/``os``/``as``) are
    folded to their base so 'quokka' and 'quokkas' count as the same subject —
    exact keyword matching, deliberately shallow (D11), not full stemming.
    """
    return frozenset(
        _singularize(word)
        for word in _WORD.findall(trigger.lower())
        if len(word) > 2 and word.isalpha() and word not in _STOPWORDS
    )


def _singularize(word: str) -> str:
    """Fold a small set of common plural endings to the base form."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def _failed(record: EpisodeRecord) -> bool:
    """A conclusion Jarvis could not ground counts as a failed attempt, whether
    the question came from the companion or from its own curiosity -- either
    way it could not answer."""
    return (
        record.kind is EpisodeKind.CONCLUSION
        and record.conclusion_confidence.value < _GROUNDED_CONFIDENCE
    )


def detect_capability_gaps(
    history: Sequence[EpisodeRecord],
) -> tuple[CapabilityGap, ...]:
    """The recurring subjects in ``history`` that Jarvis kept failing to answer.

    Failed (ungrounded) conclusions are clustered into groups connected by a
    shared content word; a group of at least :data:`_MINIMUM_RECURRENCE` such
    episodes is a gap. The gap's subject is the content word appearing in the
    most of its episodes (earliest alphabetically on a tie), and its episodes
    are the failed records -- later turned into evidence by the caller. Gaps are
    returned strongest-first (most failed episodes, then subject).
    """
    failed = [r for r in history if _failed(r)]
    if len(failed) < _MINIMUM_RECURRENCE:
        return ()

    # Cluster failed episodes into components connected by a shared content
    # word: two failed episodes belong to the same gap when they both touch the
    # same subject word, directly or through a chain of shared words.
    words = [_content_words(record.trigger) for record in failed]
    parent = list(range(len(failed)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(failed)):
        for right in range(left + 1, len(failed)):
            if words[left] & words[right]:
                root_left, root_right = find(left), find(right)
                if root_left != root_right:
                    parent[root_left] = root_right

    components: dict[int, list[int]] = {}
    for index in range(len(failed)):
        components.setdefault(find(index), []).append(index)

    gaps: list[CapabilityGap] = []
    for indices in components.values():
        if len(indices) < _MINIMUM_RECURRENCE:
            continue

        occurrences: dict[str, int] = {}
        for index in indices:
            for word in words[index]:
                occurrences[word] = occurrences.get(word, 0) + 1

        subject, count = min(
            occurrences.items(), key=lambda pair: (-pair[1], pair[0])
        )
        if count < _MINIMUM_RECURRENCE:
            continue

        gaps.append(
            CapabilityGap(
                subject=subject,
                episodes=tuple(failed[index] for index in indices),
            )
        )

    gaps.sort(key=lambda gap: (-len(gap.episodes), gap.subject))
    return tuple(gaps)