"""Login configuration, bounded transport, and signed PostgreSQL HTTP flows."""

import base64
import hashlib
import json
import secrets
import socket
import threading
import time
from email.message import Message
from http.client import HTTPConnection, RemoteDisconnected
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from flowpilot_api import login
from flowpilot_api.browser_sessions import COOKIE_NAME
from flowpilot_api.identity import IdentityUnavailable
from flowpilot_api.login import LOGIN_PATH, PENDING_COOKIE, LoginConfig, TokenExchange
from flowpilot_api.workspace_api import create_workspace_app
from sqlalchemy import create_engine, text

ORIGIN = "http://127.0.0.1"
CONFIG = LoginConfig(
    "synthetic-client", "https://identity.example/authorize", "https://identity.example/token"
)


def test_login_configuration_opt_in_and_binding(token_tools, monkeypatch):
    _, verifier, _ = token_tools
    names = ("CLIENT_ID", "AUTHORIZATION_URL", "TOKEN_URL")
    for name in names:
        monkeypatch.delenv("FLOWPILOT_LOGIN_" + name, raising=False)
    assert LoginConfig.from_environment() is None
    engine = create_engine("sqlite://")
    try:
        with TestClient(
            create_workspace_app(engine=engine, verifier=verifier), base_url=ORIGIN
        ) as client:
            assert client.get(LOGIN_PATH).status_code == 404
        monkeypatch.setenv("FLOWPILOT_LOGIN_CLIENT_ID", "synthetic-client")
        with pytest.raises(ValueError):
            LoginConfig.from_environment()
        monkeypatch.setenv("FLOWPILOT_LOGIN_AUTHORIZATION_URL", CONFIG.authorization_url)
        monkeypatch.setenv("FLOWPILOT_LOGIN_TOKEN_URL", CONFIG.token_url)
        assert LoginConfig.from_environment() == CONFIG
        with pytest.raises(ValueError):
            create_workspace_app(engine=engine, verifier=verifier)
        with pytest.raises(ValueError):
            create_workspace_app(
                engine=engine,
                verifier=verifier,
                browser_origin=ORIGIN,
                login_config=LoginConfig(
                    "synthetic-client", "https://other.example/authorize", CONFIG.token_url
                ),
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://identity.example/token",
        "https://user@identity.example/token",
        "https://identity.example/token?secret=x",
        "https://identity.example/token#fragment",
        "https://identity.example/token\n",
        "https://identity.example\\evil/token",
        "https://identity.example:bad/token",
        "https://identity.example:65536/token",
        "https://identity.example:0/token",
    ],
)
def test_login_rejects_unsafe_endpoints(endpoint):
    with pytest.raises(ValueError):
        LoginConfig("synthetic-client", endpoint, CONFIG.token_url)
    with pytest.raises(ValueError):
        LoginConfig("synthetic-client", CONFIG.authorization_url, endpoint)


@pytest.mark.parametrize("client_id", ["", " ", "bad client", "bad\tclient", "x" * 301])
def test_login_rejects_invalid_client_ids(client_id):
    with pytest.raises(ValueError):
        LoginConfig(client_id, CONFIG.authorization_url, CONFIG.token_url)


class TokenResponse:
    def __init__(self, raw, *, status=200, content_type="application/json"):
        self.raw, self.status, self.read_sizes = raw, status, []
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read1(self, size):
        self.read_sizes.append(size)
        chunk, self.raw = self.raw[:size], self.raw[size:]
        return chunk


def stub_transport(monkeypatch, response=None, error=None):
    calls = []

    class FakeSocket:
        def settimeout(self, timeout):
            assert 0 < timeout <= 5

        def shutdown(self, mode):
            pass

        def fileno(self):
            return 1

    class Connection:
        def __init__(self, host, port, *, timeout):
            assert host == "identity.example" and port is None and timeout == 5
            self.sock = FakeSocket()

        def connect(self):
            calls.append("connect")
            if error:
                raise error

        def request(self, method, path, *, body, headers):
            calls.append((method, path, body, headers))

        def getresponse(self):
            return response

        def close(self):
            calls.append("close")

    monkeypatch.setattr(login, "HTTPSConnection", Connection)
    return calls


