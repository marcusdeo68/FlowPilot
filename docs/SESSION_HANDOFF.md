# Session handoff

The [portfolio walkthrough](implementation/0049-workspace-demo.md) is
available without a running server. Live staging verification still requires
the Railway pilot's assigned HTTPS origin.

## Open a review from Today

[0048](implementation/0048-open-review-from-today.md) connects a pending
suggestion on Today to its private inbox detail view.

## Outsider audit

[0047](implementation/0047-schedule-page-consistency.md) covers browser
edge cases found during the independent audit. See [STATUS](STATUS.md) for
the local sign-off and outstanding hosted and browser coverage.

## Latest increment — hosted image rehearsal

[0046](implementation/0046-hosted-image-rehearsal.md) exercises the packaged
Linux app in Railway mode before and after migration. The same check is
configured in GitHub Actions. Live staging still needs the pilot’s assigned
Railway HTTPS URL and an isolated environment.

## Previous increment — page through Due tasks

[0045](implementation/0045-due-task-pagination.md) adds **Load more** to Due
tasks with or without an applied date filter.

## Previous increment — filter Due tasks by date

[0044](implementation/0044-due-task-date-filter.md) carries the applied date
from Schedule into Due tasks and lets users change or clear it there.

## Previous increment — browse deadlines in Schedule

[0043](implementation/0043-schedule-deadline-browsing.md) adds a start date and
deadline paging to Schedule. Today and Due tasks keep the existing API.

## Previous increment — deadlines in Schedule

[0042](implementation/0042-schedule-deadlines.md) adds a preview of unfinished
tasks due today or later, using the viewer’s local calendar date. **Open due
tasks** links to the existing task management view.

## Previous increment — workspace Schedule

[0041](implementation/0041-workspace-schedule.md) pages through ongoing and
upcoming manual events by start time. Choose **Schedule** in **Work view** or
**Open schedule** on Today. This increment requires no database migration.

## Previous increment — local workspace preview

[0040](implementation/0040-local-workspace-preview.md) opens the signed-in
workspace in desktop Chromium with sample records in a disposable schema.
The Railway pilot and live identity setup remain separate work.

## Previous increment — task priorities

[0039](implementation/0039-task-priority.md) adds Low, Normal, and High task
priorities and a combined Work filter. Upgrade to `0011_task_priorities` before
starting the workspace.

## Previous increment — workspace projects

[0038](implementation/0038-workspace-projects.md) adds project creation, task
assignment, and the Work items project filter. Upgrade the workspace database
to `0010_workspace_projects` before starting the updated application.

## Previous increment — task status filtering

[0037](implementation/0037-task-status-filter.md) adds status filtering in the
paginated task views and combines it with title search.

## Previous increment — work title search

[0036](implementation/0036-work-title-search.md) adds title search in the
signed-in Work views. The Railway pilot remains ready for synthetic staging
checks once hosting is available.

## Previous increment — Railway-only pilot

[0035](implementation/0035-railway-direct-pilot.md) adds the direct Railway
mode and its public HTTPS smoke check. Begin with synthetic staging in a
dedicated Railway environment. Live sign-in and usage measurements are pending.

## Previous increment — authenticated pilot ingress

[0034](implementation/0034-authenticated-pilot-ingress.md) adds the locally
tested Worker and backend credential check as an optional deployment path.

## Previous increment — idle database connections

[0033](implementation/0033-idle-database-connections.md) adds an optional
connection mode for a low-traffic pilot. Verify Railway sleep and usage in
staging. Public proxy trust and compatible sign-in remain the next launch checks.

## Previous increment — Railway portfolio pilot preparation

Target a free Railway pilot with synthetic data and a small group of invited
friends after staging passes. [0032](implementation/0032-railway-pilot.md)
records configuration and outstanding checks. The owner needs to connect
Railway to the FlowPilot repository when staging is ready. Public proxy trust
and compatible sign-in require live verification. Use [PORTFOLIO](PORTFOLIO.md)
to distinguish implemented skills from the earlier AWS proposal.

