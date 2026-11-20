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
from sqlalchemy import text

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

    def sign(subject, *, scope="flowpilot:read flowpilot:write"):
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
                "scope": scope,
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


def open_workspace(page, origin, provider):
    go_to_provider(page, provider)
    page.get_by_role("link", name="Return to FlowPilot").click()
    page.get_by_role("button", name="Continue sign-in").click()
    page.get_by_role("link", name="Open workspace").click()
    page.wait_for_url(origin + "/api/v2/workspace")
    page.get_by_role("heading", name="Workspaces", exact=True).wait_for()


def create_workspace_in_browser(page, origin, name):
    page.get_by_role("textbox", name="Workspace name").fill(name)
    with page.expect_response(
        lambda response: (
            response.url == origin + "/api/v2/workspaces" and response.request.method == "POST"
        )
    ) as creation:
        page.get_by_role("button", name="Create workspace").click()
    assert creation.value.status == 201
    return creation.value.json()["id"]


def seed_browser_work(page, workspace_id, titles, *, due_date=None):
    session = fetch(page, "/api/v2/session")
    assert session["status"] == 200
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": json.loads(session["text"])["csrf_token"],
    }
    for title in titles:
        created = fetch(
            page,
            f"/api/v2/workspaces/{workspace_id}/work",
            method="POST",
            headers=headers,
            body=json.dumps({"item": {"kind": "task", "title": title, "due_date": due_date}}),
        )
        assert created["status"] == 201


def enter_source_draft(page, reference, summary, excerpt):
    page.get_by_role("button", name="Add source", exact=True).click()
    page.get_by_label("Source reference", exact=True).fill(reference)
    page.get_by_label("Source summary", exact=True).fill(summary)
    page.get_by_label("Source excerpt", exact=True).fill(excerpt)


def capture_source_in_browser(page, reference, summary, excerpt):
    from playwright.sync_api import expect

    enter_source_draft(page, reference, summary, excerpt)
    with page.expect_response(
        lambda response: response.url.endswith("/sources") and response.request.method == "POST"
    ) as saved:
        page.get_by_role("button", name="Save source", exact=True).click()
    assert saved.value.status == 201
    expect(page.get_by_text("Source saved.", exact=True)).to_be_visible()
    return saved.value.json()["id"]


