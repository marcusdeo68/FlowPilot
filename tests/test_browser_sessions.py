"""Session contracts plus real PostgreSQL lifecycle and signed HTTP checks."""

import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from alembic import command
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from flowpilot_api.browser_sessions import (
    COOKIE_NAME,
    BrowserConfig,
    BrowserSessions,
    InvalidSession,
    SessionUnavailable,
    credential_digest,
    csrf_token,
)
from flowpilot_api.session_routes import session_cookie
from flowpilot_api.workspace_api import create_workspace_app
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

ORIGIN = "http://127.0.0.1"


@pytest.mark.parametrize(
    "headers",
    [
        [(b"cookie", b"flowpilot_session =first; flowpilot_session=second")],
        [(b"cookie", b"flowpilot_session=first; flowpilot_session\t=second")],
        [(b"cookie", b"flowpilot_session =first"), (b"cookie", b"flowpilot_session=second")],
        [(b"cookie", b"flowpilot_session =first"), (b"authorization", b"Bearer ignored")],
        [
            (b"cookie", b"unrelated=x"),
            (b"cookie", b"flowpilot_session =first"),
            (b"authorization", b"Basic ignored"),
        ],
    ],
)
def test_cookie_whitespace_cannot_hide_duplicate_or_mixed_credentials(headers):
    request = Request({"type": "http", "headers": headers})
    with pytest.raises(HTTPException) as error:
        session_cookie(request)
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "https://example.com",
        "http://localhost/",
        "http://localhost?x=1",
        "http://localhost#x",
        "http://user@localhost",
        "ftp://localhost",
        "http://localhost:0",
        "http://localhost:65536",
        "http://localhost:80",
        "https://localhost:443",
        "http://127.0.0.2",
        "http://localhost\n",
        "http://LOCALHOST",
        " http://localhost",
    ],
)
def test_origin_configuration_rejects_unsafe_or_noncanonical_values(origin):
    with pytest.raises(ValueError):
        BrowserConfig(origin)


def test_credentials_and_verified_expiry(token_tools):
    _, verifier, sign = token_tools
    expiry = int(time.time()) + 250
    assert verifier.verify(sign(overrides={"exp": expiry})).expires_at == expiry
    raw = secrets.token_urlsafe(32)
    assert len(credential_digest(raw)) == 64
    assert credential_digest(raw) != raw
    assert csrf_token(raw) == csrf_token(raw)
    assert csrf_token(raw) != csrf_token(secrets.token_urlsafe(32))
    for invalid in ("", "x" * 42, "x" * 44, "é" * 43, "!" * 43):
        with pytest.raises(InvalidSession):
            credential_digest(invalid)
    assert BrowserConfig("https://localhost:8443").secure
    assert not BrowserConfig(ORIGIN).secure


def test_disabled_cookie_auth_and_configuration(token_tools, monkeypatch):
    _, verifier, sign = token_tools
    monkeypatch.delenv("FLOWPILOT_BROWSER_ORIGIN", raising=False)
    engine = create_engine("sqlite://")  # No DB access occurs on rejected requests.
    try:
        with TestClient(
            create_workspace_app(engine=engine, verifier=verifier), base_url=ORIGIN
        ) as client:
            assert client.post("/api/v2/session").status_code == 404
            assert (
                client.get("/api/v2/me", headers={"Cookie": f"{COOKIE_NAME}=x"}).status_code == 401
            )
        monkeypatch.setenv("FLOWPILOT_BROWSER_ORIGIN", "https://example.com")
        with pytest.raises(ValueError):
            create_workspace_app(engine=engine, verifier=verifier)
        with TestClient(
            create_workspace_app(engine=engine, verifier=verifier, browser_origin=ORIGIN),
            base_url=ORIGIN,
        ) as client:
            assert (
                client.post(
                    "/api/v2/session",
                    headers={"Authorization": f"Bearer {sign()}", "Origin": ORIGIN},
                ).status_code
                == 503
            )
    finally:
        engine.dispose()


@pytest.fixture
def sessions(pg, token_tools):
    config, _, _ = token_tools
    return BrowserSessions(pg[0], config, BrowserConfig(ORIGIN))


