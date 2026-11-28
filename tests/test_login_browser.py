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
from zoneinfo import ZoneInfo

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
from flowpilot_api.membership_service import MembershipService, WorkspaceCreate
from flowpilot_api.work_service import Principal
from flowpilot_api.workspace_api import create_workspace_app
from sqlalchemy import text

pytestmark = [pytest.mark.browser, pytest.mark.postgres]


@pytest.fixture
def login_browser_headless():
    return True


@pytest.fixture
def login_browser(pg, tmp_path, login_browser_headless):
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
            browser = playwright.chromium.launch(headless=login_browser_headless)
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
    page.get_by_role("button", name="Work items", exact=True).click()
    page.get_by_label("New project name").fill("Earlier project")
    page.get_by_role("button", name="Create project", exact=True).click()
    expect(page.get_by_text("Project created.", exact=True)).to_be_visible()
    page.get_by_label("Task status", exact=True).select_option("completed")
    page.get_by_label("Priority filter", exact=True).select_option("high")
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
    for label in ("Task status", "Priority filter", "Project filter"):
        expect(page.get_by_label(label, exact=True)).to_have_value("")
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
@pytest.mark.parametrize("from_today", [False, True])
def test_workspace_browser_ignores_late_inbox_details_after_switch(
    login_browser, delayed_status, from_today
):
    from playwright.sync_api import Route, expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First inbox workspace")
    page.get_by_role("button", name="Private inbox", exact=True).click()
    name = "First workspace source summary"
    secret = "First workspace private excerpt"
    source_id = capture_source_in_browser(page, "first-source", name, secret)
    if from_today:
        page.get_by_role("button", name=name, exact=True).click()
        page.get_by_role("button", name="Suggest task", exact=True).click()
        expect(page.get_by_role("button", name="Accept and create task")).to_be_enabled()
    second = create_workspace_in_browser(page, origin, "Second inbox workspace")
    selector = page.get_by_label("Workspace", exact=True)
    selector.select_option(first)
    if from_today:
        page.get_by_role("button", name="Today", exact=True).click()
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
    expect(page.get_by_role("listitem")).to_have_count(20)
    expect(page.get_by_text(titles[0], exact=True)).to_have_count(0)
    more = page.get_by_role("button", name="Load more", exact=True)
    expect(more).to_be_visible()
    row.get_by_role("button", name="Edit task", exact=True).click()
    expect(work_view).to_be_disabled()
    expect(row.get_by_role("button", name="Start task", exact=True)).to_be_disabled()
    expect(more).to_have_js_property("inert", True)
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
        expect(more).to_have_js_property("inert", True)
        route.continue_()

    page.route("**/transitions", check_pending_update, times=1)
    started = click_status("Start task")
    assert started["data"]["status"] == "active" and started["version"] == 2
    blocked = click_status("Block task")
    assert blocked["data"]["status"] == "blocked" and blocked["version"] == 3
    resumed = click_status("Resume task")
    assert resumed["data"]["status"] == "active" and resumed["version"] == 4
    complete = row.get_by_role("button", name="Complete task", exact=True)
    expect(complete).to_be_enabled()

    def fail_pending_page(route: Route) -> None:
        expect(complete).to_be_disabled()
        expect(more).to_be_disabled()
        route.fulfill(status=503)

    page.route("**/work-due-page?limit=20&after=**", fail_pending_page, times=1)
    more.click()
    expect(
        page.get_by_text("Could not load more work items. Try again.", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("listitem")).to_have_count(20)
    expect(complete).to_be_enabled()
    more.click()
    expect(page.get_by_text(titles[0], exact=True)).to_be_visible()
    expect(page.get_by_role("listitem")).to_have_count(21)
    expect(more).to_be_hidden()

    page.route("**/work-due-page?limit=20", lambda route: route.fulfill(status=503), times=1)
    completed = click_status("Complete task")
    assert completed["data"]["status"] == "completed" and completed["version"] == 5
    expect(page.get_by_text("Could not load work items.", exact=True)).to_be_visible()
    expect(page.get_by_text("Task status updated.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(page.get_by_text(titles[0], exact=True)).to_be_visible()
    expect(row).to_have_count(0)
    expect(page.get_by_role("listitem")).to_have_count(20)
    expect(more).to_be_hidden()

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


def test_workspace_browser_creates_edits_and_archives_private_notes(login_browser):
    from playwright.sync_api import Route, expect

    page, context, origin, provider, sign, _ = login_browser
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Private notes workspace")
    path = f"/api/v2/workspaces/{workspace}/notes"
    notes = page.get_by_role("button", name="Notes", exact=True)
    notes.click()
    page.get_by_role("button", name="New note", exact=True).click()
    body = page.get_by_label("Note text", exact=True)
    save = page.get_by_role("button", name="Save note", exact=True)
    value = "<strong>Workshop ideas</strong>\nBring the agenda 🙂"
    body.fill(value)
    expect(page.get_by_role("button", name="Work items", exact=True)).to_be_disabled()
    selector = page.get_by_label("Workspace", exact=True)
    refresh_workspaces = page.get_by_role("button", name="Refresh workspaces", exact=True)
    create_workspace = page.get_by_role("button", name="Create workspace", exact=True)
    for control in (selector, refresh_workspaces, create_workspace):
        expect(control).to_be_disabled()
    with page.expect_response(origin + path) as created:
        save.click()
    assert created.value.status == 201 and created.value.json()["body"] == value
    note_id = created.value.json()["id"]
    cards = page.get_by_role("list", name="Private notes", exact=True)
    expect(cards.get_by_text("<strong>Workshop ideas</strong>", exact=False)).to_be_visible()
    expect(cards.locator("strong")).to_have_count(0)
    for control in (selector, refresh_workspaces, create_workspace):
        expect(control).to_be_enabled()

    ordinary = {"Content-Type": "application/json"}
    edit_url = path + "/" + note_id
    denied = fetch(
        page,
        edit_url,
        method="PATCH",
        headers=ordinary,
        body=json.dumps({"expected_version": 1, "body": "Invalid CSRF"}),
    )
    assert denied["status"] == 403
    page.get_by_role("button", name="Edit note", exact=True).click()
    expect(body).to_have_value(value)
    body.fill("Keep this draft visible")
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    saved_elsewhere = fetch(
        page,
        edit_url,
        method="PATCH",
        headers={**ordinary, "X-CSRF-Token": csrf},
        body=json.dumps({"expected_version": 1, "body": "Saved in another tab"}),
    )
    assert saved_elsewhere["status"] == 200
    with page.expect_response(origin + edit_url) as stale:
        save.click()
    assert stale.value.status == 409
    expect(page.get_by_text("This note changed.", exact=False)).to_be_visible()
    expect(body).to_have_value("Keep this draft visible")
    expect(save).to_be_disabled()
    page.get_by_role("button", name="Close note editor", exact=True).click()
    page.get_by_role("button", name="Refresh notes", exact=True).click()
    expect(cards.get_by_text("Saved in another tab", exact=True)).to_be_visible()
    page.get_by_role("button", name="Edit note", exact=True).click()
    body.fill("Final workshop note")
    save.click()
    expect(cards.get_by_text("Final workshop note", exact=True)).to_be_visible()

    page.get_by_role("button", name="Archive note", exact=True).click()
    expect(page.get_by_text("No notes yet.", exact=True)).to_be_visible()
    view = page.get_by_label("Note view", exact=True)
    view.select_option("archived")
    expect(cards.get_by_text("Final workshop note", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Edit note", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Restore note", exact=True).click()
    expect(page.get_by_text("No archived notes.", exact=True)).to_be_visible()

    view.select_option("active")
    page.get_by_role("button", name="New note", exact=True).click()
    uncertain = "Saved despite a dropped response"
    body.fill(uncertain)

    def lose_create_response(route: Route) -> None:
        persisted = route.fetch()
        assert persisted.status == 201
        route.fulfill(status=503)

    page.route(origin + path, lose_create_response, times=1)
    save.click()
    expect(page.get_by_text("Could not confirm the save.", exact=False)).to_be_visible()
    expect(body).to_have_value(uncertain)
    expect(save).to_be_disabled()
    page.get_by_role("button", name="Close note editor", exact=True).click()
    page.get_by_role("button", name="Refresh notes", exact=True).click()
    expect(cards.get_by_text(uncertain, exact=True)).to_have_count(1)

    context.clear_cookies()
    page.goto(origin + "/api/v2/test-login-browser")
    bearer = sign("new-browser-user", scope="flowpilot:read")
    auth = fetch(
        page, "/api/v2/session", method="POST", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert auth["status"] == 201
    page.goto(origin + "/api/v2/workspace")
    notes.click()
    expect(cards.get_by_text("Final workshop note", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="New note", exact=True)).to_be_hidden()
    expect(cards.get_by_role("button")).to_have_count(0)


def test_workspace_browser_discards_a_late_private_note_page(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First notes workspace")
    path = f"/api/v2/workspaces/{first}/notes"
    note = "Private note from the first workspace"
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    saved = fetch(
        page,
        path,
        method="POST",
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
        body=json.dumps({"body": note}),
    )
    assert saved["status"] == 201

    page.evaluate(
        """path => {
            const actualFetch = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await actualFetch(url, options);
                if (!url.startsWith(path + '?')) return response;
                await new Promise(resolve => { window.releaseOldNotes = resolve; });
                const json = response.json.bind(response);
                response.json = async () => {
                    const value = await json();
                    setTimeout(() => { window.oldNotesParsed = true; }, 0);
                    return value;
                };
                return response;
            };
        }""",
        path,
    )
    page.get_by_role("button", name="Notes", exact=True).click()
    page.wait_for_function("() => typeof window.releaseOldNotes === 'function'")
    second = create_workspace_in_browser(page, origin, "Second notes workspace")
    expect(page.get_by_label("Workspace", exact=True)).to_have_value(second)
    empty = page.get_by_text("No notes yet.", exact=True)
    expect(empty).to_be_visible()
    page.evaluate("() => window.releaseOldNotes()")
    page.wait_for_function("() => window.oldNotesParsed === true")
    expect(empty).to_be_visible()
    expect(page.get_by_text(note, exact=True)).to_have_count(0)


def test_workspace_browser_event_lifecycle_in_work_and_today(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, sign, _ = login_browser
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Manual event workshop")
    seed_browser_work(page, workspace, ["Task omitted from Events"])
    page.get_by_role("button", name="Today", exact=True).click()
    page.get_by_role("button", name="Open events", exact=True).click()
    expect(page.get_by_label("Work view", exact=True)).to_have_value("events")
    expect(page.get_by_text("No events yet.", exact=True)).to_be_visible()
    expect(page.get_by_text("Task omitted from Events", exact=True)).to_have_count(0)

    title = "<b>Manual workshop</b>"
    page.get_by_role("button", name="New event", exact=True).click()
    page.get_by_label("Event title", exact=True).fill(title)
    page.get_by_label("Event description", exact=True).fill("Bring the synthetic agenda.")
    zone = page.get_by_label("Time zone", exact=True)
    default_zone = page.evaluate("() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'")
    expect(zone).to_have_value(default_zone)
    zone.fill("America/New_York")
    start = page.get_by_label("Start date and time")
    end = page.get_by_label("End date and time")
    start.fill("2030-03-10T02:30")
    end.fill("2030-03-10T04:00")
    save = page.get_by_role("button", name="Create event", exact=True)
    save.click()
    expect(page.get_by_text("This local time does not exist", exact=False)).to_be_visible()
    expect(page.get_by_label("Event title", exact=True)).to_have_value(title)
    expect(page.get_by_label("Workspace", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Refresh workspaces", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Today", exact=True)).to_be_disabled()

    eastern = ZoneInfo("America/New_York")
    starts_at = (datetime.now(eastern) + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    ends_at = starts_at + timedelta(hours=1)
    local_format = "%Y-%m-%dT%H:%M"
    start.fill(starts_at.strftime(local_format))
    end.fill(ends_at.strftime(local_format))
    with page.expect_response("**/work-events") as created:
        save.click()
    assert created.value.status == 201
    record = created.value.json()
    assert record["visibility"] == "private"
    assert datetime.fromisoformat(record["data"]["starts_at"]) == starts_at
    expect(page.get_by_text("Event created.", exact=True)).to_be_visible()
    row = page.get_by_role("listitem").filter(has_text=title)
    expect(row.get_by_text(title, exact=True)).to_be_visible()
    expect(row).to_contain_text("Private")
    expect(row).to_contain_text("Bring the synthetic agenda.")
    today = page.get_by_role("button", name="Today", exact=True)
    today.click()
    upcoming = page.get_by_role("list", name="Upcoming events")
    expect(upcoming.get_by_text(title, exact=True)).to_be_visible()

    page.get_by_role("button", name="Open events", exact=True).click()
    # Simulate different zone rules in the browser while editing server-resolved times.
    page.evaluate("""() => {
        const original = Intl.DateTimeFormat.prototype.formatToParts;
        Intl.DateTimeFormat.prototype.formatToParts = function(date) {
            const shift = this.resolvedOptions().timeZone === 'America/New_York' ? 3600000 : 0;
            return original.call(this, new Date(+date - shift));
        };
    }""")
    row.get_by_role("button", name="Edit event", exact=True).click()
    expect(start).to_have_value(starts_at.strftime(local_format))
    revised_end = ends_at + timedelta(hours=1)
    end.fill(revised_end.strftime(local_format))
    changed_title = "Rescheduled workshop"
    page.get_by_label("Event title", exact=True).fill(changed_title)
    with page.expect_response("**/event-details") as edited:
        page.get_by_role("button", name="Save event changes", exact=True).click()
    assert edited.value.status == 200
    edited_data = edited.value.json()["data"]
    assert datetime.fromisoformat(edited_data["starts_at"]) == starts_at
    assert datetime.fromisoformat(edited_data["ends_at"]) == revised_end
    assert edited.value.request.post_data_json["schedule"]["starts_at"] is None
    expect(page.get_by_text("Event updated.", exact=True)).to_be_visible()
    revised = page.get_by_role("listitem").filter(has_text=changed_title)
    page.once("dialog", lambda dialog: dialog.accept())
    revised.get_by_role("button", name="Cancel event", exact=True).click()
    expect(page.get_by_text("Event canceled.", exact=True)).to_be_visible()
    expect(revised).to_contain_text("canceled")
    expect(revised.get_by_role("button")).to_have_count(0)
    today.click()
    expect(page.get_by_text("No events in the next seven days.", exact=True)).to_be_visible()

    context.clear_cookies()
    page.goto(origin + "/api/v2/test-login-browser")
    response = fetch(
        page,
        "/api/v2/session",
        method="POST",
        headers={"Authorization": f"Bearer {sign('new-browser-user', scope='flowpilot:read')}"},
    )
    assert response["status"] == 201
    page.goto(origin + "/api/v2/workspace")
    expect(page.get_by_label("Workspace", exact=True)).to_have_value(workspace)
    expect(revised).to_be_visible()
    expect(page.get_by_role("button", name="New event", exact=True)).to_be_hidden()


def test_workspace_browser_preserves_an_event_draft_after_stale_save(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Concurrent event workspace")
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    headers = {"Content-Type": "application/json", "X-CSRF-Token": csrf}
    base = f"/api/v2/workspaces/{workspace}"
    created = fetch(
        page,
        base + "/work-events",
        method="POST",
        headers=headers,
        body=json.dumps(
            {
                "title": "Original event",
                "schedule": {
                    "starts_at": "2030-06-15T09:30",
                    "ends_at": "2030-06-15T10:30",
                    "time_zone": "UTC",
                },
            }
        ),
    )
    assert created["status"] == 201
    path = base + "/work/" + json.loads(created["text"])["id"] + "/event-details"
    page.reload()
    page.get_by_role("button", name="Edit event", exact=True).click()
    title = page.get_by_label("Event title", exact=True)
    title.fill("My stale draft")
    changed = fetch(
        page,
        path,
        method="PATCH",
        headers=headers,
        body=json.dumps(
            {"expected_version": 1, "details": {"title": "Current event", "description": None}}
        ),
    )
    assert changed["status"] == 200
    save = page.get_by_role("button", name="Save event changes", exact=True)
    save.click()
    expect(page.get_by_text("This event changed.", exact=False)).to_be_visible()
    expect(title).to_have_value("My stale draft")
    expect(save).to_be_disabled()
    page.get_by_role("button", name="Close event editor", exact=True).click()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(page.get_by_text("Current event", exact=True)).to_be_visible()
    expect(page.get_by_text("My stale draft", exact=True)).to_have_count(0)


def test_in_app_reminders_retry_group_snooze_and_dismiss(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, _, _ = login_browser
    context.new_cdp_session(page).send("Emulation.setTimezoneOverride", {"timezoneId": "UTC"})
    noon = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    page.clock.install(time=noon - timedelta(days=1))
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Reminder workshop")
    day = page.evaluate("() => localDate()")
    seed_browser_work(page, workspace, ["<b>Due agenda</b>"], due_date=day)
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    headers = {"Content-Type": "application/json", "X-CSRF-Token": csrf}
    base = f"/api/v2/workspaces/{workspace}"
    starts_at = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=10)
    event = fetch(
        page,
        base + "/work",
        method="POST",
        headers=headers,
        body=json.dumps(
            {
                "item": {
                    "kind": "event",
                    "title": "Team rehearsal",
                    "time_zone": "UTC",
                    "starts_at": starts_at.isoformat(),
                    "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                }
            }
        ),
    )
    assert event["status"] == 201
    work_path = base + "/work/" + json.loads(event["text"])["id"]
    popup = page.get_by_role("complementary", name="Reminders")
    toggle = page.get_by_role("button", name="In-app reminders")
    expect(toggle).to_have_attribute("aria-pressed", "false")
    expect(popup).to_be_hidden()
    page.route(
        origin + base + "/reminders?local_date=" + day,
        lambda route: route.fulfill(status=503),
        times=1,
    )
    toggle.click()
    expect(page.get_by_text("Reminders could not refresh.", exact=False)).to_be_visible()
    page.clock.fast_forward(31_000)
    expect(popup.get_by_text("<b>Due agenda</b>", exact=True)).to_be_visible()
    expect(popup.get_by_text("Team rehearsal", exact=True)).to_be_visible()
    expect(popup.get_by_role("listitem")).to_have_count(2)

    popup.get_by_role("button", name="Snooze 5 minutes").click()
    expect(popup).to_be_hidden()
    page.clock.fast_forward(250_000)
    # Show the polling cycle actually completed while the group was snoozed.
    expect(page.get_by_text("Reminders snoozed for 5 minutes.", exact=True)).to_be_hidden()
    expect(popup).to_be_hidden()
    page.clock.fast_forward(60_000)
    expect(popup.get_by_text("Team rehearsal", exact=True)).to_be_visible()
    popup.get_by_role("button", name="Dismiss reminders").click()
    expect(popup).to_be_hidden()
    edited = fetch(
        page,
        work_path + "/event-details",
        method="PATCH",
        headers=headers,
        body=json.dumps(
            {
                "expected_version": 1,
                "details": {"title": "Renamed rehearsal", "description": None},
            }
        ),
    )
    assert edited["status"] == 200
    page.clock.fast_forward(31_000)
    expect(page.get_by_text("Reminders dismissed.", exact=True)).to_be_hidden()
    expect(popup).to_be_hidden()

    revised = starts_at + timedelta(minutes=1)
    rescheduled = fetch(
        page,
        work_path + "/event-details",
        method="PATCH",
        headers=headers,
        body=json.dumps(
            {
                "expected_version": 2,
                "details": {"title": "Renamed rehearsal", "description": None},
                "schedule": {
                    "time_zone": "UTC",
                    "starts_at": revised.replace(tzinfo=None).isoformat(),
                },
            }
        ),
    )
    assert rescheduled["status"] == 200
    page.clock.fast_forward(31_000)
    expect(popup.get_by_text("Renamed rehearsal", exact=True)).to_be_visible()
    expect(popup.get_by_role("listitem")).to_have_count(1)
    toggle.click()
    expect(popup).to_be_hidden()
    expect(toggle).to_have_attribute("aria-pressed", "false")


def test_in_app_reminders_expire_while_refresh_is_pending(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, _, _ = login_browser
    context.new_cdp_session(page).send("Emulation.setTimezoneOverride", {"timezoneId": "UTC"})
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    page.clock.install(time=midnight - timedelta(minutes=2))
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Reminder time boundaries")
    page.clock.pause_at(midnight - timedelta(seconds=20))
    day = page.evaluate("() => localDate()")
    url = origin + f"/api/v2/workspaces/{workspace}/reminders?local_date={day}"
    response = {
        "tasks": [{"title": "Previous-day task", "id": str(uuid4()), "due_date": day}],
        "events": [
            {
                "title": "About to start",
                "id": str(uuid4()),
                "starts_at": (midnight - timedelta(seconds=5)).isoformat(),
            }
        ],
        "has_more": False,
    }
    page.route(url, lambda route: route.fulfill(json=response), times=1)
    page.get_by_role("button", name="In-app reminders").click()
    popup = page.get_by_role("complementary", name="Reminders")
    expect(popup.get_by_role("listitem")).to_have_count(2)

    held = []
    page.route(url, lambda route: held.append(route), times=1)
    with page.expect_request(url):
        page.clock.run_for(15_000)
    expect(popup.get_by_text("About to start", exact=True)).to_have_count(0)
    expect(popup.get_by_text("Previous-day task", exact=True)).to_be_visible()
    page.clock.run_for(5_000)
    expect(popup).to_be_hidden()
    expect(popup.get_by_role("listitem")).to_have_count(0)
    assert len(held) == 1
    held[0].fulfill(json=response)
    page.clock.run_for(5)
    expect(popup).to_be_hidden()


def test_in_app_reminders_ignore_old_workspace_and_replaced_session(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, sign, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First reminder workspace")
    day = page.evaluate("() => localDate()")
    seed_browser_work(page, first, ["Private first reminder"], due_date=day)
    second = create_workspace_in_browser(page, origin, "Second reminder workspace")
    seed_browser_work(page, second, ["Private second reminder"], due_date=day)
    pick = page.get_by_label("Workspace", exact=True)
    pick.select_option(first)
    popup = page.get_by_role("complementary", name="Reminders")
    toggle = page.get_by_role("button", name="In-app reminders")
    first_url = f"/api/v2/workspaces/{first}/reminders?local_date={day}"
    page.evaluate(
        """url => {
        const original = window.fetch.bind(window);
        window.fetch = async (path, options) => {
            const response = await original(path, options);
            if (path !== url) return response;
            const originalBody = await response.text();
            await new Promise(resolve => { window.releaseReminder = resolve; });
            const replacement = new Response(originalBody, { status: response.status });
            const parse = replacement.json.bind(replacement);
            replacement.json = async () => {
                const value = await parse();
                setTimeout(() => { window.reminderParsed = true; }, 0);
                return value;
            };
            return replacement;
        };
    }""",
        first_url,
    )
    toggle.click()
    page.wait_for_function("() => typeof window.releaseReminder === 'function'")
    pick.select_option(second)
    expect(toggle).to_have_attribute("aria-pressed", "false")
    page.evaluate("() => window.releaseReminder()")
    page.wait_for_function("() => window.reminderParsed === true")
    expect(popup).to_be_hidden()
    toggle.click()
    expect(popup.get_by_text("Private second reminder", exact=True)).to_be_visible()
    expect(popup.get_by_text("Private first reminder", exact=True)).to_have_count(0)

    old_token = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    context.clear_cookies()
    renewed = fetch(
        page,
        "/api/v2/session",
        method="POST",
        headers={
            "Authorization": f"Bearer {sign('new-browser-user')}",
        },
    )
    assert renewed["status"] == 201
    second_url = f"/api/v2/workspaces/{second}/reminders?local_date={day}"
    assert fetch(page, second_url, headers={"X-CSRF-Token": old_token})["status"] == 401
    assert fetch(page, second_url)["status"] == 401
    new_token = json.loads(renewed["text"])["csrf_token"]
    assert fetch(page, second_url, headers={"X-CSRF-Token": new_token})["status"] == 200
    toggle.click()
    toggle.click()
    expect(page.get_by_text("Your session is unavailable.", exact=False)).to_be_visible()
    expect(popup).to_be_hidden()
    expect(popup.get_by_role("listitem")).to_have_count(0)


def test_reminder_settings_scope_lead_time_and_future_snoozes(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, _, _ = login_browser
    context.new_cdp_session(page).send("Emulation.setTimezoneOverride", {"timezoneId": "UTC"})
    noon = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    page.clock.install(time=noon - timedelta(days=1))
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "A custom reminders")
    second = create_workspace_in_browser(page, origin, "B default reminders")
    select = page.get_by_label("Workspace", exact=True)
    select.select_option(first)
    day = page.evaluate("() => localDate()")
    seed_browser_work(page, first, ["Due but filtered"], due_date=day)
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    base = f"/api/v2/workspaces/{first}"
    starts = datetime.now(UTC) + timedelta(minutes=20)
    saved = fetch(
        page,
        base + "/work",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf,
        },
        body=json.dumps(
            {
                "item": {
                    "title": "Workshop in 20 minutes",
                    "kind": "event",
                    "time_zone": "UTC",
                    "starts_at": starts.isoformat(),
                    "ends_at": (starts + timedelta(hours=1)).isoformat(),
                }
            }
        ),
    )
    assert saved["status"] == 201

    toggle = page.get_by_role("button", name="In-app reminders")
    settings = page.get_by_text("Reminder settings", exact=True)
    category = page.get_by_label("Remind me about")
    lead = page.get_by_label("Before an event starts")
    duration = page.get_by_label("Snooze for")
    popup = page.get_by_role("complementary", name="Reminders")
    requests = []
    page.on(
        "request",
        lambda outgoing: requests.append(outgoing.url) if "/reminders?" in outgoing.url else None,
    )
    settings.click()
    category.select_option("tasks")
    expect(lead).to_be_disabled()
    category.select_option("events")
    lead.select_option("30")
    duration.select_option("15")
    expect(toggle).to_have_attribute("aria-pressed", "false")
    assert requests == []
    expected_query = (
        f"{origin}{base}/reminders?local_date={day}&category=events&event_lead_minutes=30"
    )
    with page.expect_response(expected_query) as initial:
        toggle.click()
    assert initial.value.status == 200
    event = popup.get_by_text("Workshop in 20 minutes", exact=True)
    expect(event).to_be_visible()
    expect(popup.get_by_text("Due but filtered", exact=True)).to_have_count(0)
    popup.get_by_role("button", name="Snooze 15 minutes").click()
    duration.select_option("5")
    with page.expect_response(expected_query):
        page.clock.fast_forward(600_000)
    expect(event).to_have_count(0)
    with page.expect_response(expected_query):
        page.clock.fast_forward(301_000)
    expect(event).to_be_visible()
    expect(popup.get_by_role("button", name="Snooze 5 minutes")).to_be_visible()

    select.select_option(second)
    expect(toggle).to_have_attribute("aria-pressed", "false")
    settings.click()
    expect(category).to_have_value("both")
    expect(lead).to_have_value("15")
    select.select_option(first)
    expect(toggle).to_have_attribute("aria-pressed", "true")
    settings.click()
    expect(category).to_have_value("events")
    expect(lead).to_have_value("30")
    expect(event).to_be_visible()
    page.reload()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    settings.click()
    expect(category).to_have_value("both")
    expect(lead).to_have_value("15")


def test_reminder_settings_ignore_superseded_results_and_auth_errors(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Reminder settings race")
    day = page.evaluate("() => localDate()")
    seed_browser_work(page, workspace, ["Active due task"], due_date=day)
    page.evaluate("""() => {
        const original = window.fetch.bind(window);
        let delays = 0;
        window.fetch = async (url, options) => {
            const response = await original(url, options);
            if (!url.includes('/reminders?') || url.includes('category=tasks')) return response;
            const body = await response.text();
            const number = ++delays;
            await new Promise(resolve => { window.releaseObsolete = resolve; });
            setTimeout(() => { window.obsoleteProcessed = number; }, 0);
            return number === 1 ? new Response(JSON.stringify({
                ...JSON.parse(body), events: [{id: 'obsolete', title: 'Stale category event',
                    starts_at: new Date(Date.now() + 60000).toISOString()}],
            }), {status: 200}) : new Response(null, {status: 401});
        };
    }""")
    settings = page.get_by_text("Reminder settings", exact=True)
    category = page.get_by_label("Remind me about")
    popup = page.get_by_role("complementary", name="Reminders")
    toggle = page.get_by_role("button", name="In-app reminders")
    settings.click()
    toggle.click()
    for number in (1, 2):
        page.wait_for_function("() => typeof window.releaseObsolete === 'function'")
        category.select_option("tasks")
        expect(popup.get_by_text("Active due task", exact=True)).to_be_visible()
        page.evaluate("() => { window.releaseObsolete(); delete window.releaseObsolete; }")
        page.wait_for_function("number => window.obsoleteProcessed === number", arg=number)
        expect(popup.get_by_text("Stale category event", exact=True)).to_have_count(0)
        expect(popup.get_by_text("Active due task", exact=True)).to_be_visible()
        expect(toggle).to_have_attribute("aria-pressed", "true")
        if number == 1:
            category.select_option("events")


def test_workspace_browser_today_events_render_retry_and_clear_on_workspace_change(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Workspace for Today events")
    base = f"/api/v2/workspaces/{workspace_id}"
    path = base + "/work-events?limit=5"
    seed_browser_work(page, workspace_id, ["Overdue next to events"], due_date="2020-01-02")
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    now = datetime.now(UTC).replace(microsecond=0)
    zone = "America/New_York"
    title = "<strong>Planning session</strong>"
    starts_at = now - timedelta(hours=1)
    ends_at = now + timedelta(hours=1)
    for index in range(6):
        event = {
            "kind": "event",
            "title": title if not index else f"Later synthetic event {index}",
            "starts_at": (starts_at + timedelta(hours=2 * index)).isoformat(),
            "ends_at": (ends_at + timedelta(hours=2 * index)).isoformat(),
            "time_zone": zone,
        }
        saved = fetch(
            page,
            base + "/work",
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
            body=json.dumps({"item": event}),
        )
        assert saved["status"] == 201

    page.get_by_role("button", name="Private inbox", exact=True).click()
    pending_title = "Review the synthetic agenda"
    capture_source_in_browser(page, "events-agenda", pending_title, "Synthetic agenda excerpt")
    page.get_by_role("button", name=pending_title, exact=True).click()
    page.get_by_role("button", name="Suggest task", exact=True).click()
    expect(page.get_by_role("button", name="Accept and create task", exact=True)).to_be_enabled()

    today = page.get_by_role("button", name="Today", exact=True)
    work = page.get_by_role("button", name="Work items", exact=True)
    page.route(origin + path, lambda route: route.fulfill(status=503), times=1)
    today.click()
    expect(page.get_by_text("Could not load upcoming events.", exact=True)).to_be_visible()
    expect(page.get_by_text("Overdue next to events", exact=True)).to_be_visible()
    expect(page.get_by_text(pending_title, exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry upcoming events", exact=True).click()
    events = page.get_by_role("list", name="Upcoming events", exact=True)
    rows = events.get_by_role("listitem")
    expect(rows).to_have_count(5)
    expect(rows.first.get_by_text(title, exact=True)).to_be_visible()
    expect(page.get_by_text("Showing the five earliest events.", exact=True)).to_be_visible()
    timestamps = rows.first.locator("time")
    assert datetime.fromisoformat(timestamps.nth(0).get_attribute("datetime")) == starts_at
    assert datetime.fromisoformat(timestamps.nth(1).get_attribute("datetime")) == ends_at
    zone_label = page.evaluate(
        """({ value, zone }) => new Intl.DateTimeFormat(undefined, {
            hour: 'numeric', timeZone: zone, timeZoneName: 'short'
        }).formatToParts(new Date(value)).find(part => part.type === 'timeZoneName').value""",
        {"value": starts_at.isoformat(), "zone": zone},
    )
    expect(timestamps.first).to_contain_text(zone_label)

    work.click()
    page.route(origin + path, lambda route: route.fulfill(status=403), times=1)
    today.click()
    expect(page.get_by_text("Today is unavailable.", exact=False)).to_be_visible()
    expect(page.get_by_text("Overdue next to events", exact=True)).to_have_count(0)
    expect(page.get_by_text(pending_title, exact=True)).to_have_count(0)
    expect(rows).to_have_count(0)

    utc_label = page.evaluate(
        """({ value, zone }) => {
            const OriginalFormatter = Intl.DateTimeFormat;
            Intl.DateTimeFormat = function(locale, options) {
                if (options?.timeZone === zone) throw new RangeError('Unsupported test time zone');
                return new OriginalFormatter(locale, options);
            };
            window.restoreEventFormatter = () => { Intl.DateTimeFormat = OriginalFormatter; };
            return new OriginalFormatter(undefined, {
                hour: 'numeric', timeZone: 'UTC', timeZoneName: 'short'
            }).formatToParts(new Date(value)).find(part => part.type === 'timeZoneName').value;
        }""",
        {"value": starts_at.isoformat(), "zone": zone},
    )
    page.get_by_role("button", name="Refresh workspaces", exact=True).click()
    expect(rows.first.get_by_text(title, exact=True)).to_be_visible()
    expect(timestamps.first).to_contain_text(utc_label)
    page.evaluate("() => window.restoreEventFormatter()")

    work.click()
    page.evaluate(
        """path => {
            const actualFetch = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await actualFetch(url, options);
                if (url !== path) return response;
                await new Promise(resolve => { window.releaseOldEvents = resolve; });
                const json = response.json.bind(response);
                response.json = async () => {
                    const value = await json();
                    setTimeout(() => { window.oldEventsParsed = true; }, 0);
                    return value;
                };
                return response;
            };
        }""",
        path,
    )
    today.click()
    page.wait_for_function("() => typeof window.releaseOldEvents === 'function'")
    second = create_workspace_in_browser(page, origin, "Workspace without events")
    expect(page.get_by_label("Workspace", exact=True)).to_have_value(second)
    empty = page.get_by_text("No events in the next seven days.", exact=True)
    expect(empty).to_be_visible()
    page.evaluate("() => window.releaseOldEvents()")
    page.wait_for_function("() => window.oldEventsParsed === true")
    expect(empty).to_be_visible()
    expect(rows).to_have_count(0)


def test_workspace_browser_schedule_pages_reloads_and_scopes_events(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Schedule workshop")
    base = f"/api/v2/workspaces/{workspace_id}"
    session = fetch(page, "/api/v2/session")
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": json.loads(session["text"])["csrf_token"],
    }
    now = datetime.now(UTC).replace(microsecond=0)
    pivot = None
    first_event = None
    for day in range(21, 0, -1):
        start = now + timedelta(days=day)
        saved = fetch(
            page,
            base + "/work",
            method="POST",
            headers=headers,
            body=json.dumps(
                {
                    "item": {
                        "kind": "event",
                        "title": f"Planning day {day:02}",
                        "starts_at": start.isoformat(),
                        "ends_at": (start + timedelta(hours=1)).isoformat(),
                        "time_zone": "UTC",
                    },
                }
            ),
        )
        assert saved["status"] == 201
        if day == 20:
            pivot = json.loads(saved["text"])["id"]
        if day == 1:
            first_event = json.loads(saved["text"])["id"]

    seed_browser_work(page, workspace_id, ["Workshop deadline"], due_date="2099-01-02")

    page.get_by_role("button", name="Today", exact=True).click()
    expect(
        page.get_by_role("list", name="Upcoming events", exact=True).get_by_role("listitem")
    ).to_have_count(5)
    page.get_by_role("button", name="Open schedule", exact=True).click()
    expect(page.get_by_label("Work view", exact=True)).to_have_value("schedule")
    expect(page.get_by_label("Search work titles", exact=True)).to_be_hidden()
    expect(page.get_by_role("button", name="New task", exact=True)).to_be_hidden()
    expect(page.get_by_role("button", name="New event", exact=True)).to_be_visible()
    rows = page.locator("#work-items > li")
    expect(rows.locator("strong")).to_have_text([f"Planning day {day:02}" for day in range(1, 21)])
    more = page.get_by_role("button", name="Load more", exact=True)
    changed = fetch(
        page,
        base + f"/work/{pivot}/event-details",
        method="PATCH",
        headers=headers,
        body=json.dumps(
            {
                "details": {"title": "Updated planning day 20", "description": None},
                "expected_version": 1,
            }
        ),
    )
    assert changed["status"] == 200, changed["text"]
    more.click()
    expect(
        page.get_by_text("The schedule changed. Retry to start from the first page.")
    ).to_be_visible()
    expect(rows).to_have_count(0)
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(rows.last.get_by_text("Updated planning day 20", exact=True)).to_be_visible()
    moved_start = (now + timedelta(days=20, hours=1)).replace(tzinfo=None)
    moved = fetch(
        page,
        base + f"/work/{first_event}/event-details",
        method="PATCH",
        headers=headers,
        body=json.dumps(
            {
                "details": {"title": "Planning day 01", "description": None},
                "expected_version": 1,
                "schedule": {
                    "starts_at": moved_start.isoformat(),
                    "ends_at": (moved_start + timedelta(hours=1)).isoformat(),
                    "time_zone": "UTC",
                },
            }
        ),
    )
    assert moved["status"] == 200, moved["text"]
    more.click()
    expect(
        page.get_by_text("The schedule changed. Retry to start from the first page.")
    ).to_be_visible()
    expect(rows).to_have_count(0)
    expect(more).to_be_hidden()
    expect(page.get_by_text("Workshop deadline", exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(rows.last).to_contain_text("Planning day 01")
    more.click()
    expect(rows.last.get_by_text("Planning day 21", exact=True)).to_be_visible()
    expect(rows).to_have_count(21)
    expect(rows.get_by_text("Planning day 01", exact=True)).to_have_count(1)
    expect(more).to_be_hidden()
    assert datetime.fromisoformat(
        rows.last.locator("time").first.get_attribute("datetime")
    ) == now + timedelta(days=21)

    rows.last.get_by_role("button", name="Edit event", exact=True).click()
    expect(page.get_by_label("Event title", exact=True)).to_have_value("Planning day 21")
    page.get_by_role("button", name="Close event editor", exact=True).click()
    page.once("dialog", lambda dialog: dialog.accept())
    rows.last.get_by_role("button", name="Cancel event", exact=True).click()
    expect(page.get_by_text("Event canceled.", exact=True)).to_be_visible()
    expect(rows).to_have_count(20)
    expect(more).to_be_hidden()
    page.get_by_label("Work view", exact=True).select_option("events")
    expect(rows.first.get_by_text("Planning day 01", exact=True)).to_be_visible()
    more.click()
    expect(rows.last.get_by_text("Planning day 21", exact=True)).to_be_visible()
    expect(rows.last).to_contain_text("canceled")

    page.evaluate(
        """path => {
            const originalFetch = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await originalFetch(url, options);
                if (url !== path) return response;
                await new Promise(resolve => { window.releaseOldSchedule = resolve; });
                const json = response.json.bind(response);
                response.json = async () => {
                    const value = await json();
                    setTimeout(() => { window.oldScheduleParsed = true; }, 0);
                    return value;
                };
                return response;
            };
        }""",
        base + "/work-schedule?limit=20",
    )
    page.get_by_label("Work view", exact=True).select_option("schedule")
    page.wait_for_function("() => typeof window.releaseOldSchedule === 'function'")
    second = create_workspace_in_browser(page, origin, "Workspace without a schedule")
    expect(page.get_by_label("Workspace", exact=True)).to_have_value(second)
    expect(page.get_by_text("No ongoing or upcoming events.", exact=True)).to_be_visible()
    page.evaluate("() => window.releaseOldSchedule()")
    page.wait_for_function("() => window.oldScheduleParsed === true")
    expect(rows).to_have_count(0)


@pytest.mark.parametrize("action", ["Start task", "Edit task"])
def test_today_clears_all_lists_on_denied_task_write(login_browser, action):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Today task permissions")
    seed_browser_work(page, workspace_id, ["Due task"], due_date="2020-01-01")
    base = f"/api/v2/workspaces/{workspace_id}"
    page.route(
        origin + base + "/proposals?limit=5",
        lambda route: route.fulfill(json=[{"title": "Pending review"}]),
    )
    page.evaluate(
        """path => {
            const original = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                if (url !== path) return original(url, options);
                await new Promise(resolve => { window.releaseEvents = resolve; });
                return {ok: true, json: async () => {
                    setTimeout(() => { window.eventsHandled = true; }, 0);
                    return {items: [], has_more: false};
                }};
            };
        }""",
        base + "/work-events?limit=5",
    )
    page.get_by_role("button", name="Today", exact=True).click()
    pending = page.get_by_text("Pending review", exact=True)
    expect(pending).to_be_visible()
    page.wait_for_function("() => typeof window.releaseEvents === 'function'")
    suffix = "task-details" if action == "Edit task" else "transitions"
    page.route(origin + base + "/work/*/" + suffix, lambda route: route.fulfill(status=403))
    page.get_by_role("button", name=action, exact=True).click()
    if action == "Edit task":
        page.get_by_label("Task title", exact=True).fill("Updated task")
        page.get_by_role("button", name="Save changes", exact=True).click()

    expect(page.get_by_text("Today is unavailable.", exact=False)).to_be_visible()
    expect(page.get_by_text("Due task", exact=True)).to_have_count(0)
    expect(pending).to_have_count(0)
    page.evaluate("() => window.releaseEvents()")
    page.wait_for_function("() => window.eventsHandled === true")
    expect(page.locator("#today-events-status")).to_be_empty()
    page.get_by_role("button", name="Work items", exact=True).click()
    expect(page.get_by_text("Due task", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Edit task", exact=True)).to_have_count(0)


@pytest.mark.parametrize("action", ["Start task", "Edit task", "Create project"])
def test_work_clears_cached_project_names_on_denied_write(login_browser, action):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Work permissions")
    seed_browser_work(page, workspace_id, ["Existing task"])
    project_name = page.get_by_label("New project name", exact=True)
    project_name.fill("Existing group")
    page.get_by_role("button", name="Create project", exact=True).click()
    project_filter = page.get_by_label("Project filter", exact=True)
    expect(project_filter.get_by_role("option", name="Existing group")).to_have_count(1)
    project_filter.select_option("")
    expect(page.get_by_text("Existing task", exact=True)).to_be_visible()
    base = origin + f"/api/v2/workspaces/{workspace_id}"
    if action == "Create project":
        page.route(base + "/projects", lambda route: route.fulfill(status=403), times=1)
        project_name.fill("Second group")
    else:
        suffix = "task-details" if action == "Edit task" else "transitions"
        page.route(base + "/work/*/" + suffix, lambda route: route.fulfill(status=403))
    page.get_by_role("button", name=action, exact=True).click()
    if action == "Edit task":
        page.get_by_label("Task title", exact=True).fill("Updated title")
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_text("You no longer have permission", exact=False)).to_be_visible()
    expect(page.get_by_text("Existing task", exact=True)).to_have_count(0)
    expect(project_filter.get_by_role("option")).to_have_count(1)
    expect(project_filter).to_be_disabled()
    expect(page.get_by_role("button", name="Create project", exact=True)).to_have_count(0)


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


def test_workspace_browser_opens_exact_review_from_today(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Direct review workspace")
    base = f"/api/v2/workspaces/{workspace_id}"
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    headers = {"X-CSRF-Token": csrf, "Content-Type": "application/json"}
    title = "<b>Confirm the venue</b>"
    suggestions = []
    for index in range(21):
        summary = title if index in (0, 20) else f"Other source {index}"
        source = fetch(
            page,
            base + "/sources",
            method="POST",
            headers=headers,
            body=json.dumps(
                {"reference": f"venue-{index}", "summary": summary, "excerpt": f"Evidence {index}"}
            ),
        )
        assert source["status"] == 201
        if summary == title:
            source_id = json.loads(source["text"])["id"]
            result = fetch(
                page, base + f"/sources/{source_id}/task-proposal", method="PUT", headers=headers
            )
            assert result["status"] == 200
            suggestions.append(json.loads(result["text"]))

    page.get_by_role("button", name="Work items", exact=True).click()
    page.get_by_role("button", name="Today", exact=True).click()
    reviews = page.get_by_role("list", name="Pending reviews").get_by_role(
        "button", name=title, exact=True
    )
    expect(reviews).to_have_count(2)
    older = suggestions[0]
    proposal_path = base + f"/proposals/{older['id']}"
    resolved = fetch(
        page,
        proposal_path + "/review",
        method="POST",
        headers=headers,
        body=json.dumps({"decision": "dismiss", "expected_version": older["version"]}),
    )
    assert resolved["status"] == 200
    requests = []
    page.on("request", lambda request: requests.append((request.method, request.url)))
    page.route(origin + proposal_path, lambda route: route.fulfill(status=503), times=1)
    reviews.last.click()
    expect(page.get_by_text("Could not load source details.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Reload source details", exact=True).click()
    expect(page.get_by_text("Evidence 0", exact=True)).to_be_visible()
    expect(page.locator("#proposal-state")).to_have_text("Dismissed")
    expect(page.get_by_role("button", name="Accept and create task", exact=True)).to_be_hidden()
    rows = page.get_by_role("list", name="Sources").get_by_role("listitem")
    expect(rows.filter(has_text=title)).to_have_count(1)
    expect(rows.filter(has_text=title)).to_contain_text("Pending review")
    page.get_by_role("button", name="Load more sources", exact=True).click()
    expect(rows.filter(has_text=title).last).to_contain_text("Dismissed")
    page.get_by_role("button", name="Close source details", exact=True).click()
    expect(rows.filter(has_text=title).last.get_by_role("button")).to_be_focused()
    assert {method for method, url in requests if origin + base in url} == {"GET"}

    page.get_by_role("button", name="Today", exact=True).click()
    expect(reviews).to_have_count(1)
    requests.clear()
    page.route(
        origin + base + "/sources?limit=20", lambda route: route.fulfill(status=403), times=1
    )
    reviews.click()
    expect(page.get_by_text("Inbox access changed.", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Source details")).to_be_hidden()
    assert not any(origin + base + "/sources/" in url for _, url in requests)


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


def test_workspace_browser_schedule_deadlines_use_local_day_and_clear_on_access_loss(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Schedule deadlines")
    cdp = context.new_cdp_session(page)
    cdp.send("Emulation.setTimezoneOverride", {"timezoneId": "America/Los_Angeles"})
    page.clock.set_fixed_time(datetime(2030, 1, 3, 6, 30, tzinfo=UTC))
    seed_browser_work(page, workspace_id, ["Overdue from yesterday"], due_date="2030-01-01")
    seed_browser_work(page, workspace_id, ["<b>Due today</b>"], due_date="2030-01-02")
    for day in range(3, 8):
        seed_browser_work(page, workspace_id, [f"Future task {day}"], due_date=f"2030-01-{day:02}")

    base = f"/api/v2/workspaces/{workspace_id}"
    session = fetch(page, "/api/v2/session")
    start = datetime.now(UTC) + timedelta(days=10)
    saved = fetch(
        page,
        base + "/work",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": json.loads(session["text"])["csrf_token"],
        },
        body=json.dumps(
            {
                "item": {
                    "kind": "event",
                    "title": "Workshop meeting",
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(hours=1)).isoformat(),
                    "time_zone": "UTC",
                }
            }
        ),
    )
    assert saved["status"] == 201

    deadline_path = base + "/work-due-page?limit=5&from_date=2030-01-02"
    work_view = page.get_by_label("Work view", exact=True)
    event_title = page.get_by_text("Workshop meeting", exact=True)
    deadlines = page.get_by_role("list", name="Task deadlines", exact=True)
    page.route(origin + deadline_path, lambda route: route.fulfill(status=503), times=1)
    work_view.select_option("schedule")
    expect(event_title).to_be_visible()
    expect(page.get_by_text("Could not load deadlines.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry deadlines", exact=True).click()
    expect(deadlines.locator("strong")).to_have_text(
        ["<b>Due today</b>", "Future task 3", "Future task 4", "Future task 5", "Future task 6"]
    )
    expect(deadlines.locator("b")).to_have_count(0)
    expect(deadlines.locator("time").first).to_have_attribute("datetime", "2030-01-02")
    more_deadlines = page.get_by_role("button", name="Load more deadlines", exact=True)
    expect(more_deadlines).to_be_visible()
    page.route(
        origin + deadline_path + "&after=**", lambda route: route.fulfill(status=503), times=1
    )
    more_deadlines.click()
    expect(page.get_by_text("Could not load more deadlines. Try again.")).to_be_visible()
    expect(deadlines.get_by_role("listitem")).to_have_count(5)
    more_deadlines.click()
    expect(deadlines.get_by_text("Future task 7", exact=True)).to_be_visible()
    expect(more_deadlines).to_be_hidden()
    from_date = page.get_by_label("Show deadlines from", exact=True)
    expect(from_date).to_have_value("2030-01-02")
    from_date.fill("2030-01-01")
    page.get_by_role("button", name="Show deadlines", exact=True).click()
    expect(deadlines.locator("strong").first).to_have_text("Overdue from yesterday")
    current = fetch(page, base + "/work-due-page?limit=1&from_date=2030-01-01")
    assert current["status"] == 200
    task = json.loads(current["text"])["items"][0]
    moved = fetch(
        page,
        base + f"/work/{task['id']}/task-details",
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": json.loads(session["text"])["csrf_token"],
        },
        body=json.dumps(
            {
                "expected_version": task["version"],
                "details": {
                    "title": task["data"]["title"],
                    "description": None,
                    "due_date": "2030-01-05",
                },
            }
        ),
    )
    assert moved["status"] == 200, moved["text"]
    more_deadlines.click()
    expect(
        page.get_by_text("The deadline list changed. Retry to start from the first page.")
    ).to_be_visible()
    expect(deadlines.get_by_role("listitem")).to_have_count(0)
    expect(more_deadlines).to_be_hidden()
    expect(event_title).to_be_visible()
    expect(from_date).to_have_value("2030-01-01")
    page.get_by_role("button", name="Retry deadlines", exact=True).click()
    more_deadlines.click()
    expect(deadlines.locator("strong")).to_have_text(
        [
            "<b>Due today</b>",
            "Future task 3",
            "Future task 4",
            "Future task 5",
            "Overdue from yesterday",
            "Future task 6",
            "Future task 7",
        ]
    )
    from_date.fill("2030-01-06")
    page.get_by_role("button", name="Show deadlines", exact=True).click()
    expect(deadlines.locator("strong")).to_have_text(["Future task 6", "Future task 7"])
    expect(event_title).to_be_visible()

    page.route(
        origin + base + "/work/*/transitions", lambda route: route.fulfill(status=403), times=1
    )
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Cancel event", exact=True).click()
    expect(page.get_by_text("Schedule is unavailable.", exact=False)).to_be_visible()
    expect(deadlines).to_be_hidden()
    expect(event_title).to_have_count(0)
    page.get_by_role("button", name="Refresh workspaces", exact=True).click()
    expect(event_title).to_be_visible()
    expect(deadlines.get_by_text("<b>Due today</b>", exact=True)).to_be_visible()

    from_date.fill("2030-01-06")
    page.get_by_role("button", name="Show deadlines", exact=True).click()
    expect(deadlines.locator("strong")).to_have_text(["Future task 6", "Future task 7"])
    from_date.fill("2030-01-07")
    page.get_by_role("button", name="Open due tasks", exact=True).click()
    expect(work_view).to_have_value("due")
    expect(deadlines).to_be_hidden()
    expect(page.get_by_label("Show due tasks from", exact=True)).to_have_value("2030-01-06")
    expect(page.get_by_text("Future task 6", exact=True)).to_be_visible()
    expect(page.get_by_text("Overdue from yesterday", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Clear due date filter", exact=True).click()
    expect(page.get_by_text("Overdue from yesterday", exact=True)).to_be_visible()

    page.evaluate(
        """path => {
            const originalFetch = window.fetch.bind(window);
            window.fetch = async (url, options) => {
                const response = await originalFetch(url, options);
                if (url !== path) return response;
                await new Promise(resolve => { window.releaseDeadlineResponse = resolve; });
                setTimeout(() => { window.deadlineReleased = true; }, 0);
                return response;
            };
        }""",
        deadline_path,
    )
    page.route(origin + deadline_path, lambda route: route.fulfill(status=403), times=2)
    work_view.select_option("schedule")
    page.wait_for_function("() => typeof window.releaseDeadlineResponse === 'function'")
    expect(event_title).to_be_visible()
    page.evaluate("() => window.releaseDeadlineResponse()")
    expect(page.get_by_text("Schedule is unavailable.", exact=False)).to_be_visible()
    expect(event_title).to_have_count(0)
    expect(deadlines).to_be_hidden()

    page.evaluate(
        "() => { delete window.releaseDeadlineResponse; window.deadlineReleased = false; }"
    )
    work_view.select_option("events")
    work_view.select_option("schedule")
    page.wait_for_function("() => typeof window.releaseDeadlineResponse === 'function'")
    second = create_workspace_in_browser(page, origin, "No schedule deadlines")
    expect(page.get_by_label("Workspace", exact=True)).to_have_value(second)
    expect(page.get_by_text("No task deadlines from this date.", exact=True)).to_be_visible()
    page.evaluate("() => window.releaseDeadlineResponse()")
    page.wait_for_function("() => window.deadlineReleased")
    expect(page.get_by_text("No task deadlines from this date.", exact=True)).to_be_visible()
    expect(page.get_by_text("Schedule is unavailable.", exact=False)).to_have_count(0)
    expect(event_title).to_have_count(0)


def test_workspace_browser_due_date_filter_survives_retry_and_task_update(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "Filtered due work")
    context.new_cdp_session(page).send("Emulation.setTimezoneOverride", {"timezoneId": "UTC"})
    page.clock.set_fixed_time(datetime(2030, 1, 2, 12, tzinfo=UTC))
    seed_browser_work(page, first, ["Earlier task"], due_date="2030-01-01")
    seed_browser_work(page, first, ["Later task"], due_date="2030-01-06")

    view = page.get_by_label("Work view", exact=True)
    view.select_option("due")
    due_date = page.get_by_label("Show due tasks from", exact=True)
    earlier = page.get_by_text("Earlier task", exact=True)
    later = page.locator("#work-items > li").filter(has_text="Later task")
    expect(due_date).to_have_value("")
    expect(earlier).to_be_visible()

    url = origin + f"/api/v2/workspaces/{first}/work-due-page?limit=20&from_date=2030-01-06"
    page.route(url, lambda route: route.fulfill(status=503), times=1)
    due_date.fill("2030-01-06")
    page.get_by_role("button", name="Filter due tasks", exact=True).click()
    expect(page.get_by_text("Could not load work items.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(later).to_be_visible()
    expect(earlier).to_have_count(0)
    later.get_by_role("button", name="Start task", exact=True).click()
    expect(later.get_by_role("button", name="Complete task", exact=True)).to_be_visible()
    later.get_by_role("button", name="Complete task", exact=True).click()
    expect(page.get_by_text("No unfinished tasks due from this date.", exact=True)).to_be_visible()
    expect(due_date).to_have_value("2030-01-06")

    page.get_by_role("button", name="Today", exact=True).click()
    expect(due_date).to_be_hidden()
    expect(earlier).to_be_visible()
    page.get_by_role("button", name="Work items", exact=True).click()
    expect(due_date).to_have_value("2030-01-06")
    expect(earlier).to_have_count(0)

    titles = [f"Filtered task {index:02}" for index in range(21)]
    seed_browser_work(page, first, titles, due_date="2030-01-07")
    page.get_by_role("button", name="Filter due tasks", exact=True).click()
    rows = page.locator("#work-items > li")
    expect(rows).to_have_count(20)
    more = page.get_by_role("button", name="Load more", exact=True)
    page.route(url + "&after=**", lambda route: route.fulfill(status=404), times=1)
    more.click()
    expect(
        page.get_by_text(
            "The due task list changed. Retry to start from the first page.", exact=True
        )
    ).to_be_visible()
    expect(rows).to_have_count(0)
    page.get_by_role("button", name="Retry work list", exact=True).click()
    expect(rows).to_have_count(20)
    more.click()
    expect(rows).to_have_count(21)
    expect(rows.last).to_contain_text(titles[0])
    expect(earlier).to_have_count(0)
    expect(due_date).to_have_value("2030-01-06")

    page.get_by_role("button", name="Filter due tasks", exact=True).click()
    expect(rows).to_have_count(20)
    base = f"/api/v2/workspaces/{first}"
    current = fetch(page, base + "/work-due-page?limit=1&from_date=2030-01-06")
    assert current["status"] == 200
    moved = json.loads(current["text"])["items"][0]
    assert moved["data"]["title"] == titles[-1]
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    saved = fetch(
        page,
        base + f"/work/{moved['id']}/task-details",
        method="PATCH",
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
        body=json.dumps(
            {
                "expected_version": moved["version"],
                "details": {"title": titles[-1], "description": None, "due_date": "2030-01-08"},
            }
        ),
    )
    assert saved["status"] == 200, saved["text"]
    more.click()
    expect(
        page.get_by_text(
            "The due task list changed. Retry to start from the first page.", exact=True
        )
    ).to_be_visible()
    expect(rows).to_have_count(0)
    page.get_by_role("button", name="Retry work list", exact=True).click()
    more.click()
    expect(rows).to_have_count(21)
    expect(rows.last).to_contain_text(titles[-1])
    expect(page.get_by_text(titles[-1], exact=True)).to_have_count(1)

    second = create_workspace_in_browser(page, origin, "Unfiltered due work")
    expect(page.get_by_label("Workspace", exact=True)).to_have_value(second)
    expect(due_date).to_have_value("")
    expect(earlier).to_have_count(0)


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


def test_workspace_browser_title_search_finds_older_items_and_clears(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Title search workspace")
    seed_browser_work(page, workspace_id, ["Old Budget Review"])
    seed_browser_work(page, workspace_id, [f"Recent task {index}" for index in range(21)])
    page.reload()
    search = page.get_by_role("searchbox", name="Search work titles")
    button = page.get_by_role("button", name="Search", exact=True)
    expect(page.get_by_text("Recent task 20", exact=True)).to_be_visible()
    expect(page.get_by_text("Old Budget Review", exact=True)).to_have_count(0)
    search.fill("bUdGeT")
    with page.expect_request("**/work-page/search") as sent:
        button.click()
    assert sent.value.method == "POST"
    assert sent.value.post_data_json["q"] == "bUdGeT"
    assert "?" not in sent.value.url
    expect(page.get_by_text("Old Budget Review", exact=True)).to_be_visible()
    expect(page.get_by_text("Recent task 20", exact=True)).to_have_count(0)
    search.fill("missing")
    button.click()
    expect(page.get_by_text("No work titles match your search.", exact=True)).to_be_visible()
    page.get_by_role("button", name="Clear search").click()
    expect(search).to_be_focused()
    expect(search).to_have_value("")
    expect(page.get_by_text("Recent task 20", exact=True)).to_be_visible()
    page.get_by_label("Work view", exact=True).select_option("due")
    expect(search).to_be_hidden()


def test_today_opens_blocked_tasks_across_work_filters(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Workshop blockers")
    seed_browser_work(page, workspace, ["Await room confirmation", "Unrelated open task"])
    seed_browser_work(page, workspace, ["Await speaker reply"], due_date="2099-06-01")
    page.reload()
    for title in ("Await room confirmation", "Await speaker reply"):
        row = page.get_by_role("listitem").filter(has_text=title)
        row.get_by_role("button", name="Start task").click()
        row.get_by_role("button", name="Block task").click()
        expect(row.get_by_role("button", name="Resume task")).to_be_visible()

    view = page.get_by_label("Work view", exact=True)
    status = page.get_by_label("Task status", exact=True)
    project = page.get_by_label("Project filter", exact=True)
    priority = page.get_by_label("Priority filter", exact=True)
    search = page.get_by_role("searchbox", name="Search work titles")
    view.select_option("workspace")
    page.get_by_label("New project name").fill("Old project")
    page.get_by_role("button", name="Create project", exact=True).click()
    expect(project.locator("option:checked")).to_have_text("Old project")
    status.select_option("completed")
    priority.select_option("high")
    search.fill("Old search")
    with page.expect_response("**/work-page/search"):
        page.get_by_role("button", name="Search", exact=True).click()
    search.fill("Unapplied draft")
    shortcut = page.get_by_role("button", name="View blocked tasks")
    expect(shortcut).to_be_hidden()
    page.get_by_role("button", name="Today", exact=True).click()
    page.get_by_role("button", name="New task", exact=True).click()
    expect(shortcut).to_be_disabled()
    page.get_by_role("button", name="Cancel", exact=True).click()
    with page.expect_request("**/work-page?*") as sent:
        shortcut.press("Enter")
    assert sent.value.method == "GET"
    assert parse_qs(urlsplit(sent.value.url).query) == {"limit": ["20"], "task_status": ["blocked"]}
    expect(page.get_by_role("button", name="Work items", exact=True)).to_be_focused()
    expect(view).to_have_value("all")
    expect(status).to_have_value("blocked")
    for control in (project, priority, search):
        expect(control).to_have_value("")
    expect(page.get_by_text("Unrelated open task", exact=True)).to_have_count(0)
    for title in ("Await room confirmation", "Await speaker reply"):
        row = page.get_by_role("listitem").filter(has_text=title)
        row.get_by_role("button", name="Resume task").click()
        expect(row).to_have_count(0)
    expect(page.get_by_text("No tasks match the current filters.", exact=True)).to_be_visible()


def test_workspace_browser_filters_task_status_with_title_search(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Task status filters")
    seed_browser_work(page, workspace_id, ["Budget review", "Other task"])
    page.reload()
    status = page.get_by_label("Task status", exact=True)
    search = page.get_by_role("searchbox", name="Search work titles")
    expect(status).to_be_enabled()
    status.select_option("open")
    search.fill("Budget")
    with page.expect_request("**/work-page/search") as sent:
        page.get_by_role("button", name="Search", exact=True).click()
    assert sent.value.post_data_json["task_status"] == "open"
    row = page.get_by_role("listitem").filter(has_text="Budget review")
    expect(row).to_be_visible()
    expect(page.get_by_text("Other task", exact=True)).to_have_count(0)
    row.get_by_role("button", name="Start task", exact=True).click()
    expect(page.get_by_text("No tasks match the current filters.", exact=True)).to_be_visible()
    status.select_option("active")
    expect(row).to_be_visible()
    page.get_by_role("button", name="Clear search").click()
    expect(status).to_have_value("active")
    expect(row).to_be_visible()
    expect(page.get_by_text("Other task", exact=True)).to_have_count(0)
    view = page.get_by_label("Work view", exact=True)
    view.select_option("events")
    expect(status).to_be_hidden()
    view.select_option("all")
    expect(status).to_have_value("active")
    expect(row).to_be_visible()


def test_workspace_browser_creates_project_and_assigns_task(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    create_workspace_in_browser(page, origin, "Project grouping workspace")
    project_filter = page.get_by_label("Project filter", exact=True)
    expect(project_filter).to_be_enabled()
    page.get_by_label("New project name").fill("Conference")
    page.get_by_role("button", name="Create project", exact=True).click()
    expect(page.get_by_text("Project created.", exact=True)).to_be_visible()
    expect(project_filter.locator("option:checked")).to_have_text("Conference")
    page.get_by_role("button", name="New task", exact=True).click()
    task_project = page.get_by_label("Task project", exact=True)
    expect(task_project.locator("option:checked")).to_have_text("Conference")
    page.get_by_label("Task title", exact=True).fill("Reserve meeting room")
    page.get_by_role("button", name="Create task", exact=True).click()
    task = page.get_by_role("listitem").filter(has_text="Reserve meeting room")
    expect(task).to_contain_text("Conference")
    task.get_by_role("button", name="Share with workspace").click()
    preview = page.get_by_role("form", name="Review workspace sharing")
    expect(preview.get_by_text("Conference", exact=True)).to_be_visible()
    preview.get_by_role("button", name="Close sharing review").click()
    task.get_by_role("button", name="Edit task", exact=True).click()
    task_project.select_option("")
    page.get_by_role("button", name="Save changes", exact=True).click()
    expect(task).to_have_count(0)
    expect(page.get_by_text("No tasks match the current filters.", exact=True)).to_be_visible()
    project_filter.select_option("")
    expect(task).to_be_visible()
    expect(task).not_to_contain_text("Conference")

    # A project added by another request may be newer than the tab's catalog.
    current = json.loads(fetch(page, "/api/v2/session")["text"])
    ws = page.get_by_label("Workspace", exact=True).input_value()
    path = f"/api/v2/workspaces/{ws}"
    headers = {"Content-Type": "application/json", "X-CSRF-Token": current["csrf_token"]}
    created = fetch(
        page,
        path + "/projects",
        method="POST",
        headers=headers,
        body=json.dumps({"name": "Facilities"}),
    )
    assert created["status"] == 201
    late_project = json.loads(created["text"])["id"]
    created = fetch(
        page,
        path + "/work",
        method="POST",
        headers=headers,
        body=json.dumps(
            {"item": {"kind": "task", "title": "Late assignment"}, "project_id": late_project}
        ),
    )
    assert created["status"] == 201
    late_task = json.loads(created["text"])["id"]
    page.get_by_role("searchbox", name="Search work titles").fill("Late assignment")
    page.get_by_role("button", name="Search", exact=True).click()
    row = page.get_by_role("listitem").filter(has_text="Late assignment")
    row.get_by_role("button", name="Edit task", exact=True).click()
    expect(task_project).to_have_value(late_project)
    page.get_by_label("Task title", exact=True).fill("Late assignment updated")
    page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_text("Task updated.", exact=True)).to_be_visible()
    retained = json.loads(fetch(page, path + "/work/" + late_task)["text"])
    assert retained["project_id"] == late_project
    page.route("**/work-page?*", lambda route: route.fulfill(status=403))
    page.get_by_role("button", name="Clear search").click()
    expect(page.get_by_text("This work list is unavailable.", exact=False)).to_be_visible()
    expect(project_filter.get_by_role("option")).to_have_count(1)
    expect(project_filter).to_be_disabled()


def test_workspace_browser_sets_and_filters_task_priority(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    create_workspace_in_browser(page, origin, "Task priorities")
    priority_filter = page.get_by_label("Priority filter", exact=True)
    expect(priority_filter).to_be_enabled()
    priority_filter.select_option("high")
    page.get_by_role("button", name="New task", exact=True).click()
    priority = page.get_by_label("Task priority", exact=True)
    expect(priority).to_have_value("high")
    page.get_by_label("Task title", exact=True).fill("Prepare budget")
    page.get_by_role("button", name="Create task", exact=True).click()
    row = page.get_by_role("listitem").filter(has_text="Prepare budget")
    expect(row).to_contain_text("High priority")
    row.get_by_role("button", name="Edit task", exact=True).click()
    priority.select_option("low")
    page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_text("No tasks match the current filters.", exact=True)).to_be_visible()
    expect(row).to_have_count(0)
    priority_filter.select_option("low")
    expect(row).to_contain_text("Low priority")
    row.get_by_role("button", name="Share with workspace", exact=True).click()
    preview = page.get_by_role("form", name="Review workspace sharing")
    expect(preview.get_by_text("Low", exact=True)).to_be_visible()


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


def test_workspace_access_invitation_role_lifecycle_and_last_owner_conflict(login_browser):
    from playwright.sync_api import expect

    page, context, origin, provider, sign, _ = login_browser
    open_workspace(page, origin, provider)
    workspace_id = create_workspace_in_browser(page, origin, "Test access management")
    page.get_by_role("button", name="Workspace access", exact=True).click()
    panel = page.get_by_role("region", name="Workspace access", exact=True)
    roster = panel.get_by_role("list", name="Members", exact=True)
    history = panel.get_by_role("list", name="Recent access changes", exact=True)
    own = roster.get_by_role("listitem").filter(has_text="(you)")
    expect(own).to_contain_text("Owner · Active")
    assert page.locator("#access-user-id").inner_text() in own.inner_text()
    own.get_by_role("combobox").select_option("member")
    own.get_by_role("button", name="Save role").click()
    expect(page.get_by_text("Keep at least one active owner.", exact=False)).to_be_visible()
    expect(own).to_contain_text("Owner · Active")

    browser = context.browser
    assert browser is not None
    recipient_context = browser.new_context()
    try:
        recipient = recipient_context.new_page()
        recipient.goto(origin + "/api/v2/test-login-browser")
        issued = fetch(
            recipient,
            "/api/v2/session",
            method="POST",
            headers={
                "Authorization": f"Bearer {sign('synthetic-teammate')}",
            },
        )
        assert issued["status"] == 201
        recipient.goto(origin + "/api/v2/workspace")
        recipient.get_by_role("button", name="Register profile", exact=True).click()
        expect(recipient.get_by_text("Profile registered.", exact=True)).to_be_visible()
        teammate_id = recipient.locator("#invitation-user-id").inner_text()
        assert teammate_id
        selection = recipient.get_by_label("Workspace", exact=True)
        expect(selection).to_be_disabled()
        outgoing = panel.get_by_role("list", name="Pending invitations", exact=True)
        incoming = recipient.get_by_role("list", name="Incoming invitations", exact=True)

        def offer():
            panel.get_by_label("Registered user ID", exact=True).fill(teammate_id)
            panel.get_by_label("Access role", exact=True).select_option("observer")
            panel.get_by_role("button", name="Send invitation", exact=True).click()
            expect(outgoing.get_by_role("listitem")).to_contain_text(teammate_id)
            expect(roster.get_by_text(teammate_id, exact=True)).to_have_count(0)
            recipient.get_by_role("button", name="Refresh invitations", exact=True).click()
            expect(incoming.get_by_text("Test access management", exact=True)).to_be_visible()
            expect(incoming.get_by_role("listitem")).to_contain_text("Observer")
            expect(selection).to_be_disabled()

        offer()
        incoming.get_by_role("button", name="Decline invitation", exact=True).click()
        expect(recipient.get_by_text("Invitation declined.", exact=True)).to_be_visible()
        panel.get_by_role("button", name="Refresh access details", exact=True).click()
        expect(outgoing.get_by_role("listitem")).to_have_count(0)
        offer()
        outgoing.get_by_role("button", name="Revoke invitation", exact=True).click()
        expect(outgoing.get_by_role("listitem")).to_have_count(0)
        incoming.get_by_role("button", name="Accept invitation", exact=True).click()
        expect(
            recipient.get_by_text("This invitation changed or is no longer available.", exact=True)
        ).to_be_visible()
        expect(selection).to_be_disabled()

        offer()
        # A bounded list can omit the newly joined workspace. Recover through an authorized read.
        recipient.route(
            origin + "/api/v2/workspaces?limit=100", lambda route: route.fulfill(json=[]), times=1
        )
        with recipient.expect_response(origin + f"/api/v2/workspaces/{workspace_id}") as selected:
            incoming.get_by_role("button", name="Accept invitation", exact=True).click()
        assert selected.value.status == 200
        expect(recipient.get_by_text("Invitation accepted.", exact=True)).to_be_visible()
        expect(selection).to_have_value(workspace_id)
        recipient.route(
            origin + "/api/v2/workspaces?limit=100", lambda route: route.fulfill(json=[]), times=1
        )
        with recipient.expect_response(origin + f"/api/v2/workspaces/{workspace_id}") as refreshed:
            recipient.get_by_role("button", name="Refresh workspaces", exact=True).click()
        assert refreshed.value.status == 200
        expect(selection).to_have_value(workspace_id)
        recipient.get_by_role("button", name="Workspace access", exact=True).click()
        expect(recipient.locator("#access-role")).to_have_text("Observer")
        expect(recipient.get_by_role("list", name="Members", exact=True)).to_be_hidden()
    finally:
        recipient_context.close()

    panel.get_by_role("button", name="Refresh access details", exact=True).click()
    row = roster.get_by_role("listitem").filter(has_text=teammate_id)
    expect(row).to_contain_text("Observer · Active")
    expect(history.get_by_text("Access granted", exact=True)).to_be_visible()
    row.get_by_role("combobox").select_option("member")
    row.get_by_role("button", name="Save role").click()
    expect(row).to_contain_text("Member · Active")
    row.get_by_role("button", name="Remove access").click()
    expect(row).to_contain_text("Member · Inactive")
    row.get_by_role("button", name="Reactivate access").click()
    expect(row).to_contain_text("Member · Active")
    row.get_by_role("combobox").select_option("owner")
    row.get_by_role("button", name="Save role").click()
    expect(row).to_contain_text("Owner · Active")
    expect(history.get_by_role("listitem").first).to_contain_text("version 5")

    own.get_by_role("combobox").select_option("observer")
    own.get_by_role("button", name="Save role").click()
    expect(page.get_by_text("Role changed.", exact=True)).to_be_visible()
    expect(page.locator("#access-role")).to_have_text("Observer")
    expect(roster.get_by_role("listitem")).to_have_count(0)
    expect(history.get_by_role("listitem")).to_have_count(0)
    expect(panel.get_by_role("button", name="Send invitation")).to_be_hidden()


def test_workspace_access_reloads_stale_versions_and_removes_own_workspace(login_browser, pg):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    memberships = MembershipService(pg[0])
    owner = Principal(provider, "new-browser-user")
    teammate = Principal(provider, "second-synthetic-owner")
    memberships.create_workspace(teammate, WorkspaceCreate(name="Teammate registration"))
    teammate_id = memberships.profile(teammate).id
    open_workspace(page, origin, provider)
    fallback = create_workspace_in_browser(page, origin, "A remaining workspace")
    departing = create_workspace_in_browser(page, origin, "B departing workspace")
    from uuid import UUID

    workspace_id = UUID(departing)
    memberships.add_member(owner, workspace_id, teammate_id)
    page.get_by_role("button", name="Workspace access", exact=True).click()
    roster = page.get_by_role("list", name="Members", exact=True)
    teammate_row = roster.get_by_role("listitem").filter(has_text=str(teammate_id))
    expect(teammate_row).to_contain_text("Member · Active")
    from flowpilot_api.access import Role

    memberships.change_member(
        owner, workspace_id, teammate_id, role=Role.OWNER, active=True, expected_version=1
    )
    teammate_row.get_by_role("button", name="Remove access").click()
    expect(page.get_by_text("Membership changed or already exists.", exact=False)).to_be_visible()
    expect(teammate_row).to_contain_text("Owner · Active")
    own = roster.get_by_role("listitem").filter(has_text="(you)")
    page.once("dialog", lambda dialog: dialog.accept())
    own.get_by_role("button", name="Remove access").click()
    pick = page.get_by_label("Workspace", exact=True)
    expect(pick).to_have_value(fallback)
    expect(pick.locator(f"option[value='{departing}']")).to_have_count(0)
    expect(page.get_by_text("Access removed.", exact=True)).to_be_visible()
    expect(teammate_row).to_have_count(0)
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_be_visible()


def test_workspace_access_binds_roster_reads_to_its_browser_session(login_browser, pg):
    from uuid import UUID

    from flowpilot_api.access import Role
    from playwright.sync_api import expect

    page, context, origin, provider, sign, _ = login_browser
    memberships = MembershipService(pg[0])
    owner = Principal(provider, "new-browser-user")
    replacement = Principal(provider, "replacement-owner")
    memberships.create_workspace(replacement, WorkspaceCreate(name="Teammate registration"))
    replacement_id = memberships.profile(replacement).id
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Shared owner access")
    memberships.add_member(owner, UUID(workspace), replacement_id, role=Role.OWNER)

    context.clear_cookies()
    page.goto(origin + "/api/v2/test-login-browser")
    issued = fetch(
        page,
        "/api/v2/session",
        method="POST",
        headers={
            "Authorization": f"Bearer {sign('new-browser-user', scope='flowpilot:read')}",
        },
    )
    assert issued["status"] == 201
    read_csrf = json.loads(issued["text"])["csrf_token"]
    page.goto(origin + "/api/v2/workspace")
    page.get_by_role("button", name="Workspace access", exact=True).click()
    roster = page.get_by_role("list", name="Members", exact=True)
    expect(roster.get_by_role("listitem")).to_have_count(2)
    expect(roster.get_by_role("button")).to_have_count(0)
    expect(page.get_by_role("button", name="Send invitation", exact=True)).to_be_hidden()

    context.clear_cookies()
    issued = fetch(
        page,
        "/api/v2/session",
        method="POST",
        headers={
            "Authorization": f"Bearer {sign('replacement-owner')}",
        },
    )
    assert issued["status"] == 201
    new_csrf = json.loads(issued["text"])["csrf_token"]
    path = f"/api/v2/workspaces/{workspace}/members?limit=100"
    assert fetch(page, path, headers={"X-CSRF-Token": new_csrf})["status"] == 200
    assert fetch(page, "/api/v2/me", headers={"X-CSRF-Token": read_csrf})["status"] == 401
    page.get_by_role("button", name="Refresh access details", exact=True).click()
    expect(page.get_by_text("Your session is unavailable.", exact=False)).to_be_visible()
    expect(roster.get_by_role("listitem")).to_have_count(0)


def test_workspace_access_ignores_denial_from_previous_workspace(login_browser):
    from playwright.sync_api import expect

    page, _, origin, provider, _, _ = login_browser
    open_workspace(page, origin, provider)
    first = create_workspace_in_browser(page, origin, "First access workspace")
    second = create_workspace_in_browser(page, origin, "Second access workspace")
    pick = page.get_by_label("Workspace", exact=True)
    pick.select_option(first)
    url = f"/api/v2/workspaces/{first}/membership-history?limit=20"
    page.evaluate(
        """url => {
        const original = window.fetch.bind(window);
        window.fetch = async (path, options) => {
            const response = await original(path, options);
            if (path !== url) return response;
            await new Promise(resolve => { window.releaseOldAccess = resolve; });
            setTimeout(() => { window.oldAccessProcessed = true; }, 0);
            return new Response(null, {status: 403});
        };
    }""",
        url,
    )
    page.get_by_role("button", name="Workspace access", exact=True).click()
    page.wait_for_function("() => typeof window.releaseOldAccess === 'function'")
    pick.select_option(second)
    roster = page.get_by_role("list", name="Members", exact=True)
    expect(roster.get_by_role("listitem")).to_have_count(1)
    page.evaluate("() => window.releaseOldAccess()")
    page.wait_for_function("() => window.oldAccessProcessed === true")
    expect(roster.get_by_role("listitem")).to_have_count(1)
    expect(page.locator("#access-role")).to_have_text("Owner")
    expect(page.get_by_text("Access details are unavailable.", exact=False)).to_have_count(0)


def test_workspace_browser_reviews_and_shares_tasks_and_events(login_browser, pg):
    from uuid import UUID

    from flowpilot_api.access import Role
    from playwright.sync_api import expect

    page, context, origin, provider, sign, _ = login_browser
    service = MembershipService(pg[0])
    viewer = Principal(provider, "sharing-observer")
    viewer_id = service.register_profile(viewer).id
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "Sharing workshop")
    service.add_member(
        Principal(provider, "new-browser-user"), UUID(workspace), viewer_id, role=Role.OBSERVER
    )
    csrf = json.loads(fetch(page, "/api/v2/session")["text"])["csrf_token"]
    headers = {"Content-Type": "application/json", "X-CSRF-Token": csrf}
    base = f"/api/v2/workspaces/{workspace}"

    def post(path, payload):
        result = fetch(page, path, method="POST", headers=headers, body=json.dumps(payload))
        assert result["status"] in (200, 201)
        return json.loads(result["text"])

    description = "<b>Workshop agenda</b>\nBring the handout."
    task = post(
        base + "/work",
        {
            "item": {
                "kind": "task",
                "title": "Private rehearsal task",
                "description": description,
            }
        },
    )
    event = post(
        base + "/work",
        {
            "item": {
                "kind": "event",
                "title": "Workshop time",
                "time_zone": "America/New_York",
                "starts_at": "2030-06-15T14:00:01.123456Z",
                "ends_at": "2030-06-15T15:00:02.123456Z",
            }
        },
    )
    task_path = base + "/work/" + task["id"]
    sources = []
    for visibility, summary, excerpt in (
        ("private", "Private evidence title", "Private evidence"),
        ("summary_shared", "Published evidence summary", "Withheld excerpt"),
    ):
        source = post(
            base + "/sources",
            {
                "reference": f"Synthetic reference {visibility}",
                "summary": summary,
                "excerpt": excerpt,
            },
        )
        sources.append(source["id"])
        task = post(
            task_path + "/evidence",
            {
                "source_id": source["id"],
                "expected_version": task["version"],
                "visibility": visibility,
            },
        )
    browser = context.browser
    assert browser is not None
    other_context = browser.new_context()
    try:
        other = other_context.new_page()
        other.goto(origin + "/api/v2/test-login-browser")
        issued = fetch(
            other,
            "/api/v2/session",
            method="POST",
            headers={
                "Authorization": f"Bearer {sign('sharing-observer')}",
            },
        )
        assert issued["status"] == 201
        other.goto(origin + "/api/v2/workspace")
        other.get_by_label("Work view", exact=True).select_option("workspace")
        expect(other.get_by_text("No shared work yet.", exact=True)).to_be_visible()

        page.get_by_label("Work view", exact=True).select_option("private")
        draft = page.get_by_role("listitem").filter(has_text="Private rehearsal task")
        preview = page.get_by_role("form", name="Review workspace sharing")
        confirm = preview.get_by_role("button", name="Confirm sharing", exact=True)
        draft.get_by_role("button", name="Share with workspace", exact=True).click()
        expect(confirm).to_be_enabled()
        expect(preview.get_by_text("Sharing workshop", exact=True)).to_be_visible()
        expect(preview.locator("dd").filter(has_text="Workshop agenda")).to_have_text(
            description, use_inner_text=True
        )
        expect(preview.get_by_text("Published evidence summary", exact=True)).to_be_visible()
        expect(preview.get_by_text("Private evidence title", exact=True)).to_have_count(0)
        expect(preview.get_by_text("Withheld excerpt", exact=True)).to_have_count(0)
        expect(page.get_by_label("Workspace", exact=True)).to_be_disabled()
        preview.get_by_role("button", name="Close sharing review", exact=True).click()
        assert json.loads(fetch(page, task_path)["text"])["visibility"] == "private"

        draft.get_by_role("button", name="Share with workspace", exact=True).click()
        expect(confirm).to_be_enabled()
        revised = "Updated rehearsal task"
        changed = fetch(
            page,
            task_path + "/task-details",
            method="PATCH",
            headers=headers,
            body=json.dumps(
                {
                    "expected_version": task["version"],
                    "details": {"title": revised, "description": description, "due_date": None},
                }
            ),
        )
        assert changed["status"] == 200
        confirm.click()
        expect(page.get_by_text("This item changed.", exact=False)).to_be_visible()
        expect(confirm).to_be_disabled()
        preview.get_by_role("button", name="Close sharing review", exact=True).click()
        page.get_by_role("button", name="Retry work list", exact=True).click()
        updated = page.get_by_role("listitem").filter(has_text=revised)
        updated.get_by_role("button", name="Share with workspace", exact=True).click()
        expect(preview.get_by_text(revised, exact=True)).to_be_visible()
        confirm.click()
        expect(page.get_by_text("Work shared with the workspace.", exact=True)).to_be_visible()
        expect(updated).to_have_count(0)

        event_row = page.get_by_role("listitem").filter(has_text="Workshop time")
        event_row.get_by_role("button", name="Share with workspace", exact=True).click()
        expect(preview.get_by_text(event["data"]["starts_at"], exact=True)).to_be_visible()
        expect(preview.get_by_text(event["data"]["ends_at"], exact=True)).to_be_visible()
        expect(preview.get_by_text(event["data"]["time_zone"], exact=True)).to_be_visible()
        confirm.click()
        expect(event_row).to_have_count(0)

        page.get_by_label("Work view", exact=True).select_option("workspace")
        expect(page.get_by_role("button", name="New task", exact=True)).to_be_hidden()
        expect(page.get_by_role("button", name="New event", exact=True)).to_be_hidden()
        edit_task = updated.get_by_role("button", name="Edit task", exact=True)
        edit_task.click()
        expect(page.get_by_label("Task title", exact=True)).to_have_value(revised)
        page.locator("#cancel-task").click()
        expect(edit_task).to_be_focused()
        edit_task.click()
        shared_task_title = "Shared rehearsal task updated"
        page.get_by_label("Task title", exact=True).fill(shared_task_title)
        page.locator("#save-task").click()
        expect(page.get_by_text("Task updated.", exact=True)).to_be_visible()

        edit_event = event_row.get_by_role("button", name="Edit event", exact=True)
        edit_event.click()
        expect(page.get_by_label("Event title", exact=True)).to_have_value("Workshop time")
        page.get_by_role("button", name="Close event editor", exact=True).click()
        expect(edit_event).to_be_focused()
        edit_event.click()
        shared_event_title = "Shared workshop time updated"
        page.get_by_label("Event title", exact=True).fill(shared_event_title)
        page.get_by_role("button", name="Save event changes", exact=True).click()
        expect(page.get_by_text("Event updated.", exact=True)).to_be_visible()

        other.reload()
        other.get_by_label("Work view", exact=True).select_option("workspace")
        task_row = other.get_by_role("listitem").filter(has_text=shared_task_title)
        expect(task_row).to_be_visible()
        expect(other.get_by_role("listitem").filter(has_text=shared_event_title)).to_be_visible()
        expect(task_row.get_by_role("button")).to_have_count(0)
        expect(task_row).to_contain_text("Shared with workspace")
        assert json.loads(fetch(other, task_path + "/evidence")["text"]) == [
            {"summary": "Published evidence summary"}
        ]
        for source_id in sources:
            assert fetch(other, base + "/sources/" + source_id)["status"] == 404
    finally:
        other_context.close()


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
