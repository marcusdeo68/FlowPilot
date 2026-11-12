import pytest
from fastapi.testclient import TestClient
from flowpilot_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWPILOT_DB_PATH", str(tmp_path / "test.sqlite3"))
    with TestClient(app, base_url="http://127.0.0.1") as session:
        yield session