@pytest.mark.postgres
def test_persisted_hash_binding_expiry_and_independent_sessions(sessions, token_tools):
    _, verifier, sign = token_tools
    user = verifier.verify(sign())
    raw = sessions.issue(user)
    second = sessions.issue(user)
    assert raw != second
    with sessions.engine.connect() as connection:
        row = (
            connection.execute(
                text("SELECT * FROM browser_sessions WHERE credential_hash=:h"),
                {"h": credential_digest(raw)},
            )
            .mappings()
            .one()
        )
        assert raw not in str(row)
        assert row["expires_at"] == user.expires_at
        assert set(row["scopes"]) == user.scopes
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
    assert sessions.resolve(raw) == user
    for config, origin in (
        (replace(sessions.identity, audience="other"), ORIGIN),
        (sessions.identity, "http://127.0.0.1:8001"),
        (
            replace(
                sessions.identity,
                issuer="https://other.example",
                jwks_url="https://other.example/jwks",
            ),
            ORIGIN,
        ),
    ):
        with pytest.raises(InvalidSession):
            BrowserSessions(sessions.engine, config, BrowserConfig(origin)).resolve(raw)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(sessions.revoke, [raw, raw]))
    with pytest.raises(InvalidSession):
        sessions.resolve(raw)
    assert sessions.resolve(second) == user
    with sessions.engine.begin() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM browser_session_audit WHERE operation='revoked'")
            ).scalar_one()
            == 1
        )
        connection.execute(text("UPDATE browser_sessions SET expires_at=0"))
    with pytest.raises(InvalidSession):
        sessions.resolve(second)
    with pytest.raises(InvalidSession):
        sessions.issue(replace(user, expires_at=int(time.time()) - 1))


@pytest.mark.postgres
def test_session_audit_atomicity_and_immutability(sessions, token_tools):
    _, verifier, sign = token_tools
    user = verifier.verify(sign())
    raw = sessions.issue(user)
    # Reuse the immutable-event trigger to force every audit insert to fail.
    with sessions.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TRIGGER fail_session_audit BEFORE INSERT ON browser_session_audit FOR EACH ROW EXECUTE FUNCTION reject_audit_edit()"
            )
        )
    with pytest.raises(SessionUnavailable):
        sessions.issue(user)
    with pytest.raises(SessionUnavailable):
        sessions.revoke(raw)
    assert sessions.resolve(raw) == user
    with sessions.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM browser_sessions")).scalar_one() == 1
    for sql in (
        "UPDATE browser_session_audit SET operation='revoked'",
        "DELETE FROM browser_session_audit",
        "TRUNCATE browser_session_audit",
    ):
        with pytest.raises(DBAPIError), sessions.engine.begin() as connection:
            connection.execute(text(sql))


@pytest.mark.postgres
def test_session_migration_roundtrip(pg):
    engine, config = pg
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0004_source_inbox")
        assert (
            connection.execute(text("SELECT to_regclass('browser_sessions')")).scalar_one() is None
        )
        command.upgrade(config, "head")
        assert connection.execute(text("SELECT count(*) FROM browser_sessions")).scalar_one() == 0