## Previous increment — hosted workspace foundation

Increment 0031 adds opt-in HTTPS workspace hosting and a non-root image.
See [0031](implementation/0031-hosted-workspace.md) for the generic host
and proxy trust design.

## Previous increment — workspace sharing

Increment 0030 adds [review and sharing](implementation/0030-workspace-sharing.md)
for private tasks and events, with Shared work and My private work filters.
See [STATUS](STATUS.md) for verification. Next, improve task organization or
finish the operational controls for a live pilot.

## Previous increment — recipient-consented invitations

Increment 0029 adds signed-in profile registration, owner-managed offers, and
recipient decisions for synthetic workspace invitations. Apply migration
`0009_workspace_invitations` to use the updated workspace API. See
[0029](implementation/0029-workspace-invitations.md) and [STATUS](STATUS.md).

## Previous increment — signed-in workspace access

Increment 0028 adds the signed-in [workspace access view](implementation/0028-workspace-access.md).
Owners can manage roles, grants and existing memberships and review history.
See [STATUS](STATUS.md) for verification.

## Previous increment — reminder settings

Increment 0027 lets users control which reminders appear, how far ahead to show
events, and how long to snooze the next group. See
[0027](implementation/0027-reminder-settings.md) and [STATUS](STATUS.md).

## Previous increment — in-app reminders

Increment 0026 adds an opt-in popup for tasks due today and events starting
within 15 minutes in the signed-in workspace. See
[0026](implementation/0026-in-app-reminders.md) and [STATUS](STATUS.md).

## Previous increment — manual workspace events

Increment 0025 adds the signed-in event editor, event list and cancellation.
Today links to Events under Work items. See [0025](implementation/0025-manual-workspace-events.md)
and [STATUS](STATUS.md).

## Previous increment — private sticky notes

Increment 0024 provides native private Notes. Apply `alembic upgrade head` to
the configured workspace database before starting the updated API. See STATUS
for verification.

## Previous increment — upcoming events in Today

Increment 0023 shows up to five scheduled events in the next seven days,
including events already in progress. Existing signed API clients can create
manual events. See STATUS for validation. Next, add a manual event entry form.

## Previous increment — pending reviews in Today

Increment 0022 puts a recent private review list alongside due tasks in Today.
Review decisions remain in Private inbox. See STATUS and the PR for validation.
The next increment can add upcoming calendar events to signed-in Today.

## Previous increment — due work in Today

Increment 0021 adds overdue and due-today tasks to signed-in Today. See STATUS
for verification. The next increment is pending private reviews in Today.

## Latest increment — signed-in private inbox

Increment 0020 connects private manual sources and task suggestion review to
the signed-in workspace. It uses the existing PostgreSQL schema and synthetic
login setup. See STATUS for verification. Next, bring due work and review items
into a signed-in Today view.

## Latest increment — task lifecycle and due view

Increment 0019 completes the signed-in manual task lifecycle and adds a bounded
view of unfinished tasks ordered by due date. It uses the existing 0007 schema.
See STATUS and the PR for verification. Next, connect the authenticated private
inbox review workflow. Check external prerequisites while planning that work.

## Latest increment — manual task editing

Increment 0018 adds private task capture and creator-only task detail edits in
the signed-in workspace. Apply migration 0007 before starting the API. The
independent local run passed 261 tests with zero skips. See STATUS and the PR for
verification. Next, add task status controls or the private inbox review surface.
Live identity provider setup remains pending.

## Latest increment - signed-in workspace screen

Increment 0017 builds on merged PR #22 and adds a same-origin workspace screen
at `/api/v2/workspace`. It can create and select workspaces, page through authorized
work and sign out with the existing browser session. Live identity provider setup
remains pending. See STATUS and the PR for verification on the reviewed revision.
Next, build an authenticated manual work or private review workflow.

## Latest increment - browser login adapter (2026-11-19)

