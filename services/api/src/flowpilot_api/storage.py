"""Explicit PostgreSQL engine configuration; never silently fall back to SQLite."""

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

SCHEMA_REVISION = "0005_browser_sessions"


def create_database_engine(url: str | None = None) -> Engine:
    configured = url or os.environ.get("FLOWPILOT_DATABASE_URL")
    if not configured:
        raise ValueError("Set FLOWPILOT_DATABASE_URL for PostgreSQL operations")
    parsed = make_url(configured)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("PostgreSQL with the psycopg driver is required")
    # Hide SQL parameters in exception rendering; source content must not enter logs.
    return create_engine(parsed, pool_pre_ping=True, hide_parameters=True)
