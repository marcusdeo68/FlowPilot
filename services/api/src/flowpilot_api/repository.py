"""Persistence operations; SQL values are always bound parameters."""

import sqlite3
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from flowpilot_api.database import transaction
from flowpilot_api.domain import CommitmentStatus, can_transition
from flowpilot_api.schemas import CommitmentCreate


class CommitmentNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


class VersionConflict(Exception):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def row_to_commitment(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "title": row["title"],
        "details": row["details"],
        "owner_name": row["owner_name"],
        "due_date": row["due_date"],
        "evidence_excerpt": row["evidence_excerpt"],
        "status": row["status"],
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_commitment(payload: CommitmentCreate) -> dict[str, object]:
    commitment_id = str(uuid4())
    timestamp = utc_now()
    with transaction(write=True) as connection:
        connection.execute(
            """INSERT INTO commitments
               (id, title, details, owner_name, due_date, evidence_excerpt, status, version,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                commitment_id,
                payload.title,
                payload.details,
                payload.owner_name,
                payload.due_date.isoformat() if payload.due_date else None,
                payload.evidence_excerpt,
                CommitmentStatus.DETECTED.value,
                1,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """INSERT INTO commitment_events
               (commitment_id, event_type, actor, from_status, to_status, reason, created_at)
               VALUES (?, 'created', 'local-user', NULL, ?, NULL, ?)""",
            (commitment_id, CommitmentStatus.DETECTED.value, timestamp),
        )
        row = connection.execute(
            "SELECT * FROM commitments WHERE id = ?", (commitment_id,)
        ).fetchone()
    return row_to_commitment(row)


def list_commitments(*, status: CommitmentStatus | None, limit: int) -> list[dict[str, object]]:
    with transaction() as connection:
        if status is None:
            rows = connection.execute(
                "SELECT * FROM commitments ORDER BY updated_at DESC, id LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM commitments WHERE status = ? ORDER BY updated_at DESC, id LIMIT ?",
                (status.value, limit),
            ).fetchall()
    return [row_to_commitment(row) for row in rows]


def get_commitment(commitment_id: UUID) -> dict[str, object]:
    with transaction() as connection:
        row = connection.execute(
            "SELECT * FROM commitments WHERE id = ?", (str(commitment_id),)
        ).fetchone()
    if row is None:
        raise CommitmentNotFound
    return row_to_commitment(row)


def focus_snapshot(day: date) -> dict[str, object]:
    """One read snapshot: global due count and at most 50 recent list rows."""
    with transaction() as connection:
        count = connection.execute(
            """SELECT COUNT(*) FROM commitments WHERE due_date=?
               AND status NOT IN ('completed','canceled')""",
            (day.isoformat(),),
        ).fetchone()[0]
        rows = connection.execute(
            """SELECT id, title, owner_name, due_date, status, version FROM commitments
               ORDER BY updated_at DESC, id LIMIT 50"""
        ).fetchall()
    return {"items": [dict(row) for row in rows], "due_count": count}


def transition_commitment(
    commitment_id: UUID,
    *,
    target: CommitmentStatus,
    expected_version: int,
    reason: str | None,
) -> dict[str, object]:
    timestamp = utc_now()
    with transaction(write=True) as connection:
        row = connection.execute(
            "SELECT * FROM commitments WHERE id = ?", (str(commitment_id),)
        ).fetchone()
        if row is None:
            raise CommitmentNotFound
        if row["version"] != expected_version:
            raise VersionConflict
        current = CommitmentStatus(row["status"])
        if not can_transition(current, target):
            raise InvalidTransition
        connection.execute(
            """UPDATE commitments
               SET status = ?, version = version + 1, updated_at = ?
               WHERE id = ? AND version = ?""",
            (target.value, timestamp, str(commitment_id), expected_version),
        )
        connection.execute(
            """INSERT INTO commitment_events
               (commitment_id, event_type, actor, from_status, to_status, reason, created_at)
               VALUES (?, 'status_changed', 'local-user', ?, ?, ?, ?)""",
            (str(commitment_id), current.value, target.value, reason, timestamp),
        )
        updated = connection.execute(
            "SELECT * FROM commitments WHERE id = ?", (str(commitment_id),)
        ).fetchone()
    return row_to_commitment(updated)


def list_events(commitment_id: UUID) -> list[dict[str, object]]:
    with transaction() as connection:
        exists = connection.execute(
            "SELECT 1 FROM commitments WHERE id = ?", (str(commitment_id),)
        ).fetchone()
        if exists is None:
            raise CommitmentNotFound
        rows = connection.execute(
            """SELECT * FROM commitment_events WHERE commitment_id = ?
               ORDER BY created_at, id""",
            (str(commitment_id),),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "commitment_id": row["commitment_id"],
            "event_type": row["event_type"],
            "actor": row["actor"],
            "from_status": row["from_status"],
            "to_status": row["to_status"],
            "reason": row["reason"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