@pytest.fixture
def session_client(setup, token_tools):
    service, workspace, other, users = setup
    config, verifier, sign = token_tools
    with service.engine.begin() as connection:
        connection.execute(text("UPDATE users SET issuer=:issuer"), {"issuer": config.issuer})
    app = create_workspace_app(engine=service.engine, verifier=verifier, browser_origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, workspace, other, users, sign, service.engine


def exchange(client, sign, subject="owner", **kwargs):
    return client.post(
        "/api/v2/session",
        headers={"Authorization": f"Bearer {sign(subject, **kwargs)}", "Origin": ORIGIN},
    )


@pytest.mark.postgres
def test_session_http_lifecycle_and_csrf(session_client):
    client, workspace, _, _, sign, _ = session_client
    issued = exchange(client, sign)
    assert issued.status_code == 201
    cookie = issued.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v2" in cookie
    assert "Domain=" not in cookie and "Secure" not in cookie
    raw = client.cookies.get(COOKIE_NAME)
    assert raw not in issued.text
    info = client.get("/api/v2/session")
    assert info.json() == issued.json()
    assert info.headers["cache-control"] == "no-store"
    assert client.get(f"/api/v2/workspaces/{workspace}/work").status_code == 200
    for headers in (
        {},
        {"Origin": ORIGIN},
        {"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
        {"X-CSRF-Token": info.json()["csrf_token"]},
    ):
        assert (
            client.post("/api/v2/workspaces", json={"name": "Denied"}, headers=headers).status_code
            == 403
        )
    headers = {"Origin": ORIGIN, "X-CSRF-Token": info.json()["csrf_token"]}
    created = client.post(
        "/api/v2/workspaces", json={"name": "Synthetic session team"}, headers=headers
    )
    assert created.status_code == 201
    assert len(client.get("/api/v2/workspaces").json()) == 2
    assert client.delete("/api/v2/session", headers={"Origin": ORIGIN}).status_code == 403
    assert client.delete("/api/v2/session", headers=headers).status_code == 204
    assert client.cookies.get(COOKIE_NAME) is None
    assert client.get("/api/v2/me", headers={"Cookie": f"{COOKIE_NAME}={raw}"}).status_code == 401
    assert (
        client.delete(
            "/api/v2/session", headers={"Origin": ORIGIN, "Cookie": f"{COOKIE_NAME}={raw}"}
        ).status_code
        == 204
    )
    assert client.get("/api/v1/commitments").status_code == 404


@pytest.mark.postgres
def test_exchange_auth_and_scope_failures(session_client):
    client, _, _, _, sign, _ = session_client
    for token in (
        "forged",
        sign(overrides={"exp": int(time.time()) - 1}),
        sign(overrides={"aud": "wrong"}),
    ):
        assert (
            client.post(
                "/api/v2/session", headers={"Origin": ORIGIN, "Authorization": f"Bearer {token}"}
            ).status_code
            == 401
        )
    assert client.post("/api/v2/session", headers={"Origin": ORIGIN}).status_code == 401
    for origin in (
        None,
        "null",
        "http://localhost",
        "http://127.0.0.1:8001",
        "https://evil.example",
    ):
        headers = {"Authorization": f"Bearer {sign()}"}
        if origin is not None:
            headers["Origin"] = origin
        assert client.post("/api/v2/session", headers=headers).status_code == 403
    assert exchange(client, sign, overrides={"scope": "flowpilot:write"}).status_code == 403
    issued = exchange(client, sign, overrides={"scope": "flowpilot:read"})
    assert issued.status_code == 201
    assert (
        client.post(
            "/api/v2/workspaces",
            json={"name": "Denied"},
            headers={"Origin": ORIGIN, "X-CSRF-Token": issued.json()["csrf_token"]},
        ).status_code
        == 403
    )
    assert exchange(client, sign).status_code == 401
    assert client.get("/api/v2/me", headers={"Authorization": "Basic x"}).status_code == 401


@pytest.mark.postgres
def test_cookie_origin_ambiguity_and_stale_recovery(session_client):
    client, _, _, _, sign, engine = session_client
    assert exchange(client, sign).status_code == 201
    for headers in (
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Host": "127.0.0.1:8001"},
    ):
        assert client.get("/api/v2/me", headers=headers).status_code == 403
    raw = client.cookies.get(COOKIE_NAME)
    assert (
        client.get(
            "/api/v2/me", headers={"Cookie": f"{COOKIE_NAME}={raw}; {COOKIE_NAME}={raw}"}
        ).status_code
        == 401
    )
    for headers in (
        {"Cookie": f"{COOKIE_NAME} ={raw}; {COOKIE_NAME}={raw}"},
        {"Cookie": f"{COOKIE_NAME} ={raw}", "Authorization": "Basic ignored"},
    ):
        assert client.get("/api/v2/me", headers=headers).status_code == 401
    with engine.begin() as connection:
        connection.execute(text("UPDATE browser_sessions SET expires_at=0"))
    assert client.get("/api/v2/session").status_code == 401
    assert client.delete("/api/v2/session", headers={"Origin": ORIGIN}).status_code == 204
    assert exchange(client, sign).status_code == 201


@pytest.mark.postgres
def test_cookie_membership_and_private_work_checks_remain_live(session_client):
    client, workspace, other, users, sign, engine = session_client
    # Create private work as owner with the existing bearer API, before cookie exchange.
    created = client.post(
        f"/api/v2/workspaces/{workspace}/work",
        json={"item": {"kind": "task", "title": "Private synthetic task"}},
        headers={"Authorization": f"Bearer {sign()}"},
    )
    assert created.status_code == 201
    assert exchange(client, sign, "member").status_code == 201
    assert (
        client.get(f"/api/v2/workspaces/{workspace}/work/{created.json()['id']}").status_code == 404
    )
    assert client.get(f"/api/v2/workspaces/{other}/work").status_code == 403
    assert client.get(f"/api/v2/workspaces/{workspace}/work").status_code == 200
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE memberships SET active=false WHERE user_id=:user"),
            {"user": users["member"]},
        )
    assert client.get(f"/api/v2/workspaces/{workspace}/work").status_code == 403


@pytest.mark.postgres
def test_https_cookie_and_new_identity_onboarding(pg, token_tools):
    _, verifier, sign = token_tools
    origin = "https://localhost"
    app = create_workspace_app(engine=pg[0], verifier=verifier, browser_origin=origin)
    with TestClient(app, base_url=origin) as client:
        issued = client.post(
            "/api/v2/session",
            headers={"Origin": origin, "Authorization": f"Bearer {sign('new-user')}"},
        )
        assert issued.status_code == 201
        assert "Secure" in issued.headers["set-cookie"]
        assert client.get("/api/v2/me").status_code == 404
        assert (
            client.post(
                "/api/v2/workspaces",
                json={"name": "First workspace"},
                headers={"Origin": origin, "X-CSRF-Token": issued.json()["csrf_token"]},
            ).status_code
            == 201
        )
        assert client.get("/api/v2/me").status_code == 200
