"""Real cross-site Chromium redirects, pending Lax cookie, and Strict completion."""

import json
import os
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from html import escape
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import jwt
import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from flowpilot_api.browser_sessions import COOKIE_NAME
from flowpilot_api.identity import AccessTokenVerifier, IdentityConfig
from flowpilot_api.login import LOGIN_PATH, PENDING_COOKIE, LoginConfig
from flowpilot_api.workspace_api import create_workspace_app

pytestmark = [pytest.mark.browser, pytest.mark.postgres]


@pytest.fixture
def login_browser(pg, tmp_path):
    if os.environ.get("FLOWPILOT_BROWSER_TESTS") != "1":
        pytest.skip("Enable FLOWPILOT_BROWSER_TESTS=1 and install Playwright Chromium")
    from playwright.sync_api import sync_playwright

    sockets = [socket.socket(), socket.socket()]
    for sock in sockets:
        sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sockets[0].getsockname()[1]}"
    provider = f"https://localhost:{sockets[1].getsockname()[1]}"
    # Use a real HTTPS redirect target. Playwright routing only intercepts the
    # first request in a Chromium redirect chain (including a 303 after POST).
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path, cert_path = tmp_path / "provider.key", tmp_path / "provider.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    identity = IdentityConfig(provider, "flowpilot-api", provider + "/jwks")
    verifier = AccessTokenVerifier(identity, key_resolver=lambda _: key.public_key())
    calls = []

    def sign(subject):
        issued = int(time.time())
        return jwt.encode(
            {
                "iss": provider,
                "aud": identity.audience,
                "sub": subject,
                "iat": issued,
                "exp": issued + 300,
                "jti": str(uuid4()),
                "client_id": "synthetic-client",
                "scope": "flowpilot:read flowpilot:write",
            },
            key,
            algorithm="RS256",
            headers={"typ": "at+jwt", "kid": "synthetic-key"},
        )

    def exchange(code, verifier):
        calls.append((code, verifier))
        return sign("new-browser-user")

    app = create_workspace_app(
        engine=pg[0],
        verifier=verifier,
        browser_origin=origin,
        login_config=LoginConfig(
            "synthetic-client",
            provider + "/authorize",
            provider + "/token",
        ),
        login_exchange=exchange,
    )

    provider_app = FastAPI()

    @provider_app.get("/authorize", response_class=HTMLResponse)
    def provider_page(request: Request):
        query = request.query_params
        callback = (
            query["redirect_uri"]
            + "?"
            + urlencode(
                {
                    "state": query["state"],
                    "iss": provider,
                    "code": "synthetic-browser-code",
                }
            )
        )
        return (
            '<!doctype html><title>Synthetic provider</title><a href="'
            + escape(callback, quote=True)
            + '">Return to FlowPilot</a>'
        )

    @app.get("/api/v2/test-login-browser", response_class=HTMLResponse)
    def harness():
        return "<!doctype html><title>Synthetic browser harness</title>"

    loop = "asyncio:SelectorEventLoop" if os.name == "nt" else "auto"
    servers = [
        uvicorn.Server(uvicorn.Config(app, log_level="error", loop=loop, access_log=False)),
        uvicorn.Server(
            uvicorn.Config(
                provider_app,
                log_level="error",
                loop=loop,
                access_log=False,
                ssl_certfile=str(cert_path),
                ssl_keyfile=str(key_path),
            )
        ),
    ]
    threads = [
        threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        for server, sock in zip(servers, sockets, strict=True)
    ]
    for thread in threads:
        thread.start()
    try:
        deadline = time.monotonic() + 10
        while not all(server.started for server in servers):
            if not all(thread.is_alive() for thread in threads) or time.monotonic() > deadline:
                pytest.fail("Login browser server failed to start")
            time.sleep(0.02)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()
                page.set_default_timeout(10000)
                page.goto(origin + LOGIN_PATH)
                yield page, context, origin, provider, sign, calls
            finally:
                browser.close()
    finally:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            thread.join(timeout=10)
        for sock in sockets:
            sock.close()
        assert not any(thread.is_alive() for thread in threads), (
            "Login browser servers did not stop"
        )


def fetch(page, path, *, method="GET", headers=None, body=None):
    return page.evaluate(
        """async ({path, method, headers, body}) => {
            const response = await fetch(path, {method, headers, body});
            return {status: response.status, text: await response.text()};
        }""",
        {"path": path, "method": method, "headers": headers or {}, "body": body},
    )


