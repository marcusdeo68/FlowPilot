import pytest
from flowpilot_api.storage import create_database_engine


def test_postgres_configuration_is_explicit(monkeypatch):
    monkeypatch.delenv("FLOWPILOT_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="Set FLOWPILOT_DATABASE_URL"):
        create_database_engine()
    with pytest.raises(ValueError, match="PostgreSQL"):
        create_database_engine("sqlite:///local.db")
