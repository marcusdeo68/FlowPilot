# Implementation 0013 - Local PostgreSQL verification

## Behavior and structure

`compose.test.yaml` starts PostgreSQL 17 in the separate `flowpilot-tests` project,
with database `flowpilot_test`, its own `postgres_test` volume and host binding
`127.0.0.1:5433`. Development Compose and its persistent records are unchanged.
Credentials are public synthetic fixtures, never suitable for real data.

The test URL enters pytest's existing `pg` fixture. It requires the psycopg driver
and a database ending `_test`, creates a random schema, applies Alembic migrations,
and drops that exact schema after the test. For example, two permission tests use
different `fp_test_*` schemas while sharing the disposable database. Separate
containers/volumes protect development records; schemas isolate individual tests.
No application routes or authorization rules change. Local verification exposed
FP-013: on Windows Python 3.12, Proactor connection-reset cleanup could raise
before detaching a socket from the asyncio server. Its active count then remained
nonzero and Uvicorn waited indefinitely during shutdown. The socket-only session
test server now selects a Selector loop on Windows; Playwright subprocesses stay
on their separate execution path. Linux retains its default loop. All security
assertions and the strict server-thread shutdown assertion remain intact.

## Run and verify

From the repository root with Docker running:

```powershell
docker compose -f compose.test.yaml config
docker compose -f compose.test.yaml up -d --wait
docker compose -f compose.test.yaml ps
docker compose -f compose.test.yaml exec -T postgres psql -U flowpilot -d flowpilot_test -c "SELECT current_database(), current_setting('server_version');"
$env:FLOWPILOT_TEST_DATABASE_URL = 'postgresql+psycopg://flowpilot:synthetic-test-only@127.0.0.1:5433/flowpilot_test'
uv sync --locked --extra dev --extra browser
uv run --no-sync playwright install --only-shell chromium
$env:FLOWPILOT_BROWSER_TESTS = '1'
uv run --no-sync pytest -q -m 'postgres and not browser'
uv run --no-sync pytest -q -m browser
uv run --no-sync pytest -q
```

Run the lint, format, typecheck, build and JavaScript checks from the
[README](../../README.md#verify-changes) too. On the existing workstation, Chromium
is installed under `.tools/playwright`; set `PLAYWRIGHT_BROWSERS_PATH` to that
absolute directory when using that installation. Do not mix custom and default
browser installation paths. Verification results are recorded in
[STATUS](../STATUS.md).

Stop only this project after testing:

```powershell
docker compose -f compose.test.yaml stop
Remove-Item Env:FLOWPILOT_TEST_DATABASE_URL
Remove-Item Env:FLOWPILOT_BROWSER_TESTS
```

Stopping preserves the test volume. No volume-deletion command is needed. If port
5433 is occupied, identify the listener before changing anything; do not stop an
unrelated service. If Docker is unavailable, start Docker Desktop's Linux engine.
A missing test URL causes skips, not proof that database checks passed.

## Limits and next increment

Independent Windows verification on 2026-11-16 (working tree based on `7ac632b`):
`.venv\Scripts\python.exe -m pytest -q` passed 177 with no skips;
`-m 'postgres and not browser'` passed 51 (126 deselected); `-m browser` passed
15 (162 deselected). The focused
`tests/test_session_browser.py` suite passed twice, two tests each. Ruff check,
Ruff format (66 files), pinned Pyright (zero diagnostics), `python -m build`
(wheel and sdist), `node --check services/api/src/flowpilot_api/web/app.js`, and
`git diff --check` passed. Commands used the test/browser environment above.
Initial sandbox network/browser restrictions required running checks with host
access; their failures were not treated as passing evidence. Docker inspection
confirmed the database/version, loopback port and separate named volume.

This is local synthetic verification, not production database administration or
live account integration. Browser login/provider configuration and authenticated
dashboard wiring remain separate roadmap work. CI retains its own fresh database
services; no claim of continuous runtime monitoring is made.
