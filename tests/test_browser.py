"""Chromium workflows against a real loopback server and disposable SQLite data."""

import os
import socket
import threading
import time

import pytest
import uvicorn
from flowpilot_api.main import app

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def chromium():
    if os.environ.get("FLOWPILOT_BROWSER_TESTS") != "1":
        pytest.skip("Enable FLOWPILOT_BROWSER_TESTS=1 and install Playwright Chromium")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(chromium, tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWPILOT_DB_PATH", str(tmp_path / "browser.sqlite3"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    context = None
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                pytest.fail("Loopback test server failed to start")
            time.sleep(0.02)
        context = chromium.new_context(viewport={"width": 1280, "height": 900})
        tab = context.new_page()
        tab.goto(f"http://127.0.0.1:{port}")
        tab.locator("#task-list .task-row").first.wait_for()
        yield tab
    finally:
        if context:
            context.close()
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive(), "Test server did not shut down"


def capture(page, title):
    page.get_by_role("button", name="New task").click()
    page.get_by_label("Task title").fill(title)
    page.get_by_role("button", name="Add task", exact=True).click()
    row = page.locator(".task-row").filter(has=page.locator(".task-title", has_text=title))
    row.wait_for()
    return row


def test_capture_review_and_completion_are_explicit(page):
    from playwright.sync_api import expect

    row = capture(page, "Synthetic browser commitment")
    expect(row.locator(".task-check")).to_be_disabled()
    expect(row.locator(".task-detail")).to_contain_text("detected")
    row.get_by_role("button", name="Confirm:").click()
    expect(row.locator(".task-detail")).to_contain_text("confirmed")
    expect(row.locator(".task-check")).to_be_disabled()
    row.get_by_role("button", name="Start:").click()
    expect(row.locator(".task-detail")).to_contain_text("active")
    row.locator(".task-check").check()
    expect(row.locator(".task-detail")).to_contain_text("completed")
    page.reload()
    expect(
        page.locator(".task-row")
        .filter(has_text="Synthetic browser commitment")
        .locator(".task-check")
    ).to_be_checked()
    records = page.request.get(page.url + "api/v1/commitments").json()["items"]
    history = page.request.get(page.url + f"api/v1/commitments/{records[0]['id']}/events").json()
    assert [event["to_status"] for event in history] == [
        "detected",
        "confirmed",
        "active",
        "completed",
    ]


def test_capture_renders_untrusted_text_literally(page):
    from playwright.sync_api import expect

    title = '<img src=x onerror="window.injected=true">'
    row = capture(page, title)
    expect(row.locator(".task-title")).to_have_text(title)
    expect(row.locator("img")).to_have_count(0)
    assert page.evaluate("window.injected === undefined")


def test_conflict_reloads_state_and_keeps_server_authoritative(page):
    from playwright.sync_api import expect

    row = capture(page, "Concurrent browser task")
    item = page.request.get(page.url + "api/v1/commitments").json()["items"][0]
    response = page.request.post(
        page.url + f"api/v1/commitments/{item['id']}/transitions",
        data={"target_status": "confirmed", "expected_version": 1},
    )
    assert response.status == 200
    # The browser still has version 1; its action must fail and then reload version 2.
    row.get_by_role("button", name="Confirm:").click()
    expect(page.locator("#toast")).to_contain_text("Task changed")
    expect(row.locator(".task-detail")).to_contain_text("confirmed")
    expect(row.get_by_role("button", name="Start:")).to_be_enabled()


def test_dialog_cancel_and_keyboard_focus(page):
    from playwright.sync_api import expect

    page.get_by_role("button", name="New task").click()
    expect(page.get_by_label("Task title")).to_be_focused()
    page.get_by_label("Task title").fill("Do not save")
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.locator("#task-dialog")).not_to_be_visible()
    assert page.request.get(page.url + "api/v1/commitments").json()["count"] == 0


def test_empty_dialog_can_be_cancelled(page):
    from playwright.sync_api import expect

    page.get_by_role("button", name="New task").click()
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.locator("#task-dialog")).not_to_be_visible()


def test_server_validation_is_readable_and_form_stays_open(page):
    from playwright.sync_api import expect

    page.get_by_role("button", name="New task").click()
    page.get_by_label("Task title").fill("   ")
    page.get_by_role("button", name="Add task", exact=True).click()
    expect(page.locator("#task-dialog")).to_be_visible()
    expect(page.locator("#toast")).to_contain_text("Text fields cannot contain only whitespace")
    expect(page.locator("#save-task")).to_be_enabled()
