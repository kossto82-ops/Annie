"""EnergyRecovery: how cognitive energy refills over time (Vision §15 leftover).

Fatigue is not a hard cap: a tired mind rests when it is quiet. This frozen
profile describes *how fast* the recoverable energy budget comes back with
wall-clock time — linearly from the current level back to full over
``full_recovery_minutes`` since the last charge. It is configurable (injectable
at construction and runtime-tunable), never a buried constant, and it does not
forgive past spend: the cumulative ``spent`` ledger (Increment 33) never
rewinds, only the recoverable ``available`` budget climbs back.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class EnergyRecovery:
    """The wall-clock recovery profile for the energy budget (Vision §15).

    A drained budget refills to full over ``full_recovery_minutes`` minutes of
    quiet time, applied lazily whenever the ledger is read. ``None`` (no
    profile) keeps the historical behaviour: energy comes back only on an
    explicit ``rest()``.
    """

    full_recovery_minutes: int = 60