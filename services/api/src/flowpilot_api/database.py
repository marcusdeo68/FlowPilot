"""Small SQLite persistence adapter for the local, synthetic-data milestone."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS commitments (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
    details TEXT CHECK(details IS NULL OR length(details) <= 4000),
    owner_name TEXT CHECK(owner_name IS NULL OR length(owner_name) <= 160),
    due_date TEXT,
    evidence_excerpt TEXT CHECK(evidence_excerpt IS NULL OR length(evidence_excerpt) <= 2000),
    status TEXT NOT NULL CHECK(status IN (
        'detected', 'confirmed', 'active', 'blocked', 'completed', 'canceled', 'disputed'
    )),
    version INTEGER NOT NULL CHECK(version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commitment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commitment_id TEXT NOT NULL REFERENCES commitments(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK(event_type IN ('created', 'status_changed')),
    actor TEXT NOT NULL,
    from_status TEXT CHECK(from_status IS NULL OR from_status IN (
        'detected', 'confirmed', 'active', 'blocked', 'completed', 'canceled', 'disputed'
    )),
    to_status TEXT CHECK(to_status IS NULL OR to_status IN (
        'detected', 'confirmed', 'active', 'blocked', 'completed', 'canceled', 'disputed'
    )),
    reason TEXT CHECK(reason IS NULL OR length(reason) <= 1000),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_commitments_status_updated
    ON commitments(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_commitment_events_commitment_created
    ON commitment_events(commitment_id, created_at, id);

CREATE TRIGGER IF NOT EXISTS commitment_events_no_update
BEFORE UPDATE ON commitment_events
BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;

CREATE TRIGGER IF NOT EXISTS commitment_events_no_delete
BEFORE DELETE ON commitment_events
BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;
"""


def database_path() -> Path:
    configured = os.environ.get("FLOWPILOT_DB_PATH", "data/flowpilot.sqlite3")
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database() -> None:
    with closing(connect()) as connection:
        connection.executescript(SCHEMA)


@contextmanager
def transaction(*, write: bool = False) -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