def test_workspace_browser_captures_and_reviews_private_sources(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Synthetic review workspace")
    inbox = page.get_by_role("button", name="Private inbox", exact=True)
    inbox.click()
    expect(page.get_by_text("No sources yet.", exact=True)).to_be_visible()
    first = "Prepare the workshop packet"
    source_id = capture_source_in_browser(
        page, "workshop-note", first, "<strong>A printed outline</strong>"
    )
    base = f"/api/v2/workspaces/{workspace_id}"
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    for index in range(20):
        created = fetch(
            page,
            base + "/sources",
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
            body=json.dumps(
                {
                    "reference": f"extra-{index}",
                    "summary": f"Note {index}",
                    "excerpt": "Synthetic text",
                }
            ),
        )
        assert created["status"] == 201
    page.reload()
    inbox.click()
    first_row = page.get_by_role("button", name=first, exact=True)
    more = page.get_by_role("button", name="Load more sources", exact=True)
    expect(more).to_be_visible()
    expect(first_row).to_have_count(0)
    more.click()
    first_row.click()
    expect(page.get_by_text("<strong>A printed outline</strong>", exact=True)).to_be_visible()
    expect(page.get_by_text("workshop-note", exact=True)).to_be_visible()
    with page.expect_response(origin + base + f"/sources/{source_id}/task-proposal") as suggested:
        page.get_by_role("button", name="Suggest task", exact=True).click()
    assert suggested.value.status == 200
    proposal = suggested.value.json()
    assert proposal["version"] == 1 and proposal["due_date"] is None
    title = page.get_by_label("Suggested task title", exact=True)
    expect(title).to_have_value(first)
    due_date = page.get_by_label("Suggested due date", exact=True)
    accept = page.get_by_role("button", name="Accept and create task", exact=True)
    due_date.focus()
    page.keyboard.press("2")
    assert due_date.evaluate("element => element.validity.badInput")
    expect(due_date).to_have_value("")
    expect(accept).to_be_disabled()
    expect(page.get_by_text("Enter a complete due date.", exact=True)).to_be_visible()
    due_date.fill("2030-07-08")
    assert not due_date.evaluate("element => element.validity.badInput")
    expect(accept).to_be_disabled()
    due_date.fill("")
    expect(accept).to_be_enabled()
    title.fill("Send the workshop packet")
    due_date.fill("2030-07-08")
    expect(accept).to_be_disabled()
    with page.expect_response(origin + base + f"/proposals/{proposal['id']}") as corrected:
        page.get_by_role("button", name="Save suggestion changes", exact=True).click()
    assert corrected.value.status == 200 and corrected.value.json()["version"] == 2
    with page.expect_response("**/review") as accepted:
        accept.click()
    assert accepted.value.status == 200 and accepted.value.json()["version"] == 3
    task = accepted.value.json()
    assert task["state"] == "accepted" and task["work_id"]
    expect(page.get_by_text("Private task created.", exact=True)).to_be_visible()
    expect(accept).to_be_hidden()
    page.get_by_role("button", name="Go to work list", exact=True).click()
    row = page.get_by_role("listitem").filter(has_text="Send the workshop packet")
    expect(row.get_by_text("Due 2030-07-08")).to_be_visible()
    stored = json.loads(fetch(page, base + f"/work/{task['work_id']}")["text"])
    assert stored["visibility"] == "private" and stored["data"]["status"] == "open"

    inbox.click()
    second = "Optional venue walkthrough"
    capture_source_in_browser(page, "venue-note", second, "Discuss at a later meeting")
    page.get_by_role("button", name=second, exact=True).click()
    page.get_by_role("button", name="Suggest task", exact=True).click()
    page.once("dialog", lambda dialog: dialog.accept())
    with page.expect_response("**/review") as dismissed:
        page.get_by_role("button", name="Dismiss suggestion", exact=True).click()
    assert dismissed.value.status == 200
    assert (
        dismissed.value.json()["state"] == "dismissed" and dismissed.value.json()["work_id"] is None
    )
    expect(page.get_by_text("Suggestion dismissed.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Refresh inbox", exact=True).click()
    more.click()
    rows = page.get_by_role("list", name="Sources").get_by_role("listitem")
    expect(rows.filter(has_text=first)).to_contain_text("Accepted")
    expect(rows.filter(has_text=second)).to_contain_text("Dismissed")


def test_workspace_browser_recovers_stale_and_unconfirmed_review(login_browser):
    from playwright.sync_api import Route, expect

    page, context, origin, provider, sign, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Synthetic review recovery")
    inbox = page.get_by_role("button", name="Private inbox", exact=True)
    inbox.click()
    name = "A source awaiting review"
    capture_source_in_browser(page, "recovery-note", name, "Review the current saved title")
    page.get_by_role("button", name=name, exact=True).click()
    with page.expect_response("**/task-proposal") as suggested:
        page.get_by_role("button", name="Suggest task", exact=True).click()
    base = f"/api/v2/workspaces/{workspace_id}"
    proposal_path = base + f"/proposals/{suggested.value.json()['id']}"
    accept = page.get_by_role("button", name="Accept and create task", exact=True)
    expect(accept).to_be_enabled()
    session = json.loads(fetch(page, "/api/v2/session")["text"])
    corrected = fetch(
        page,
        proposal_path,
        method="PATCH",
        headers={"Content-Type": "application/json", "X-CSRF-Token": session["csrf_token"]},
        body=json.dumps(
            {"title": "Latest reviewed title", "due_date": None, "expected_version": 1}
        ),
    )
    assert corrected["status"] == 200
    with page.expect_response(origin + proposal_path + "/review") as stale:
        accept.click()
    assert stale.value.status == 409
    expect(accept).to_be_disabled()
    expect(page.get_by_text("The suggestion changed.", exact=False)).to_be_visible()
    reload_details = page.get_by_role("button", name="Reload source details", exact=True)
    reload_details.click()
    expect(page.get_by_label("Suggested task title", exact=True)).to_have_value(
        "Latest reviewed title"
    )

    def lose_confirmed_response(route: Route) -> None:
        expect(page.get_by_role("button", name="Work items", exact=True)).to_be_disabled()
        result = route.fetch()
        assert result.status == 200 and result.json()["state"] == "accepted"
        route.fulfill(status=503)

    page.route(origin + proposal_path + "/review", lose_confirmed_response, times=1)
    accept.click()
    expect(page.get_by_text("Could not confirm the decision.", exact=False)).to_be_visible()
    expect(accept).to_be_disabled()
    expect(page.get_by_role("button", name="Work items", exact=True)).to_be_enabled()
    reload_details.click()
    expect(page.get_by_role("button", name="Go to work list", exact=True)).to_be_visible()
    expect(accept).to_be_hidden()
    work = json.loads(fetch(page, base + "/work-page")["text"])["items"]
    assert [item["data"]["title"] for item in work] == ["Latest reviewed title"]

    pending_name = "Another pending suggestion"
    enter_source_draft(
        page, "uncertain-source", pending_name, "Source saved before response failed"
    )

    def lose_capture_response(route: Route) -> None:
        response = route.fetch()
        assert response.status == 201
        route.fulfill(status=503)

    page.route(origin + base + "/sources", lose_capture_response, times=1)
    save_source = page.get_by_role("button", name="Save source", exact=True)
    save_source.click()
    expect(page.get_by_text("Could not confirm the source was saved.", exact=False)).to_be_visible()
    expect(save_source).to_be_disabled()
    expect(page.get_by_label("Source reference", exact=True)).to_have_value("uncertain-source")
    page.get_by_role("button", name="Refresh inbox", exact=True).click()
    pending_row = page.get_by_role("button", name=pending_name, exact=True)
    expect(pending_row).to_have_count(1)
    expect(save_source).to_be_enabled()
    page.get_by_role("button", name="Close source form", exact=True).click()
    pending_row.click()
    page.get_by_role("button", name="Suggest task", exact=True).click()
    expect(accept).to_be_enabled()

    context.clear_cookies()
    page.goto(origin + "/api/v2/test-login-browser")
    read_token = sign("new-browser-user", scope="flowpilot:read")
    exchanged = fetch(
        page, "/api/v2/session", method="POST", headers={"Authorization": f"Bearer {read_token}"}
    )
    assert exchanged["status"] == 201
    page.goto(origin + "/api/v2/workspace")
    inbox.click()
    pending_row.click()
    title = page.get_by_label("Suggested task title", exact=True)
    expect(title).to_have_value(pending_name)
    assert title.evaluate("element => element.readOnly")
    expect(page.get_by_role("button", name="Add source", exact=True)).to_be_hidden()
    expect(accept).to_be_hidden()


def test_workspace_browser_keeps_inbox_read_only_after_role_downgrade(login_browser, pg):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Synthetic role downgrade")
    inbox = page.get_by_role("button", name="Private inbox", exact=True)
    work = page.get_by_role("button", name="Work items", exact=True)
    inbox.click()
    source = "Reread the prior evidence"
    capture_source_in_browser(page, "downgrade-source", source, "Private retained evidence")
    source_button = page.get_by_role("button", name=source, exact=True)
    source_button.click()
    page.get_by_role("button", name="Suggest task", exact=True).click()
    accept = page.get_by_role("button", name="Accept and create task", exact=True)
    expect(accept).to_be_enabled()

    with pg[0].begin() as connection:
        connection.execute(
            text("UPDATE memberships SET role='observer' WHERE workspace_id=CAST(:ws AS uuid)"),
            {"ws": workspace_id},
        )
    with page.expect_response("**/review") as denied:
        accept.click()
    assert denied.value.status == 403
    expect(page.get_by_text("Inbox access changed.", exact=False)).to_be_visible()
    expect(source_button).to_have_count(0)
    expect(page.get_by_text("Private retained evidence", exact=True)).to_have_count(0)

    page.get_by_role("button", name="Refresh inbox", exact=True).click()
    source_button.click()
    expect(page.get_by_text("Private retained evidence", exact=True)).to_be_visible()
    expect(accept).to_be_hidden()
    add_source = page.get_by_role("button", name="Add source", exact=True)
    expect(add_source).to_be_hidden()
    work.click()
    inbox.click()
    expect(source_button).to_be_visible()
    expect(add_source).to_be_hidden()


@pytest.mark.parametrize("delayed_status", [200, 401])
def test_workspace_browser_ignores_late_inbox_details_after_switch(login_browser, delayed_status):
    from playwright.sync_api import Route, expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First inbox workspace")
    page.get_by_role("button", name="Private inbox", exact=True).click()
    name = "First workspace source summary"
    secret = "First workspace private excerpt"
    source_id = capture_source_in_browser(page, "first-source", name, secret)
    second = create_workspace_in_browser(page, origin, "Second inbox workspace")
    selector = page.get_by_label("Workspace", exact=True)
    selector.select_option(first)
    path = f"/api/v2/workspaces/{first}/sources/{source_id}"
    page.evaluate(
        """path => {
            const actualFetch = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await actualFetch(url, options);
                if (new URL(url, location.href).pathname !== path) return response;
                const signal = () => setTimeout(() => { window.sourceHandled = true; }, 0);
                if (!response.ok) signal();
                else {
                    const json = response.json.bind(response);
                    response.json = async () => {
                        const value = await json();
                        signal();
                        return value;
                    };
                }
                return response;
            };
        }""",
        path,
    )
    held: list[Route] = []
    page.route(origin + path, lambda route: held.append(route), times=1)
    with page.expect_request(origin + path):
        page.get_by_role("button", name=name, exact=True).click()
    selector.select_option(second)
    expect(page.get_by_text("No sources yet.", exact=True)).to_be_visible()
    assert len(held) == 1
    if delayed_status == 200:
        response = held[0].fetch()
        assert response.ok and response.json()["excerpt"] == secret
        held[0].fulfill(response=response)
    else:
        held[0].fulfill(status=401, json={"detail": "Unauthorized"})
    page.wait_for_function("window.sourceHandled === true")
    expect(page.get_by_text(secret, exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name=name, exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()


def test_workspace_browser_onboards_browses_and_signs_out(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    expect(page.get_by_text("Create your first workspace to get started.")).to_be_visible()
    selector = page.get_by_label("Workspace", exact=True)
    expect(selector).to_be_disabled()
    name = "Synthetic browser workspace"
    workspace_id = create_workspace_in_browser(page, origin, name)
    expect(selector).to_have_value(workspace_id)
    expect(page.get_by_text("No work items yet.", exact=True)).to_be_visible()

    oldest = "Oldest task on the next page"
    literal_title = "<strong>Synthetic title</strong>"
    titles = [oldest, *(f"Synthetic task {index:02}" for index in range(1, 20)), literal_title]
    seed_browser_work(page, workspace_id, titles)
    page.reload()
    expect(selector).to_have_value(workspace_id)
    expect(selector.locator("option:checked")).to_have_text(name)
    newest_item = page.get_by_text(literal_title, exact=True)
    oldest_item = page.get_by_text(oldest, exact=True)
    expect(newest_item).to_be_visible()
    load_more = page.get_by_role("button", name="Load more", exact=True)
    expect(load_more).to_be_visible()
    expect(oldest_item).to_have_count(0)
    load_more.click()
    expect(oldest_item).to_be_visible()
    expect(newest_item).to_be_visible()
    expect(load_more).to_be_hidden()

    with page.expect_response(
        lambda response: (
            response.url == origin + "/api/v2/session" and response.request.method == "DELETE"
        )
    ) as logout:
        page.get_by_role("button", name="Sign out", exact=True).click()
    assert logout.value.status == 204
    expect(page.get_by_role("link", name="Sign in", exact=True)).to_be_visible()
    expect(newest_item).to_have_count(0)
    assert not any(cookie["name"] == COOKIE_NAME for cookie in context.cookies())
    page.reload()
    expect(page.get_by_role("link", name="Sign in", exact=True)).to_be_visible()


def test_workspace_browser_creates_edits_and_recovers_from_stale_task(login_browser):
    from playwright.sync_api import Route, expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Synthetic task workspace")
    work_path = f"/api/v2/workspaces/{workspace_id}/work"
    title = page.get_by_label("Task title", exact=True)
    description = page.get_by_label("Description", exact=True)
    due_date = page.get_by_label("Due date", exact=True)
    page.get_by_role("button", name="New task", exact=True).click()
    title.fill("Prepare the synthetic agenda")
    description.fill("<strong>Outline</strong>")
    due_date.fill("2030-01-02")
    with page.expect_response(
        lambda response: response.url == origin + work_path and response.request.method == "POST"
    ) as creation:
        page.get_by_role("button", name="Create task", exact=True).click()
    assert creation.value.status == 201
    created = creation.value.json()
    assert created["visibility"] == "private" and created["data"]["status"] == "open"
    expect(page.get_by_text("Task created.", exact=True)).to_be_visible()
    row = page.get_by_role("listitem").filter(has_text="Prepare the synthetic agenda")
    expect(row.get_by_text("<strong>Outline</strong>", exact=True)).to_be_visible()
    expect(row.get_by_text("Due 2030-01-02")).to_be_visible()
    row.get_by_role("button", name="Edit task", exact=True).click()
    expect(title).to_have_value("Prepare the synthetic agenda")
    expect(description).to_have_value("<strong>Outline</strong>")
    expect(due_date).to_have_value("2030-01-02")

    updated_title = "Finalize the synthetic agenda"
    title.fill(updated_title)
    description.fill("")
    due_date.fill("2030-02-03")
    edit_path = work_path + f"/{created['id']}/task-details"
    save = page.get_by_role("button", name="Save changes", exact=True)

    def check_pending_editor(route: Route) -> None:
        for field in (title, description, due_date):
            assert field.evaluate("element => element.readOnly")
        expect(save).to_be_disabled()
        route.continue_()

    page.route(origin + edit_path, check_pending_editor, times=1)
    with page.expect_response(origin + edit_path) as update:
        save.click()
    assert update.value.status == 200
    updated = update.value.json()
    assert updated["version"] == created["version"] + 1
    expect(page.get_by_text("Task updated.", exact=True)).to_be_visible()
    page.reload()
    updated_row = page.get_by_role("listitem").filter(has_text=updated_title)
    expect(updated_row.get_by_text("Due 2030-02-03")).to_be_visible()
    updated_row.get_by_role("button", name="Edit task", exact=True).click()
    expect(title).to_have_value(updated_title)
    expect(description).to_have_value("")
    expect(due_date).to_have_value("2030-02-03")

    title.fill("Draft in the older editor")
    latest = "Agenda changed\r\nin another editor"
    latest_description = "Agenda outline\r\nSecond item"
    session = fetch(page, "/api/v2/session")
    assert session["status"] == 200
    changed = fetch(
        page,
        edit_path,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": json.loads(session["text"])["csrf_token"],
        },
        body=json.dumps(
            {
                "expected_version": updated["version"],
                "details": {
                    "title": latest,
                    "description": latest_description,
                    "due_date": None,
                },
            }
        ),
    )
    assert changed["status"] == 200
    with page.expect_response(origin + edit_path) as conflict:
        save.click()
    assert conflict.value.status == 409
    expect(page.get_by_text("This task changed.", exact=False)).to_be_visible()
    expect(title).to_have_value("Draft in the older editor")
    expect(save).to_be_disabled()
    assert not title.evaluate("element => element.readOnly")
    page.get_by_role("button", name="Cancel", exact=True).click()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    latest_row = page.get_by_role("listitem").filter(has_text="Agenda changed")
    latest_row.get_by_role("button", name="Edit task", exact=True).click()
    expect(title).to_have_value(latest.replace("\r\n", "\n"))
    expect(description).to_have_value(latest_description.replace("\r\n", "\n"))
    expect(due_date).to_have_value("")
    expect(save).to_be_enabled()
    due_date.fill("2030-03-04")
    with page.expect_response(origin + edit_path) as due_date_update:
        save.click()
    assert due_date_update.value.status == 200
    assert due_date_update.value.json()["data"] == {
        **json.loads(changed["text"])["data"],
        "due_date": "2030-03-04",
    }


def test_workspace_browser_prioritizes_and_completes_due_tasks(login_browser):
    from playwright.sync_api import Route, expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Task lifecycle workspace")
    urgent = "Old task with the earliest deadline"
    seed_browser_work(page, workspace_id, [urgent], due_date="2026-01-02")
    titles = [f"Dated item {index:02d}" for index in range(20)]
    seed_browser_work(page, workspace_id, titles, due_date="2026-01-03")
    page.reload()
    work_view = page.get_by_label("Work view", exact=True)
    row = page.get_by_role("listitem").filter(has_text=urgent)
    expect(page.get_by_role("button", name="Load more", exact=True)).to_be_visible()
    expect(row).to_have_count(0)

    work_view.select_option("due")
    expect(page.get_by_role("listitem").first).to_contain_text(urgent)
    expect(page.get_by_text("Showing the 20 earliest deadlines.", exact=False)).to_be_visible()
    expect(page.get_by_role("listitem")).to_have_count(20)
    expect(page.get_by_text(titles[0], exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Load more", exact=True)).to_be_hidden()
    row.get_by_role("button", name="Edit task", exact=True).click()
    expect(work_view).to_be_disabled()
    expect(row.get_by_role("button", name="Start task", exact=True)).to_be_disabled()
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(work_view).to_have_value("due")

    def click_status(label):
        with page.expect_response("**/transitions") as update:
            row.get_by_role("button", name=label, exact=True).click()
        assert update.value.status == 200
        return update.value.json()

    def check_pending_update(route: Route) -> None:
        expect(row.get_by_role("button", name="Edit task", exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="New task", exact=True)).to_be_disabled()
        expect(work_view).to_be_disabled()
        route.continue_()

    page.route("**/transitions", check_pending_update, times=1)
    started = click_status("Start task")
    assert started["data"]["status"] == "active" and started["version"] == 2
    blocked = click_status("Block task")
    assert blocked["data"]["status"] == "blocked" and blocked["version"] == 3
    resumed = click_status("Resume task")
    assert resumed["data"]["status"] == "active" and resumed["version"] == 4
    expect(row.get_by_role("button", name="Complete task", exact=True)).to_be_enabled()
    page.route("**/work-due?**", lambda route: route.fulfill(status=503), times=1)
    completed = click_status("Complete task")
    assert completed["data"]["status"] == "completed" and completed["version"] == 5
    expect(page.get_by_text("Could not load work items.", exact=True)).to_be_visible()
    expect(page.get_by_text("Task status updated.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(page.get_by_text(titles[0], exact=True)).to_be_visible()
    expect(row).to_have_count(0)
    expect(page.get_by_role("listitem")).to_have_count(20)
    expect(page.get_by_text("Showing the 20 earliest deadlines.", exact=False)).to_have_count(0)

    other = page.get_by_role("listitem").filter(has_text=titles[-1])
    cancel = other.get_by_role("button", name="Cancel task", exact=True)
    page.once("dialog", lambda dialog: dialog.dismiss())
    cancel.click()
    expect(other).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    with page.expect_response("**/transitions") as cancellation:
        cancel.click()
    assert cancellation.value.status == 200
    assert cancellation.value.json()["data"]["status"] == "canceled"
    expect(other).to_have_count(0)

    work_view.select_option("all")
    page.get_by_role("button", name="Load more", exact=True).click()
    expect(row).to_contain_text("completed")
    expect(row.get_by_role("button", name="Start task", exact=True)).to_have_count(0)
    next_task = page.get_by_role("listitem").filter(has_text=titles[-2])
    next_task.get_by_role("button", name="Start task", exact=True).click()
    expect(next_task.get_by_role("button", name="Complete task", exact=True)).to_be_visible()
    expect(row).to_be_visible()
    expect(page.get_by_role("listitem")).to_have_count(21)


def test_workspace_browser_today_shows_pending_reviews_separately_from_due_work(login_browser):
    from playwright.sync_api import Route, expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Today reviews workspace")
    seed_browser_work(page, workspace_id, ["Overdue synthetic task"], due_date="2020-01-02")
    page.get_by_role("button", name="Private inbox", exact=True).click()
    title = "<strong>Review the draft</strong>"
    capture_source_in_browser(page, "today-review", title, "Synthetic excerpt")
    page.get_by_role("button", name=title, exact=True).click()
    page.get_by_role("button", name="Suggest task", exact=True).click()
    expect(page.get_by_role("button", name="Accept and create task", exact=True)).to_be_enabled()

    today = page.get_by_role("button", name="Today", exact=True)
    queue_url = origin + f"/api/v2/workspaces/{workspace_id}/proposals?limit=5"
    page.route(queue_url, lambda route: route.fulfill(status=503), times=1)
    today.click()
    expect(page.get_by_text("Could not load pending reviews.", exact=True)).to_be_visible()
    expect(page.get_by_text("Overdue synthetic task", exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry pending reviews", exact=True).click()
    reviews = page.get_by_role("list", name="Pending reviews", exact=True)
    expect(reviews.get_by_text(title, exact=True)).to_be_visible()

    page.get_by_role("button", name="Open private inbox", exact=True).click()
    expect(reviews.get_by_text(title, exact=True)).to_have_count(0)
    page.get_by_role("button", name=title, exact=True).click()
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Dismiss suggestion", exact=True).click()
    expect(page.get_by_text("Suggestion dismissed.", exact=True)).to_be_visible()
    today.click()
    expect(page.get_by_text("No pending reviews.", exact=True)).to_be_visible()

    page.get_by_role("button", name="Work items", exact=True).click()
    page.evaluate(
        """path => {
            const actualFetch = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await actualFetch(url, options);
                if (url === path) setTimeout(() => { window.oldReviewsHandled = true; }, 0);
                return response;
            };
        }""",
        queue_url.removeprefix(origin),
    )
    held: list[Route] = []
    page.route(queue_url, lambda route: held.append(route), times=1)
    with page.expect_request(queue_url):
        today.click()
    second = create_workspace_in_browser(page, origin, "Other Today reviews workspace")
    expect(page.get_by_label("Workspace", exact=True)).to_have_value(second)
    expect(page.get_by_text("No pending reviews.", exact=True)).to_be_visible()
    assert len(held) == 1
    held[0].fulfill(status=401)
    page.wait_for_function("() => window.oldReviewsHandled === true")
    expect(page.get_by_text("No pending reviews.", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()


def test_workspace_browser_today_discards_pending_reviews_after_access_denial(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Workspace with private review")
    page.get_by_role("button", name="Private inbox", exact=True).click()
    title = "Private proposal title"
    capture_source_in_browser(page, "today-permission", title, "Synthetic excerpt")
    page.get_by_role("button", name=title, exact=True).click()
    page.get_by_role("button", name="Suggest task", exact=True).click()
    expect(page.get_by_role("button", name="Accept and create task", exact=True)).to_be_enabled()

    base = f"/api/v2/workspaces/{workspace_id}"
    path = base + "/proposals?limit=5"
    page.evaluate(
        """path => {
            const actualFetch = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await actualFetch(url, options);
                if (url === path) {
                    window.lateReviewTitle = (await response.clone().json())[0].title;
                    await new Promise(resolve => { window.releaseLateReview = resolve; });
                    const json = response.json.bind(response);
                    response.json = async () => {
                        const value = await json();
                        setTimeout(() => { window.lateReviewParsed = true; }, 0);
                        return value;
                    };
                }
                return response;
            };
        }""",
        path,
    )
    page.route(
        origin + base + "/work-due?limit=21", lambda route: route.fulfill(status=403), times=1
    )
    page.get_by_role("button", name="Today", exact=True).click()
    unavailable = page.get_by_text("Today is unavailable. Refresh your workspaces to try again.")
    expect(unavailable).to_be_visible()
    page.wait_for_function("() => typeof window.releaseLateReview === 'function'")
    assert page.evaluate("window.lateReviewTitle") == title
    page.evaluate("() => window.releaseLateReview()")
    page.wait_for_function("() => window.lateReviewParsed === true")
    expect(page.get_by_text(title, exact=True)).to_have_count(0)


def test_workspace_browser_today_uses_local_date_and_bounds_due_work(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Workspace for Today")
    path = f"/api/v2/workspaces/{workspace_id}/work-due?limit=21"
    seed_browser_work(page, workspace_id, ["Due tomorrow"], due_date="2030-01-03")
    seed_browser_work(page, workspace_id, ["Undated task"])
    titles = [f"Due today {index:02d}" for index in range(20)]
    seed_browser_work(page, workspace_id, titles, due_date="2030-01-02")
    cdp = context.new_cdp_session(page)
    cdp.send("Emulation.setTimezoneOverride", {"timezoneId": "America/Los_Angeles"})
    # The signed-in screen uses the local January 2 date even though UTC is January 3.
    page.clock.set_fixed_time(datetime(2030, 1, 3, 6, 30, tzinfo=UTC))

    today = page.get_by_role("button", name="Today", exact=True)
    all_work = page.get_by_role("button", name="Work items", exact=True)
    page.route(origin + path, lambda route: route.fulfill(status=503), times=1)
    today.click()
    expect(page.get_by_text("Could not load work items.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(today).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("heading", name="Today", exact=True)).to_be_visible()
    rows = page.get_by_role("listitem")
    expect(rows).to_have_count(20)
    expect(rows.filter(has_text=titles[0])).to_contain_text("Due today")
    expect(page.get_by_text("Due tomorrow", exact=True)).to_have_count(0)
    expect(page.get_by_text("Undated task", exact=True)).to_have_count(0)
    limit_message = page.get_by_text("Showing the 20 earliest tasks due by today.", exact=False)
    expect(limit_message).to_have_count(0)

    seed_browser_work(page, workspace_id, ["Oldest urgent task"], due_date="2030-01-01")
    all_work.click()
    today.click()
    urgent = rows.filter(has_text="Oldest urgent task")
    expect(rows.first).to_contain_text("Oldest urgent task")
    expect(urgent).to_contain_text("Overdue")
    expect(limit_message).to_be_visible()
    urgent.get_by_role("button", name="Start task", exact=True).click()
    urgent.get_by_role("button", name="Complete task", exact=True).click()
    expect(urgent).to_have_count(0)
    expect(rows).to_have_count(20)
    expect(limit_message).to_have_count(0)
    expect(page.get_by_text(titles[0], exact=True)).to_be_visible()


def test_workspace_browser_transition_refreshes_stale_task_and_hides_read_only_controls(
    login_browser,
):
    from playwright.sync_api import expect

    page, context, origin, provider, sign, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Task conflict workspace")
    title = "One versioned task"
    seed_browser_work(page, workspace_id, [title])
    page.reload()
    row = page.get_by_role("listitem").filter(has_text=title)
    expect(row).to_be_visible()
    path = f"/api/v2/workspaces/{workspace_id}/work-page"
    task = json.loads(fetch(page, path)["text"])["items"][0]
    session = json.loads(fetch(page, "/api/v2/session")["text"])
    assert session["can_write"] is True
    changed = fetch(
        page,
        f"/api/v2/workspaces/{workspace_id}/work/{task['id']}/transitions",
        method="POST",
        headers={"Content-Type": "application/json", "X-CSRF-Token": session["csrf_token"]},
        body=json.dumps({"target": "active", "expected_version": task["version"]}),
    )
    assert changed["status"] == 200
    start_task = row.get_by_role("button", name="Start task", exact=True)
    with page.expect_response("**/transitions") as conflict:
        start_task.click()
    assert conflict.value.status == 409
    expect(start_task).to_be_disabled()
    expect(page.get_by_label("Work view", exact=True)).to_be_enabled()
    expect(page.get_by_text("This task changed.", exact=False)).to_be_visible()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(row.get_by_role("button", name="Complete task", exact=True)).to_be_enabled()

    context.clear_cookies()
    page.goto(origin + "/api/v2/test-login-browser")
    exchanged = fetch(
        page,
        "/api/v2/session",
        method="POST",
        headers={"Authorization": f"Bearer {sign('new-browser-user', scope='flowpilot:read')}"},
    )
    assert exchanged["status"] == 201
    assert json.loads(exchanged["text"])["can_write"] is False
    page.goto(origin + "/api/v2/workspace")
    expect(row).to_contain_text("active")
    expect(row.get_by_role("button")).to_have_count(0)
    expect(page.get_by_role("button", name="New task", exact=True)).to_be_hidden()


def test_workspace_browser_ignores_late_transition_after_workspace_switch(login_browser):
    from playwright.sync_api import Route, expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First task workspace")
    seed_browser_work(page, first, ["Visible only in first workspace"])
    second = create_workspace_in_browser(page, origin, "Second task workspace")
    selector = page.get_by_label("Workspace", exact=True)
    expect(selector).to_have_value(second)
    selector.select_option(first)
    page.evaluate(
        """() => {
            const fetchOriginal = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await fetchOriginal(url, options);
                if (url.endsWith('/transitions')) {
                    setTimeout(() => { window.transitionHandled = true; }, 0);
                }
                return response;
            };
        }"""
    )
    held: list[Route] = []
    page.route("**/transitions", lambda route: held.append(route), times=1)
    with page.expect_request("**/transitions"):
        page.get_by_role("button", name="Start task", exact=True).click()
    selector.select_option(second)
    empty = page.get_by_text("No work items yet.", exact=True)
    expect(empty).to_be_visible()
    assert len(held) == 1
    held[0].fulfill(status=401, json={"detail": "Unauthorized"})
    page.wait_for_function("window.transitionHandled === true")
    expect(selector).to_have_value(second)
    expect(empty).to_be_visible()
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()


def test_workspace_browser_clears_visible_work_when_session_expires(login_browser, pg):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First synthetic workspace")
    title = "Previously visible private task"
    seed_browser_work(page, first, [title])
    second = create_workspace_in_browser(page, origin, "Second synthetic workspace")
    selector = page.get_by_label("Workspace", exact=True)
    expect(selector).to_have_value(second)
    selector.select_option(first)
    visible_work = page.get_by_text(title, exact=True)
    expect(visible_work).to_be_visible()

    with pg[0].begin() as connection:
        connection.execute(text("UPDATE browser_sessions SET expires_at=0"))
    with page.expect_response(origin + f"/api/v2/workspaces/{second}/work-page?**") as denied:
        selector.select_option(second)
    assert denied.value.status == 401
    expect(page.get_by_role("link", name="Sign in", exact=True)).to_be_visible()
    expect(visible_work).to_have_count(0)
    expect(page.get_by_role("textbox", name="Workspace name")).to_be_hidden()


@pytest.mark.parametrize("delayed_status", [200, 401])
def test_workspace_browser_ignores_late_work_from_previous_selection(login_browser, delayed_status):
    from playwright.sync_api import Route, expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First synthetic workspace")
    first_title = "Task from previous selection"
    seed_browser_work(page, first, [first_title])
    second = create_workspace_in_browser(page, origin, "Second synthetic workspace")
    selector = page.get_by_label("Workspace", exact=True)
    expect(selector).to_have_value(second)
    expect(page.get_by_text("No work items yet.", exact=True)).to_be_visible()
    second_title = "Task from current selection"
    seed_browser_work(page, second, [second_title])

    delayed_path = f"/api/v2/workspaces/{first}/work-page"
    # Signal in the next task so the app has processed the error or parsed work.
    page.evaluate(
        """path => {
            const fetchOriginal = window.fetch.bind(window);
            const signal = () => setTimeout(() => { window.delayedWorkHandled = true; }, 0);
            window.fetch = async (url, options) => {
                const response = await fetchOriginal(url, options);
                if (new URL(url, location.href).pathname !== path) return response;
                if (!response.ok) {
                    signal();
                    return response;
                }
                const json = response.json.bind(response);
                response.json = async () => {
                    const body = await json();
                    signal();
                    return body;
                };
                return response;
            };
        }""",
        delayed_path,
    )
    held: list[Route] = []
    delayed_url = origin + delayed_path + "?**"
    page.route(delayed_url, lambda route: held.append(route), times=1)
    with page.expect_request(delayed_url):
        selector.select_option(first)
    expect(page.get_by_text("Loading work items…", exact=True)).to_be_visible()

    selector.select_option(second)
    current_item = page.get_by_text(second_title, exact=True)
    expect(current_item).to_be_visible()
    assert len(held) == 1
    if delayed_status == 200:
        stale = held[0].fetch()
        assert stale.ok and stale.json()["items"][0]["data"]["title"] == first_title
        held[0].fulfill(response=stale)
    else:
        held[0].fulfill(status=401, json={"detail": "Unauthorized"})
    page.wait_for_function("window.delayedWorkHandled === true")
    expect(selector).to_have_value(second)
    expect(current_item).to_be_visible()
    expect(page.get_by_text(first_title, exact=True)).to_have_count(0)
