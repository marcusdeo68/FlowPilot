# Implementation 0006 - Browser regressions and maintenance checks

Status: merged in PR #5 after all six CI jobs passed. Local verification: 45 tests
passed including six Chromium workflows, with no TestClient deprecation warning.
CI also passed 16 real PostgreSQL integration checks plus the platform/Python matrix,
lint, formatting, package builds, and JavaScript syntax checks.

## Behavior changes and reproduced bugs

FP-007: open New task with an empty title and click Cancel. The dialog previously
stayed open because HTML form validation applied to the cancel submitter too.
Both Cancel and Close now use `formnovalidate`. Save still requires validation;
the existing dialog form submission handles cancel without writing a record.

FP-008: submit a whitespace-only title. The server correctly rejects it, but its
structured validation error previously became `[object Object]` in the toast.
`validationMessage` projects the defined field label and message into readable
text. The form stays open, preserves the attempted input, and re-enables Save.
Error text still renders through textContent; it is never HTML.

Both bugs were first reproduced by failing Chromium tests, then fixed. The tests
also verify capture, individual confirmation/start/completion, persisted reload,
keyboard focus, concurrent-state conflict recovery, and injection-shaped text.

## Why real-browser checks complement API tests

An API test cannot tell whether a browser enforces a required form field before
JavaScript sees the click, or whether a DOM update produces useful text. The
Playwright suite drives accessible controls in headless Chromium against the real
FastAPI server. Most assertions wait for user-visible state instead of sleeping.
The competing-writer test changes server state through HTTP, then clicks the
browser's stale version and verifies reload rather than a silent overwrite.

Each test starts its own loopback listener with an OS-assigned port and temporary
SQLite database, and closes its browser context and server afterward. No installed
Chrome profile, logged-in account, provider connection, or personal data is used.
Browser dependencies are optional so ordinary backend development does not need
to download Chromium. CI has a separate browser job and installs its dependencies.

## Dependency and environment maintenance

FP-001: Starlette's official TestClient guidance now uses httpx2. The dev dependency
changes to httpx2 and the regression suite verifies compatibility rather than
hiding the warning. Alembic explicitly configures its path separator too.

FP-006: repeated dependency updates in the OneDrive checkout failed while removing
package metadata, leaving an incomplete environment. The old agent-created `.venv`
was preserved under ignored `.tools/venv-backup-0006`; a fresh `.venv` was built
successfully. uv now copies dependency files instead of linking cache files. This
worked for rebuilding the environment but does not establish that OneDrive caused
every lock or eliminate future antivirus/sync locks. Future projects belong in
the user's CODE folder; migrating this checkout remains a separate operation.

CI runs for main pushes, pull requests, manual dispatch, and a daily scheduled
check at 10:17 UTC. The schedule checks the committed code and locked dependencies
against fresh runners; it is not a scheduled development agent or uptime monitor.
GitHub can delay scheduled jobs. Weekly Dependabot PRs cover dependency updates.

## Run locally

```powershell
uv sync --locked --extra dev --extra browser
uv run --no-sync playwright install --only-shell chromium
$env:FLOWPILOT_BROWSER_TESTS = '1'
uv run --no-sync pytest -q -m browser
```

On this workstation the browser is under ignored `.tools/playwright`; also set
`$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.tools/playwright'`.
Backend-only runs omit FLOWPILOT_BROWSER_TESTS; the browser fixture explicitly skips.
PostgreSQL tests still require their separate dedicated test URL.

## Remaining limits and next learning step

Chromium checks cover the current local dashboard. Firefox/WebKit, visual
regressions, screen-reader auditing, mobile navigation, and authenticated browser
flows remain open. The dashboard still uses SQLite; the internal PostgreSQL service
is separately tested and awaits verified HTTP identity and remaining unified records.

Read `tests/test_browser.py` alongside the dialog submit listener in `app.js`.
Explain why HTML constraints, server validation, and domain transitions each protect
a different boundary. Compare a syntax check with observing a real click and
waiting for the resulting DOM state.

References: [Playwright library](https://playwright.dev/python/docs/library),
[Starlette TestClient](https://www.starlette.io/testclient/).