def go_to_provider(page, provider):
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_url(provider + "/authorize?**")
    query = parse_qs(urlsplit(page.url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["flowpilot:read flowpilot:write"]


def test_cross_site_login_continues_into_session_reload_write_logout(login_browser):
    page, context, origin, provider, _, calls = login_browser
    go_to_provider(page, provider)
    pending = next(cookie for cookie in context.cookies() if cookie["name"] == PENDING_COOKIE)
    assert pending["httpOnly"] and pending["sameSite"] == "Lax"
    assert pending["path"] == LOGIN_PATH
    assert PENDING_COOKIE not in page.evaluate("document.cookie")
    with page.expect_request(origin + LOGIN_PATH + "/callback?**") as callback:
        page.get_by_role("link", name="Return to FlowPilot").click()
    page.get_by_role("button", name="Continue sign-in").wait_for()
    callback_headers = callback.value.all_headers()
    assert callback_headers["sec-fetch-site"] == "cross-site"
    assert PENDING_COOKIE + "=" in callback_headers.get("cookie", "")
    assert COOKIE_NAME + "=" not in callback_headers.get("cookie", "")
    assert calls == []
    with page.expect_request(origin + LOGIN_PATH + "/complete") as completion:
        page.get_by_role("button", name="Continue sign-in").click()
    page.get_by_role("heading", name="Signed in to FlowPilot").wait_for()
    assert completion.value.all_headers()["origin"] == origin
    assert completion.value.all_headers()["sec-fetch-site"] == "same-origin"
    assert completion.value.all_headers()["referer"] == origin + "/"
    assert len(calls) == 1 and calls[0][0] == "synthetic-browser-code"
    cookies = context.cookies()
    session = next(cookie for cookie in cookies if cookie["name"] == COOKIE_NAME)
    assert session["sameSite"] == "Strict" and session["httpOnly"]
    assert not any(cookie["name"] == PENDING_COOKIE for cookie in cookies)
    assert COOKIE_NAME not in page.evaluate("document.cookie")
    page.goto(origin + "/api/v2/test-login-browser")
    page.reload()
    info = fetch(page, "/api/v2/session")
    assert info["status"] == 200
    csrf = json.loads(info["text"])["csrf_token"]
    body = json.dumps({"name": "Synthetic login browser workspace"})
    assert (
        fetch(
            page,
            "/api/v2/workspaces",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=body,
        )["status"]
        == 403
    )
    assert (
        fetch(
            page,
            "/api/v2/workspaces",
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
            body=body,
        )["status"]
        == 201
    )
    assert (
        fetch(page, "/api/v2/session", method="DELETE", headers={"X-CSRF-Token": csrf})["status"]
        == 204
    )
    page.reload()
    assert fetch(page, "/api/v2/session")["status"] == 401
    assert not any(cookie["name"] == COOKIE_NAME for cookie in context.cookies())


def test_cross_site_callback_cannot_replace_session_hidden_by_strict_cookie(login_browser):
    page, context, origin, provider, sign, calls = login_browser
    go_to_provider(page, provider)
    # A second tab signs in while the pending login remains at the foreign provider.
    incumbent = context.new_page()
    incumbent.goto(origin + "/api/v2/test-login-browser")
    issued = fetch(
        incumbent,
        "/api/v2/session",
        method="POST",
        headers={"Authorization": f"Bearer {sign('incumbent-browser-user')}"},
    )
    assert issued["status"] == 201
    credential = next(
        cookie["value"] for cookie in context.cookies() if cookie["name"] == COOKIE_NAME
    )
    with page.expect_request(origin + LOGIN_PATH + "/callback?**") as callback:
        page.get_by_role("link", name="Return to FlowPilot").click()
    page.get_by_role("button", name="Continue sign-in").wait_for()
    headers = callback.value.all_headers()
    assert headers["sec-fetch-site"] == "cross-site"
    assert PENDING_COOKIE + "=" in headers.get("cookie", "")
    assert COOKIE_NAME + "=" not in headers.get("cookie", "")
    with page.expect_response(origin + LOGIN_PATH + "/complete") as response:
        page.get_by_role("button", name="Continue sign-in").click()
    assert response.value.status == 409
    completion_headers = response.value.request.all_headers()
    assert completion_headers["origin"] == origin
    assert completion_headers["sec-fetch-site"] == "same-origin"
    assert COOKIE_NAME + "=" in completion_headers.get("cookie", "")
    assert calls == []
    assert (
        next(cookie["value"] for cookie in context.cookies() if cookie["name"] == COOKIE_NAME)
        == credential
    )
    assert not any(cookie["name"] == PENDING_COOKIE for cookie in context.cookies())
    assert fetch(incumbent, "/api/v2/session")["status"] == 200