@pytest.mark.parametrize("same_tick", [False, True])
def test_code_transport_uses_bounded_post_no_proxy_redirect_or_retry(monkeypatch, same_tick):
    if same_tick:
        # Adding five at this tick crosses a floating-point precision boundary.
        monkeypatch.setattr(login, "time", SimpleNamespace(monotonic=lambda: 251.004))
    response = TokenResponse(b'{"access_token":"signed-token","token_type":"bearer"}')
    calls = stub_transport(monkeypatch, response)
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted-proxy.invalid:1")
    callback = ORIGIN + LOGIN_PATH + "/callback"
    assert TokenExchange(CONFIG, callback)("synthetic code&=", "verifier") == "signed-token"
    method, path, body, headers = calls[1]
    assert calls[0] == "connect" and calls[-1] == "close" and len(calls) == 3
    assert method == "POST" and path == "/token"
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert headers["Accept"] == "application/json"
    assert parse_qs(body.decode("ascii")) == {
        "grant_type": ["authorization_code"],
        "client_id": [CONFIG.client_id],
        "code": ["synthetic code&="],
        "code_verifier": ["verifier"],
        "redirect_uri": [callback],
    }
    assert response.read_sizes == [4096, 4096]


@pytest.mark.parametrize(
    "raw,status,content_type",
    [
        (b"{}", 302, "application/json"),
        (b"{}", 200, "text/html"),
        (b"x" * 32769, 200, "application/json"),
        (b"\xff", 200, "application/json"),
        (b"[1]", 200, "application/json"),
        (b"null", 200, "application/json"),
        (b'{"access_token":"a","access_token":"b","token_type":"Bearer"}', 200, "application/json"),
        (b'{"access_token":"a","token_type":"Basic"}', 200, "application/json"),
        (b'{"access_token":"a","token_type":"Bearer","error":"denied"}', 200, "application/json"),
        (b'{"access_token":null,"token_type":"Bearer"}', 200, "application/json"),
        (b'{"access_token":"","token_type":"Bearer"}', 200, "application/json"),
        (
            json.dumps({"access_token": "x" * 16385, "token_type": "Bearer"}).encode(),
            200,
            "application/json",
        ),
    ],
)
def test_code_transport_rejects_untrusted_responses(monkeypatch, raw, status, content_type):
    response = TokenResponse(raw, status=status, content_type=content_type)
    calls = stub_transport(monkeypatch, response)
    with pytest.raises(IdentityUnavailable):
        TokenExchange(CONFIG, ORIGIN + LOGIN_PATH + "/callback")("code", "verifier")
    assert calls[0] == "connect" and calls[-1] == "close" and len(calls) == 3


@pytest.mark.parametrize(
    "error",
    [OSError("synthetic failure"), TimeoutError(), RemoteDisconnected()],
)
def test_code_transport_failure_never_retries(monkeypatch, error):
    calls = stub_transport(monkeypatch, error=error)
    with pytest.raises(IdentityUnavailable):
        TokenExchange(CONFIG, ORIGIN + LOGIN_PATH + "/callback")("code", "verifier")
    assert calls == ["connect", "close"]


