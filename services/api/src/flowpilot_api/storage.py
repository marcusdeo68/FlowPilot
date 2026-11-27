"""Explicit PostgreSQL engine configuration; never silently fall back to SQLite."""

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, QueuePool

SCHEMA_REVISION = "0011_task_priorities"


def create_database_engine(url: str | None = None) -> Engine:
    configured = url or os.environ.get("FLOWPILOT_DATABASE_URL")
    if not configured:
        raise ValueError("Set FLOWPILOT_DATABASE_URL for PostgreSQL operations")
    parsed = make_url(configured)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("PostgreSQL with the psycopg driver is required")
    pool = os.environ.get("FLOWPILOT_DATABASE_POOL", "pooled")
    if pool not in ("pooled", "disabled"):
        raise ValueError("Set FLOWPILOT_DATABASE_POOL to pooled or disabled")
    # Hide SQL parameters in exception rendering; source content must not enter logs.
    return create_engine(
        parsed,
        poolclass=QueuePool if pool == "pooled" else NullPool,
        pool_pre_ping=pool == "pooled",
        hide_parameters=True,
    )
