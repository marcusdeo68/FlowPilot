# FlowPilot

**From conversation to completion.** FlowPilot is a unified work coordination hub for bringing permitted signals from email, chat, notes, and calendars into a shared view of tasks, commitments, events, and approved follow-up actions.

This repository currently contains a local API foundation, a dependency-free dashboard shell, and a deterministic commitment lifecycle. It does not yet connect to email, chat, notes, or calendar providers and does not call an AI model.

## Current foundation

- Same-origin local dashboard served at `/` for Today, inbox, tasks, schedule, and review/send workflow previews.
- Dashboard task capture and lifecycle changes use the existing local API; the task view distinguishes loading, empty, failed, and saved results. Inbox, schedule, and draft previews remain labeled samples.
- FastAPI service with separate liveness and database-readiness endpoints.
- SQLite-backed commitment records for local development.
- Validated API inputs and explicit, server-enforced commitment state transitions.
- Optimistic concurrency using a record version, so stale updates are rejected.
- Append-only event history for creation and status changes.
- No external actions, integrations, or authentication; use synthetic data only.

## Run locally

Requires Python 3.11 or newer.

For the reproducible development environment, install
[uv](https://docs.astral.sh/uv/getting-started/installation/) and run:

```powershell
uv sync --locked --extra dev --python 3.12
uv run uvicorn flowpilot_api.main:app --reload --host 127.0.0.1 --port 8000
```

On this workstation uv is also available as `.tools\uv.exe`; that directory is
ignored by Git. The managed environment avoids depending on global Python or
PowerShell activation settings. A conventional Python installation also works:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -e .
py -m uvicorn flowpilot_api.main:app --reload --host 127.0.0.1 --port 8000
```

The API binds to loopback (`127.0.0.1`) by default. Open `http://127.0.0.1:8000/` for the dashboard or `http://127.0.0.1:8000/docs` for the generated local API reference. The default SQLite database is created under `data/flowpilot.sqlite3`; set `FLOWPILOT_DB_PATH` to choose another local path.

In Cursor, use **Terminal > Run Task > FlowPilot: Run local app** after setup.
The **FlowPilot: Tests** task runs the regression suite without activating a shell.

`/healthz` reports whether the process is responding. `/readyz` also checks that the database can be opened. Neither endpoint is an authentication check.

The dashboard is an early local prototype. Its inbox, event, draft, and connection cards are illustrative only; only manually entered commitments are stored. The API has no authentication or workspace authorization, so keep it on loopback and use synthetic data. Do not deploy it or connect personal accounts yet.

## Project map

- `services/api/src/flowpilot_api/`: API routes, domain rules, schemas, and persistence.
- `services/api/src/flowpilot_api/web/`: dependency-free local dashboard assets.
- `docs/`: product intent, architecture, security boundaries, decisions, and learning notes.
- `docs/implementation/`: feature-by-feature implementation notes and software/design explanations.
- `docs/STATUS.md`: maintenance tracker, known issues, verification gaps, and next milestones.

Read [the product direction](docs/PRODUCT.md), [the roadmap](docs/ROADMAP.md), and [security boundaries](docs/SECURITY.md) before extending this foundation.

## Verify changes

```powershell
uv run --locked --extra dev pytest -q
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check .
npx --yes --package pyright@1.1.407 pyright
uv run --locked --extra dev python -m build
node --check services/api/src/flowpilot_api/web/app.js
node --check services/api/src/flowpilot_api/web/workspace.js
node --check services/api/src/flowpilot_api/web/workspace-events.js
```

GitHub Actions runs these checks on Windows and Linux with Python 3.11 and 3.12.
The access policy and typed-work modules are groundwork for Stage 1; the current
commitment endpoints still have no identity or workspace authorization. See
[implementation 0004](docs/implementation/0004-verification-and-access-policies.md).

## PostgreSQL foundation (internal service)

The next storage adapter has a reversible Alembic migration and authorized
services for manual sources, typed work, sharing, and audit history. It is not
connected to the dashboard or HTTP authentication yet. Optional local PostgreSQL
setup, test isolation, design, and remaining limits are documented in
[implementation 0005](docs/implementation/0005-postgres-work-storage.md).
CI runs real-database checks separately; local runs skip them unless
`FLOWPILOT_TEST_DATABASE_URL` points to a dedicated database ending in `_test`.

For a separate local PostgreSQL 17 test database (Docker Desktop must be running):

```powershell
docker compose -f compose.test.yaml up -d --wait
$env:FLOWPILOT_TEST_DATABASE_URL = 'postgresql+psycopg://flowpilot:synthetic-test-only@127.0.0.1:5433/flowpilot_test'
uv run --locked --extra dev pytest -q -m 'postgres and not browser'
```

The test project uses its own volume and loopback port 5433; it does not use
`flowpilot_dev`. Fixtures migrate and clean up isolated schemas automatically.
Stop it with `docker compose -f compose.test.yaml stop`. See
[local test environment](docs/implementation/0013-local-postgres-tests.md) for
browser checks, full verification and troubleshooting.

Chromium workflow checks and optional local browser setup are documented in
[implementation 0006](docs/implementation/0006-browser-regressions.md). CI also
supports manual dispatch and a daily 10:17 UTC maintenance check.

The separate bearer-verified workspace API is described in
[implementation 0007](docs/implementation/0007-verified-workspace-api.md). It requires
explicit identity and PostgreSQL configuration. It runs separately from the local
dashboard. Keep both applications on loopback with synthetic data.

Verified-user workspace creation/discovery and owner-only membership management
are documented in [implementation 0008](docs/implementation/0008-workspace-onboarding.md).
This removes manual user/workspace SQL setup once a compatible access token is
available; live sign-in configuration and dashboard migration remain future work.

For a worked example of turning a synthetic note into an accepted private task,
see [the source review walkthrough](docs/implementation/0009-private-task-review.md).

Optional bounded browser sessions for the verified API are described in
[implementation 0012](docs/implementation/0012-browser-sessions.md). These require
a compatible verified access token and explicit loopback origin. CI tests their
lifecycle in Chromium with PostgreSQL.

An opt-in generic authorization-code sign-in adapter is documented in
[implementation 0016](docs/implementation/0016-browser-login.md). It is disabled
by default and tested synthetically; no real provider is configured. Review its
token compatibility requirements and suppress callback query access logs before
configuring any provider. The first signed-in workspace screen is available at
`/api/v2/workspace` when browser sessions are enabled. See
[increment 0017](docs/implementation/0017-workspace-screen.md).

The signed-in workspace can create private tasks and edit their details. Apply
`alembic upgrade head` to the workspace database before starting the updated
verified API. See [increment 0018](docs/implementation/0018-manual-task-editing.md).
Task status controls and the Due tasks view are described in
[increment 0019](docs/implementation/0019-task-lifecycle-and-due-view.md).
Open **Private inbox** in the signed-in workspace to capture a synthetic source
and review it into a private task. See
[increment 0020](docs/implementation/0020-signed-in-private-inbox.md).

Open **Notes** in the signed-in workspace to create private sticky notes. Apply
`alembic upgrade head` before starting this version of the workspace API. See
[increment 0024](docs/implementation/0024-private-sticky-notes.md).

Open **Events** under **Work items** in the signed-in workspace to create a
private event, reschedule it, or cancel it. **Today** shows upcoming and ongoing
events. See [increment 0025](docs/implementation/0025-manual-workspace-events.md).
