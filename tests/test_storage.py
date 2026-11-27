from uuid import uuid4

import pytest
from flowpilot_api.storage import create_database_engine
from psycopg import Connection
from sqlalchemy import text
from sqlalchemy.pool import NullPool, QueuePool


def test_postgres_configuration_is_explicit(monkeypatch):
    monkeypatch.delenv("FLOWPILOT_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="Set FLOWPILOT_DATABASE_URL"):
        create_database_engine()
    with pytest.raises(ValueError, match="PostgreSQL"):
        create_database_engine("sqlite:///local.db")


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg"])
def test_postgresql_url_uses_psycopg_and_preserves_connection_settings(monkeypatch, scheme):
    monkeypatch.setenv(
        "FLOWPILOT_DATABASE_URL",
        f"{scheme}://sample:p%40ss%3Aword@postgres.railway.internal:5432/flowpilot?sslmode=require",
    )
    engine = create_database_engine()
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.username == "sample"
        assert engine.url.password == "p@ss:word"
        assert engine.url.host == "postgres.railway.internal"
        assert engine.url.port == 5432
        assert engine.url.database == "flowpilot"
        assert engine.url.query == {"sslmode": "require"}
        assert engine.hide_parameters
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("mode", "pool_type"),
    [(None, QueuePool), ("pooled", QueuePool), ("disabled", NullPool)],
)
def test_postgres_pool_mode(monkeypatch, mode, pool_type):
    monkeypatch.delenv("FLOWPILOT_DATABASE_POOL", raising=False)
    if mode is not None:
        monkeypatch.setenv("FLOWPILOT_DATABASE_POOL", mode)
    engine = create_database_engine("postgresql://example/flowpilot")
    try:
        assert isinstance(engine.pool, pool_type)
        assert engine.hide_parameters
    finally:
        engine.dispose()


@pytest.mark.parametrize("mode", ["", "off"])
def test_postgres_rejects_invalid_pool_mode(monkeypatch, mode):
    monkeypatch.setenv("FLOWPILOT_DATABASE_POOL", mode)
    with pytest.raises(ValueError, match="Set FLOWPILOT_DATABASE_POOL to pooled or disabled"):
        create_database_engine("postgresql://example/flowpilot")


@pytest.mark.postgres
def test_unpooled_postgres_closes_connections_after_commit_and_rollback(pg, monkeypatch):
    fixture_engine, _ = pg
    with fixture_engine.connect() as probe:
        schema = probe.execute(text("SELECT current_schema()")).scalar_one()
    url = fixture_engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("FLOWPILOT_DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("FLOWPILOT_DATABASE_POOL", "disabled")
    engine = create_database_engine()
    workspace_id = uuid4()
    try:
        with engine.begin() as first:
            driver = first.connection.driver_connection
            assert isinstance(driver, Connection)
            first.execute(
                text("INSERT INTO workspaces (id, name) VALUES (:id, 'Synthetic')"),
                {"id": workspace_id},
            )
            assert not driver.closed
        assert driver.closed

        with engine.connect() as second:
            rollback_driver = second.connection.driver_connection
            assert isinstance(rollback_driver, Connection)
            assert rollback_driver is not driver
            with pytest.raises(RuntimeError, match="synthetic rollback"), second.begin():
                second.execute(
                    text("UPDATE workspaces SET name = 'Changed' WHERE id = :id"),
                    {"id": workspace_id},
                )
                raise RuntimeError("synthetic rollback")
        assert rollback_driver.closed

        with engine.connect() as last:
            name = last.execute(
                text("SELECT name FROM workspaces WHERE id = :id"), {"id": workspace_id}
            ).scalar_one()
            assert name == "Synthetic"
    finally:
        engine.dispose()
