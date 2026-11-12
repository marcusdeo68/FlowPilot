# FlowPilot

**From conversation to completion.** FlowPilot is a unified work coordination hub for bringing permitted signals from email, chat, notes, and calendars into a shared view of tasks, commitments, events, and approved follow-up actions.

This repository currently contains a local API foundation, a dependency-free dashboard shell, and a deterministic commitment lifecycle. It does not yet connect to email, chat, notes, or calendar providers and does not call an AI model.

## Current foundation

- Same-origin local dashboard served at `/` for Today, inbox, tasks, schedule, and review/send workflow previews.
- Dashboard task capture and lifecycle changes use the existing local API; empty workspaces show non-persisted sample cards.
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
uv run --locked --extra dev python -m build
node --check services/api/src/flowpilot_api/web/app.js
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

Chromium workflow checks and optional local browser setup are documented in
[implementation 0006](docs/implementation/0006-browser-regressions.md). CI also
supports manual dispatch and a daily 10:17 UTC maintenance check.

The separate bearer-verified workspace API is described in
[implementation 0007](docs/implementation/0007-verified-workspace-api.md). It requires
explicit identity/PostgreSQL configuration and does not provide browser login or
replace the local dashboard. Keep both applications on loopback with synthetic data.

Verified-user workspace creation/discovery and owner-only membership management
are documented in [implementation 0008](docs/implementation/0008-workspace-onboarding.md).
This removes manual user/workspace SQL setup once a compatible access token is
available; live sign-in configuration and dashboard migration remain future work.

For a worked example of turning a synthetic note into an accepted private task,
see [the source review walkthrough](docs/implementation/0009-private-task-review.md).
