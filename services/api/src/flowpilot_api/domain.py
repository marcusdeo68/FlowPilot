"""Deterministic commitment lifecycle rules."""

from enum import StrEnum


class CommitmentStatus(StrEnum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELED = "canceled"
    DISPUTED = "disputed"


ALLOWED_TRANSITIONS: dict[CommitmentStatus, frozenset[CommitmentStatus]] = {
    CommitmentStatus.DETECTED: frozenset(
        {CommitmentStatus.CONFIRMED, CommitmentStatus.CANCELED, CommitmentStatus.DISPUTED}
    ),
    CommitmentStatus.CONFIRMED: frozenset(
        {CommitmentStatus.ACTIVE, CommitmentStatus.CANCELED, CommitmentStatus.DISPUTED}
    ),
    CommitmentStatus.ACTIVE: frozenset(
        {
            CommitmentStatus.BLOCKED,
            CommitmentStatus.COMPLETED,
            CommitmentStatus.CANCELED,
            CommitmentStatus.DISPUTED,
        }
    ),
    CommitmentStatus.BLOCKED: frozenset(
        {CommitmentStatus.ACTIVE, CommitmentStatus.CANCELED, CommitmentStatus.DISPUTED}
    ),
    CommitmentStatus.DISPUTED: frozenset(
        {CommitmentStatus.CONFIRMED, CommitmentStatus.ACTIVE, CommitmentStatus.CANCELED}
    ),
    CommitmentStatus.COMPLETED: frozenset(),
    CommitmentStatus.CANCELED: frozenset(),
}


def can_transition(current: CommitmentStatus, target: CommitmentStatus) -> bool:
    """Return whether the requested lifecycle transition is valid."""
    return target in ALLOWED_TRANSITIONS[current]
