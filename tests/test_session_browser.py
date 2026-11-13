"""Real Chromium + PostgreSQL, with a test-only HTML harness and signed JWTs."""

import os
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.responses import HTMLResponse
from flowpilot_api.browser_sessions import COOKIE_NAME
from flowpilot_api.workspace_api import create_workspace_app

pytestmark = [pytest.mark.browser, pytest.mark.postgres]


@pytest.fixture
def session_browser(pg, token_tools):
    if os.environ.get("FLOWPILOT_BROWSER_TESTS") != "1":
        pytest.skip("Enable FLOWPILOT_BROWSER_TESTS=1 and install Playwright Chromium")
    from playwright.sync_api import sync_playwright

    _, verifier, sign = token_tools
    sockets = [socket.socket(), socket.socket()]
    for sock in sockets:
        sock.bind(("127.0.0.1", 0))
    origin, foreign = [f"http://127.0.0.1:{sock.getsockname()[1]}" for sock in sockets]
    app = create_workspace_app(engine=pg[0], verifier=verifier, browser_origin=origin)

    @app.get("/api/v2/test-browser", response_class=HTMLResponse)
    def harness():
        return "<!doctype html><title>Synthetic session test</title>"

    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": sockets}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                pytest.fail("Session browser server failed to start")
            time.sleep(0.02)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(origin + "/api/v2/test-browser")
                yield page, context, origin, foreign, sign
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        for sock in sockets:
            sock.close()
        assert not thread.is_alive(), "Session browser server did not shut down"


def fetch(page, path, *, method="GET", headers=None, body=None):
    return page.evaluate(
        """async ({path, method, headers, body}) => {
        const response = await fetch(path, {method, headers, body});
        return {status: response.status, text: await response.text()};
    }""",
        {"path": path, "method": method, "headers": headers or {}, "body": body},
    )


def test_browser_cookie_reload_write_and_logout(session_browser):
    import json

    page, context, _, _, sign = session_browser
    issued = fetch(
        page,
        "/api/v2/session",
        method="POST",
        headers={"Authorization": f"Bearer {sign('browser-user')}"},
    )
    assert issued["status"] == 201
    csrf = json.loads(issued["text"])["csrf_token"]
    cookies = context.cookies()
    cookie = next(cookie for cookie in cookies if cookie["name"] == COOKIE_NAME)
    assert cookie["httpOnly"] and cookie["sameSite"] == "Strict"
    assert COOKIE_NAME not in page.evaluate("document.cookie")
    page.reload()
    with page.expect_request("**/api/v2/session") as request:
        info = fetch(page, "/api/v2/session")
    assert "origin" not in request.value.headers
    assert info["status"] == 200
    assert json.loads(info["text"])["csrf_token"] == csrf
    payload = json.dumps({"name": "Synthetic browser workspace"})
    assert (
        fetch(
            page,
            "/api/v2/workspaces",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=payload,
        )["status"]
        == 403
    )
    assert (
        fetch(
            page,
            "/api/v2/workspaces",
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
            body=payload,
        )["status"]
        == 201
    )
    assert len(json.loads(fetch(page, "/api/v2/workspaces")["text"])) == 1
    assert (
        fetch(page, "/api/v2/session", method="DELETE", headers={"X-CSRF-Token": csrf})["status"]
        == 204
    )
    page.reload()
    assert fetch(page, "/api/v2/session")["status"] == 401
    assert not any(cookie["name"] == COOKIE_NAME for cookie in context.cookies())


def test_browser_same_site_other_port_cannot_use_cookie(session_browser):
    page, context, origin, foreign, sign = session_browser
    assert (
        fetch(
            page, "/api/v2/session", method="POST", headers={"Authorization": f"Bearer {sign()}"}
        )["status"]
        == 201
    )
    attacker = context.new_page()
    attacker.goto(foreign + "/api/v2/test-browser")
    # Cookies are not port-scoped. Real Fetch Metadata and Origin must deny this.
    with attacker.expect_response(origin + "/api/v2/session") as response:
        attacker.evaluate(
            """async origin => {
            await fetch(origin + '/api/v2/session', {
                method: 'POST', mode: 'no-cors', credentials: 'include'
            });
        }""",
            origin,
        )
    assert response.value.status == 401  # Existing cookie cannot exchange a new identity.
    with attacker.expect_response(origin + "/api/v2/workspaces") as response:
        attacker.evaluate(
            """async origin => {
            await fetch(origin + '/api/v2/workspaces', {
                method: 'POST', mode: 'no-cors', credentials: 'include', body: '{}'
            });
        }""",
            origin,
        )
    assert response.value.status == 403
    assert fetch(page, "/api/v2/session")["status"] == 200
    assert fetch(attacker, "/api/v2/session")["status"] == 403