@pytest.mark.parametrize("mode", ["success", "slow-header", "slow-body"])
def test_direct_transport_real_socket_success_and_total_response_deadline(monkeypatch, mode):
    """Exercise EOF/closed socket and slow byte streams absent from in-memory doubles."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    stopped = threading.Event()
    errors = []
    body = b'{"access_token":"synthetic-network-token","token_type":"Bearer"}'

    def serve():
        try:
            with listener.accept()[0] as peer:
                peer.settimeout(2)
                request = b""
                while b"\r\n\r\n" not in request:
                    request += peer.recv(4096)
                head, received_body = request.split(b"\r\n\r\n", 1)
                length = next(
                    int(line.split(b":", 1)[1])
                    for line in head.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                while len(received_body) < length:
                    received_body += peer.recv(4096)
                headers = (
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                )
                if mode == "success":
                    peer.sendall(headers + body)
                else:
                    stream = headers + body if mode == "slow-header" else body
                    if mode == "slow-body":
                        peer.sendall(headers)
                    for byte in stream:
                        if stopped.wait(0.03):
                            break
                        try:
                            peer.sendall(bytes([byte]))
                        except OSError:
                            break
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    monkeypatch.setattr(
        login,
        "HTTPSConnection",
        lambda host, port, timeout: HTTPConnection(
            "127.0.0.1", listener.getsockname()[1], timeout=timeout
        ),
    )
    monkeypatch.setattr(login, "EXCHANGE_SECONDS", 0.25)
    started = time.monotonic()
    try:
        exchange = TokenExchange(CONFIG, ORIGIN + LOGIN_PATH + "/callback")
        if mode == "success":
            assert exchange("code", "verifier") == "synthetic-network-token"
        else:
            with pytest.raises(IdentityUnavailable):
                exchange("code", "verifier")
            assert 0.15 <= time.monotonic() - started < 1.5
    finally:
        stopped.set()
        listener.close()
        thread.join(3)
    assert not thread.is_alive() and not errors


@pytest.fixture
def login_client(pg, token_tools):
    _, verifier, sign = token_tools
    calls = []
    outcome = {"token": sign("login-user")}

    def exchange(code, verifier):
        calls.append((code, verifier))
        if "error" in outcome:
            raise outcome["error"]
        return outcome["token"]

    app = create_workspace_app(
        engine=pg[0],
        verifier=verifier,
        browser_origin=ORIGIN,
        login_config=CONFIG,
        login_exchange=exchange,
    )
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, calls, outcome, sign, pg[0]


def begin(client):
    response = client.post(LOGIN_PATH, headers={"Origin": ORIGIN}, follow_redirects=False)
    assert response.status_code == 303
    fields = parse_qs(urlsplit(response.headers["location"]).query)
    return fields["state"][0], client.cookies.get(PENDING_COOKIE), response, fields


def complete(client, state, **kwargs):
    data = {"state": state, "iss": "https://identity.example", "code": "synthetic-code"}
    data.update(kwargs)
    return client.post(
        LOGIN_PATH + "/complete",
        content=urlencode(data),
        headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"},
    )


@pytest.mark.postgres
def test_login_http_signed_session_lifecycle(login_client):
    client, calls, _, _, engine = login_client
    page = client.get(LOGIN_PATH)
    assert page.status_code == 200 and "<form" in page.text
    assert page.headers["cache-control"] == "no-store"
    state, verifier, response, fields = begin(client)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and f"Path={LOGIN_PATH}" in cookie
    assert "Domain=" not in cookie
    assert fields == {
        "response_type": ["code"],
        "client_id": [CONFIG.client_id],
        "redirect_uri": [ORIGIN + LOGIN_PATH + "/callback"],
        "scope": ["flowpilot:read flowpilot:write"],
        "state": [state],
        "code_challenge_method": ["S256"],
        "code_challenge": [
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        ],
    }
    callback = client.get(
        LOGIN_PATH + "/callback",
        params={
            "state": state,
            "iss": "https://identity.example",
            "code": '<synthetic&"code>',
            "redirect_uri": "https://extension.example/ignored",
        },
    )
    assert callback.status_code == 200 and "Continue sign-in" in callback.text
    assert "&lt;synthetic&amp;&quot;code&gt;" in callback.text
    assert "<script" not in callback.text and calls == []
    assert "extension.example" not in callback.text
    assert callback.headers["referrer-policy"] == "strict-origin"
    assert "form-action 'self'" in callback.headers["content-security-policy"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM browser_sessions")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
    issued = complete(client, state)
    assert issued.status_code == 200 and "Signed in" in issued.text
    assert calls == [("synthetic-code", verifier)]
    assert client.cookies.get(PENDING_COOKIE) is None
    assert any("SameSite=strict" in value for value in issued.headers.get_list("set-cookie"))
    session = client.get("/api/v2/session")
    assert session.status_code == 200
    csrf = session.json()["csrf_token"]
    assert (
        client.post(
            "/api/v2/workspaces", json={"name": "Denied"}, headers={"Origin": ORIGIN}
        ).status_code
        == 403
    )
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    assert (
        client.post(
            "/api/v2/workspaces", json={"name": "Synthetic login team"}, headers=headers
        ).status_code
        == 201
    )
    assert client.delete("/api/v2/session", headers=headers).status_code == 204
    client.cookies.set(PENDING_COOKIE, verifier, path=LOGIN_PATH)
    assert complete(client, state).status_code == 400
    assert len(calls) == 1


@pytest.mark.postgres
@pytest.mark.parametrize("origin", [None, "null", "http://localhost", "http://127.0.0.1:8001"])
def test_login_initiation_requires_exact_origin(login_client, origin):
    client, calls, _, _, engine = login_client
    headers = {} if origin is None else {"Origin": origin}
    assert client.post(LOGIN_PATH, headers=headers).status_code == 403
    assert calls == [] and client.cookies.get(PENDING_COOKIE) is None
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM login_transactions")).scalar_one() == 0


@pytest.mark.postgres
@pytest.mark.parametrize(
    "mutation",
    [
        "issuer",
        "duplicate",
        "state",
        "missing-cookie",
        "duplicate-cookie",
        "oversize",
        "encoding",
    ],
)
def test_callback_rejects_ambiguous_unbound_or_oversized_input(login_client, mutation):
    client, calls, _, _, _ = login_client
    state, verifier, _, _ = begin(client)
    params = {"state": state, "iss": "https://identity.example", "code": "synthetic-code"}
    headers = {}
    if mutation == "issuer":
        params["iss"] = "https://evil.example"
    if mutation == "state":
        params["state"] = "invalid"
    if mutation == "missing-cookie":
        client.cookies.clear()
    if mutation == "duplicate-cookie":
        headers["Cookie"] = f"{PENDING_COOKIE} ={verifier}; {PENDING_COOKIE}={verifier}"
    raw = urlencode(params)
    if mutation == "duplicate":
        raw += "&code=second"
    if mutation == "oversize":
        raw += "x" * 8193
    if mutation == "encoding":
        raw = raw.replace("synthetic-code", "%FF")
    response = client.get(LOGIN_PATH + "/callback?" + raw, headers=headers)
    assert response.status_code == 400 and calls == []
    assert response.headers.get_list("set-cookie") == []
    assert client.cookies.get(PENDING_COOKIE) == (
        None if mutation == "missing-cookie" else verifier
    )
    assert client.cookies.get(COOKIE_NAME) is None


@pytest.mark.postgres
@pytest.mark.parametrize(
    "failure", ["forged", "expired", "audience", "client", "id-token", "scope", "network"]
)
def test_exchange_or_strict_verification_failure_consumes_once(login_client, failure):
    client, calls, outcome, sign, engine = login_client
    state, verifier, _, _ = begin(client)
    tokens = {
        "forged": "forged",
        "expired": sign(overrides={"exp": int(time.time()) - 60}),
        "audience": sign(overrides={"aud": "other-api"}),
        "client": sign(overrides={"client_id": "other-client"}),
        "id-token": sign(headers={"typ": "JWT"}),
        "scope": sign(overrides={"scope": "flowpilot:read"}),
    }
    if failure == "network":
        outcome["error"] = IdentityUnavailable()
    else:
        outcome["token"] = tokens[failure]
    response = complete(client, state)
    assert response.status_code == (503 if failure == "network" else 400)
    assert client.cookies.get(COOKIE_NAME) is None and client.cookies.get(PENDING_COOKIE) is None
    client.cookies.set(PENDING_COOKIE, verifier, path=LOGIN_PATH)
    assert complete(client, state).status_code == 400 and len(calls) == 1
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM browser_sessions")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT count(*) FROM login_transactions WHERE consumed_at IS NOT NULL")
            ).scalar_one()
            == 1
        )


@pytest.mark.postgres
def test_provider_denial_consumes_without_exchange(login_client):
    client, calls, _, _, engine = login_client
    state, _, _, _ = begin(client)
    raw = urlencode(
        {
            "state": state,
            "iss": "https://identity.example",
            "error": "access_denied",
            "error_description": "<untrusted>",
            "error_uri": "https://extension.example/ignored",
        }
    )
    response = client.post(
        LOGIN_PATH + "/complete",
        content=raw,
        headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400 and "cancelled" in response.text
    assert "<untrusted>" not in response.text and calls == []
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM login_transactions WHERE consumed_at IS NOT NULL")
            ).scalar_one()
            == 1
        )


@pytest.mark.postgres
def test_completion_revalidates_origin_cookie_state_and_existing_session(login_client):
    client, calls, _, _, _ = login_client
    state, verifier, _, _ = begin(client)
    assert (
        client.post(LOGIN_PATH, headers={"Origin": ORIGIN}, follow_redirects=False).status_code
        == 409
    )
    body = urlencode({"state": state, "iss": "https://identity.example", "code": "synthetic-code"})
    assert (
        client.post(
            LOGIN_PATH + "/complete",
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 403
    )
    assert client.cookies.get(PENDING_COOKIE) == verifier
    assert complete(client, secrets.token_urlsafe(32)).status_code == 400
    client.cookies.set(PENDING_COOKIE, verifier, path=LOGIN_PATH)
    assert complete(client, state).status_code == 200
    credential = client.cookies.get(COOKIE_NAME)
    assert (
        client.post(LOGIN_PATH, headers={"Origin": ORIGIN}, follow_redirects=False).status_code
        == 409
    )
    client.cookies.set(PENDING_COOKIE, verifier, path=LOGIN_PATH)
    assert complete(client, state).status_code == 409
    assert client.cookies.get(COOKIE_NAME) == credential and len(calls) == 1


@pytest.mark.postgres
@pytest.mark.parametrize("kind", ["authorization", "cross-site"])
def test_login_posts_reject_bearer_credentials_and_cross_site_metadata(login_client, kind):
    client, calls, _, sign, engine = login_client
    headers = {"Origin": ORIGIN}
    headers.update(
        {"Authorization": f"Bearer {sign()}"}
        if kind == "authorization"
        else {"Sec-Fetch-Site": "cross-site"}
    )
    expected = 409 if kind == "authorization" else 403
    assert client.post(LOGIN_PATH, headers=headers, follow_redirects=False).status_code == expected
    state, _, _, _ = begin(client)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    body = urlencode({"state": state, "iss": "https://identity.example", "code": "synthetic-code"})
    assert (
        client.post(LOGIN_PATH + "/complete", headers=headers, content=body).status_code == expected
    )
    assert calls == [] and client.cookies.get(COOKIE_NAME) is None
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM login_transactions WHERE consumed_at IS NOT NULL")
            ).scalar_one()
            == 0
        )


@pytest.mark.postgres
@pytest.mark.parametrize("kind", ["json", "oversize", "nonascii"])
def test_completion_rejects_invalid_form_before_consumption(login_client, kind):
    client, calls, _, _, engine = login_client
    begin(client)
    body = {"json": b"{}", "oversize": b"x" * 8193, "nonascii": b"\xff"}[kind]
    content_type = "application/json" if kind == "json" else "application/x-www-form-urlencoded"
    response = client.post(
        LOGIN_PATH + "/complete",
        content=body,
        headers={"Origin": ORIGIN, "Content-Type": content_type},
    )
    assert response.status_code == 400 and calls == []
    assert client.cookies.get(PENDING_COOKIE) is None
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM login_transactions WHERE consumed_at IS NOT NULL")
            ).scalar_one()
            == 0
        )