Base `a7dc846` is merged main (PR #17, post-merge CI 44026104641 all six passed).
User authorized next autonomous increment without preference/approval prompts.
0016 adds default-disabled generic code/PKCE login: trusted endpoint config,
same-origin initiation, Lax verifier cookie, script-free callback form, same-origin
completion POST, one-time consume/exchange, strict token/client checks, opaque
session issuance. No live provider is configured and no provider data is connected.
Local full verification passed 251 tests with no skips. See STATUS for review
findings FP-015 through FP-019 and follow the PR for CI on the reviewed revision.
Preserve unrelated `.playwright-mcp/`.

Next: authenticated workspace onboarding/selection using synthetic browser tests,
and real provider compatibility review when account resources are available.
No scheduled development process runs after this session ends. Earlier checkpoints
below are historical.

## Latest increment - pending login transactions

User authorized autonomous development. Base `46cb903` is merged main; PR #16
and post-merge run 44016668450 passed all six jobs. Increment 0015 adds internal
digest-only state/PKCE login transactions, fixed expiry, atomic consumption and
append-only audit. Eight targeted tests passed. Independent full suite: 189 passed, no skips.
Audit found FP-014 expiry-under-lock race; regression reproduced and lock-first
fix passed. Independent lint, format, typecheck, build, JavaScript syntax and doc
links passed. Inspect exact-revision PR CI before merging. Apply migration 0006 before
starting the workspace API. No HTTP login routes, provider or live accounts exist.

Next is a reviewed authorization redirect/callback adapter, bounded token exchange,
unchanged strict access-token verification, then session/UI wiring with synthetic
browser tests. Keep provider compatibility/scopes/privacy review explicit; no
credentials or live provider data have been introduced. `.playwright-mcp/` is an
unrelated local artifact to preserve. Earlier checkpoints below are historical.

## Latest increment - work pagination

User authorized the next autonomous development increment. Base `6209526` is
merged main with all six CI checks passed. Increment 0014 adds an authorized,
creation-order cursor endpoint for work browsing beyond 100 rows, preparing the
future task screen while sign-in/provider configuration remains pending.
Independent full suite: 181 passed, no skips (111 ordinary, 55 PostgreSQL,
15 Chromium). Lint, format, typecheck, sdist/wheel build and documentation links passed; final CI
and commit/PR evidence must be checked before merge. Read STATUS and the 0014
implementation note for final evidence. Preserve unrelated `.playwright-mcp/`.
No ongoing background worker is configured; this handoff records session work.

## Current checkpoint - 2026-11-16

User resumed development and deferred further GitHub remote MCP troubleshooting.
Docker engine 29.9.3 is running. Increment 0013 adds `compose.test.yaml`, a separate
`flowpilot-tests` project, PostgreSQL 17.12, `flowpilot_test`, dedicated test volume
and loopback port 5433. Test startup is verified. First full local suite had 177
passed and one Windows browser teardown error (FP-013); the diagnosed fixture
fix now passes all 177 locally and independently, without skips. Independent
lint, format, typecheck, build and JavaScript syntax checks also passed.

PR14 merged as 7ac632b after all six CI jobs passed for exact candidate 05ee451.
Current branch: chore/local-postgres-tests, based on merged main. No product
integration or live sign-in was added. The increment is prepared for its own PR;
verify current PR state and exact-revision CI before any merge.
Preserve pending resource docs and unrelated `.playwright-mcp/` local artifact.
Next: reconcile/merge the reviewed test-environment increment with
exact-revision CI, then plan the next access-model/UI roadmap slice. At this
checkpoint the planned integrations included Keep. See the current roadmap
for the native Notes decision and remaining integration targets.

The earlier restart checkpoint below is historical; Docker and Playwright status
have since advanced. Playwright MCP navigation was successfully exercised after
restart; its generated local snapshot is not product code.

## Historical pre-restart checkpoint

Recorded: 2026-11-15. Read AGENTS.md and ENGINEERING_GUARDRAILS.md before work.

## Immediate user request and next action

User installed Docker Desktop and ran `wsl --install`. They want the next setup
step and to resume this conversation after restarting Windows. Focus on making
local PostgreSQL tests work before adding the other proposed supplements.

Verified on this machine before restart:

- WSL reports default version 2. It also prints a WSL1 optional-component warning;
  Docker's selected path is WSL2. Full runtime readiness is not established.
- Docker CLI is installed at
  `C:\Users\marcu\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`.
- Docker CLI version is 29.9.3, context `desktop-linux`.
- Docker engine is unavailable: dockerDesktopLinuxEngine named pipe not found.
  Restart Windows, open Docker Desktop and wait for engine readiness, then verify
  `docker version` reports both Client and Server and `docker compose version` works.
- Use Docker Desktop's WSL2 engine / Linux containers. A separate native
  PostgreSQL installation is unnecessary for the chosen approach.

Next implementation: read-only planner first, then add a separate PostgreSQL 17
test service/database ending `_test` and run the real integration/browser checks.
Existing compose.yaml defines `flowpilot_dev` only; NEVER use it as the test DB.
Keep listeners on loopback and use synthetic data. No Compose changes or database
startup have been performed in this setup conversation.

## Repository checkpoint

- Branch: feat/browser-sessions.
- HEAD: 05ee451269897da5eadc678ee0f7030168dda4cf.
- PR14 is OPEN, unmerged as last checked through GitHub on 2026-11-15.
  It previously received independent sign-off and all six final-candidate CI jobs
  passed. Recheck head/base/status before any authorized merge; do not claim merged.
- Browser sessions are implemented in implementation/0012-browser-sessions.md.
  No real provider, sign-in/callback, authenticated dashboard or live data is ready.
- Last independent local suite: 124 passed, 53 database-dependent skips.
  Exact candidate CI: 111 ordinary tests per matrix job, 51 PostgreSQL tests and
  15 Chromium workflows. These are historical results, not a post-restart run.
- Uncommitted documentation: STATUS.md updated; DEVELOPMENT_RESOURCES.md and
  this SESSION_HANDOFF.md are newly saved. Preserve these changes.

## Resource/workflow decisions

DEVELOPMENT_RESOURCES.md saves priorities, verified tool states, agent roles,
compact handoff template and verification/report proposals. Its links and content
were independently checked; no workflow or application implementation was added.

Priority: local PostgreSQL tests, compact context/handoffs, concise verification
reports, failure-only Playwright traces/artifacts, Context7, optional Playwright
CLI evaluation, optional later Serena trial. Context7 connection is unconfirmed.

## Codex and MCP recovery

Codex CLI supports `codex resume` (picker), `codex resume --last`, and
`codex resume --all`. Run from this repository. Use `--no-daemon` if a reused
background server lacks newly set environment variables.

GitHub MCP initially failed because the PAT was supplied as a variable name.
Configuration now correctly reads GITHUB_TOKEN. User verified the replacement
token via GitHub and confirmed MCP connected with `codex --no-daemon`.
The old daemon lacked GITHUB_TOKEN despite the parent PowerShell having it.
Session-only environment variables do not survive restart: enter credentials
securely again if necessary. Do not put token values in docs, commands or chat.
This chat separately has an authenticated GitHub plugin connection.

Playwright MCP is configured and enabled as `npx @playwright/mcp@latest`.
A direct MCP initialization/tool-list probe passed and returned 25 tools. This
chat had no exposed Playwright MCP tools; actual browser navigation via MCP was
not tested. OpenAI Developers is confirmed installed. Existing pytest/Chromium
regressions remain the verification suite.

## Resume prompt

Read docs/SESSION_HANDOFF.md, docs/DEVELOPMENT_RESOURCES.md and the repository
instructions. Verify Docker/WSL after restart, then continue the local PostgreSQL
test environment as one scoped, independently verified increment. Preserve the
pending docs and recheck PR14 status before any repository reconciliation.
