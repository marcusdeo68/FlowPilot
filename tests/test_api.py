import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from flowpilot_api.database import transaction


def create(client, title="Synthetic follow-up"):
    response = client.post("/api/v1/commitments", json={"title": title})
    assert response.status_code == 201
    return response.json()


def test_assets_health_and_persistence(client):
    for path in ("/", "/app.js", "/styles.css", "/healthz", "/readyz", "/openapi.json"):
        assert client.get(path).status_code == 200
    item = create(client, "Robert'); DROP TABLE commitments;--")
    assert client.get(f"/api/v1/commitments/{item['id']}").json() == item
    assert client.get("/api/v1/commitments").json()["count"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"title": " "},
        {"title": "x" * 201},
        {"title": "x", "status": "completed"},
        {"title": "x", "due_date": "nonsense"},
        {"title": "x", "owner_name": " "},
    ],
)
def test_invalid_input_does_not_write(client, payload):
    assert client.post("/api/v1/commitments", json=payload).status_code == 422
    assert client.get("/api/v1/commitments").json()["count"] == 0


def test_lifecycle_stale_and_illegal_transitions(client):
    item = create(client)
    path = f"/api/v1/commitments/{item['id']}/transitions"
    assert (
        client.post(path, json={"target_status": "completed", "expected_version": 1}).status_code
        == 409
    )
    for version, target in enumerate(("confirmed", "active", "blocked", "active", "completed"), 1):
        response = client.post(path, json={"target_status": target, "expected_version": version})
        assert response.status_code == 200
        assert response.json()["version"] == version + 1
    assert (
        client.post(path, json={"target_status": "canceled", "expected_version": 1}).status_code
        == 409
    )
    events = client.get(f"/api/v1/commitments/{item['id']}/events").json()
    assert len(events) == 6
    assert events[-1]["to_status"] == "completed"


def test_concurrent_writers_only_one_succeeds(client):
    item = create(client)

    def update(_):
        return client.post(
            f"/api/v1/commitments/{item['id']}/transitions",
            json={
                "target_status": "confirmed",
                "expected_version": 1,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, range(2))) == [200, 409]
    assert len(client.get(f"/api/v1/commitments/{item['id']}/events").json()) == 2


def test_audit_failure_rolls_back_state(client):
    item = create(client)
    with transaction(write=True) as connection:
        connection.execute("""CREATE TRIGGER fail_audit BEFORE INSERT ON commitment_events
                              BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="test failure"):
        client.post(
            f"/api/v1/commitments/{item['id']}/transitions",
            json={
                "target_status": "confirmed",
                "expected_version": 1,
            },
        )
    saved = client.get(f"/api/v1/commitments/{item['id']}").json()
    assert (saved["status"], saved["version"]) == ("detected", 1)
    assert len(client.get(f"/api/v1/commitments/{item['id']}/events").json()) == 1


def test_missing_and_invalid_ids(client):
    assert client.get("/api/v1/commitments/not-an-id").status_code == 422
    assert client.get("/api/v1/commitments/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/v1/commitments?limit=101").status_code == 422


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://hostile.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_cross_site_browser_writes_rejected(client, headers):
    assert (
        client.post("/api/v1/commitments", json={"title": "x"}, headers=headers).status_code == 403
    )
    assert client.get("/api/v1/commitments").json()["count"] == 0


def test_host_and_same_origin_boundary(client):
    assert client.get("/", headers={"Host": "hostile.example"}).status_code == 400
    assert (
        client.post(
            "/api/v1/commitments",
            json={"title": "Synthetic"},
            headers={"Origin": "http://127.0.0.1"},
        ).status_code
        == 201
    )
    response = client.get("/")
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize(
    "statement", ["DELETE FROM commitment_events", "UPDATE commitment_events SET actor = 'changed'"]
)
def test_audit_is_append_only(client, statement):
    item = create(client)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with transaction(write=True) as connection:
            connection.execute(statement)
    assert len(client.get(f"/api/v1/commitments/{item['id']}/events").json()) == 1
