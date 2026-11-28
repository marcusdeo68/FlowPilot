"""Explicitly selected local preview of the signed-in workspace."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_login_browser import create_workspace_in_browser, fetch, open_workspace
from test_login_browser import login_browser as login_browser

pytestmark = [pytest.mark.browser, pytest.mark.postgres]


@pytest.fixture
def login_browser_headless():
    return os.environ.get("FLOWPILOT_INTERACTIVE_PREVIEW") != "1"


def test_workspace_preview(request, monkeypatch, login_browser_headless):
    from playwright.sync_api import expect

    # Select only the database provided by compose.test.yaml. The pg fixture
    # migrates and removes a unique schema for each run.
    monkeypatch.setenv(
        "FLOWPILOT_TEST_DATABASE_URL",
        "postgresql+psycopg://flowpilot:synthetic-test-only@127.0.0.1:5433/flowpilot_test"
        "?hostaddr=127.0.0.1",
    )
    monkeypatch.setenv("FLOWPILOT_BROWSER_TESTS", "1")
    # An existing deployment shell must still start the local preview.
    monkeypatch.setenv("FLOWPILOT_HOSTED", "0")
    monkeypatch.setenv("FLOWPILOT_RAILWAY_EDGE", "0")
    monkeypatch.delenv("FLOWPILOT_PROBE_HOST", raising=False)
    monkeypatch.delenv("FLOWPILOT_PROXY_UPSTREAM_HOST", raising=False)
    monkeypatch.delenv("FLOWPILOT_PROXY_SECRET", raising=False)
    page, _, origin, provider, _, _ = request.getfixturevalue("login_browser")
    open_workspace(page, origin, provider)
    workspace = create_workspace_in_browser(page, origin, "FlowPilot preview")
    session = fetch(page, "/api/v2/session")
    assert session["status"] == 200
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": json.loads(session["text"])["csrf_token"],
    }

    def create(path, data):
        result = fetch(
            page,
            f"/api/v2/workspaces/{workspace}/{path}",
            method="POST",
            headers=headers,
            body=json.dumps(data),
        )
        assert result["status"] == 201, (path, result["status"])
        return json.loads(result["text"])

    project = create("projects", {"name": "Community workshop"})
    title = "Reserve a room for the workshop"
    excerpt = "Please book a room with space for twelve people before the workshop."
    source = create("sources", {"reference": "workshop-room", "summary": title, "excerpt": excerpt})
    suggestion = fetch(
        page,
        f"/api/v2/workspaces/{workspace}/sources/{source['id']}/task-proposal",
        method="PUT",
        headers=headers,
    )
    assert suggestion["status"] == 200
    assert json.loads(suggestion["text"])["state"] == "pending_review"
    due_date = page.evaluate(
        "() => { const now = new Date(); return new Date(now - "
        "now.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }"
    )
    create(
        "work",
        {
            "item": {"kind": "task", "title": "Confirm workshop agenda", "due_date": due_date},
            "project_id": project["id"],
            "priority": "high",
        },
    )
    create("notes", {"body": "Workshop ideas: leave ten minutes for questions."})
    start = datetime.now(UTC) + timedelta(minutes=10)
    create(
        "work-events",
        {
            "title": "Workshop planning session",
            "schedule": {
                "time_zone": "UTC",
                "starts_at": start.replace(tzinfo=None).isoformat(timespec="seconds"),
                "ends_at": (start + timedelta(minutes=30))
                .replace(tzinfo=None)
                .isoformat(timespec="seconds"),
            },
        },
    )
    page.reload()
    page.get_by_label("Workspace", exact=True).select_option(workspace)
    page.get_by_role("button", name="Today", exact=True).click()
    expect(page.get_by_text("Confirm workshop agenda", exact=True)).to_be_visible()
    expect(page.get_by_text("Workshop planning session", exact=True)).to_be_visible()
    review = page.get_by_role("button", name=title, exact=True)
    expect(review).to_be_visible()

    if not login_browser_headless:
        input("FlowPilot is open in Chromium. Press Enter here to close the preview. ")
        return

    capture = os.environ.get("FLOWPILOT_CAPTURE_PREVIEW") == "1"
    output = Path(__file__).resolve().parents[1] / ".tools" / "preview-images"
    if capture:
        output.mkdir(parents=True, exist_ok=True)
        page.locator("#work-panel").screenshot(path=output / "today.png")
    review.click()
    expect(page.get_by_text(excerpt, exact=True)).to_be_visible()
    accept = page.get_by_role("button", name="Accept and create task", exact=True)
    expect(accept).to_be_enabled()
    if capture:
        page.locator("#source-detail").screenshot(path=output / "review.png")
    with page.expect_response("**/review") as accepted:
        accept.click()
    assert accepted.value.status == 200
    result = accepted.value.json()
    assert result["state"] == "accepted" and result["source_id"] == source["id"]
    page.get_by_role("button", name="Go to work list", exact=True).click()
    row = page.get_by_role("listitem").filter(has=page.get_by_text(title, exact=True))
    expect(row).to_have_count(1)
    expect(row).to_be_visible()
    saved = fetch(page, f"/api/v2/workspaces/{workspace}/work/{result['work_id']}")
    assert saved["status"] == 200
    task = json.loads(saved["text"])
    assert task["visibility"] == "private" and task["data"]["title"] == title
    if capture:
        row.screenshot(path=output / "task.png")
