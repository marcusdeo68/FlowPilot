# FlowPilot maintenance and implementation tracker

Updated: 2026-11-27. This file records implementation evidence, known issues, and
the next increment. Implementation notes explain design; GitHub Actions records
verification for each revision. Update this file when an item's state changes.

## Current checkpoint

- [0048](implementation/0048-open-review-from-today.md) opens a selected
  pending review from Today in the private inbox, including sources outside
  its first page. The general inbox shortcut remains available.
- Increments 0031–0047 merged in [PR #42](https://github.com/marcusdeo68/FlowPilot/pull/42)
  after all seven PR checks passed. The squash commit is `feedb07`.

- The [outsider audit](implementation/0047-schedule-page-consistency.md)
  reproduced duplicate Schedule rows when an already displayed event or
  deadline moved to a later page. The local synthetic preview also ran
  headlessly and displayed the seeded task and event. Final local verification
  of FP-052 through FP-054 on the working tree based on `2db7e43` passed
  368 tests with zero failures, errors, or skips, including 124 PostgreSQL-only
  and 60 Chromium cases. Lint, formatting, types, JavaScript checks, package
  builds, documentation links, and both Linux container rehearsal phases
  passed. The candidate awaits exact-revision GitHub CI and live pilot checks.

- Increment 0046 adds a [hosted image rehearsal](implementation/0046-hosted-image-rehearsal.md)
  to the workspace image job with disposable PostgreSQL. On the working tree
  based on `2db7e43`, the independent local regression report recorded 363 tests,
  zero failures, zero errors, and zero skips. The Linux container rehearsal
  passed before and after migration. Exact-revision CI and live Railway
  verification remain pending.
- Increment 0045 adds [pagination in Due tasks](implementation/0045-due-task-pagination.md)
  with or without a date filter. Independent verification passed all 363 tests
  with zero skips, including 124 PostgreSQL-only and 55 Chromium tests.
  Lint, type checks, package and Linux image builds, JavaScript checks, and
  documentation links passed. GitHub CI for this revision is pending.
- Increment 0044 adds [date filtering in Due tasks](implementation/0044-due-task-date-filter.md)
  and carries the applied date over from Schedule. Independent PostgreSQL and
  Chromium verification passed all 363 tests with zero skips, including 124
  PostgreSQL-only and 55 Chromium tests. Lint, type checks, documentation,
  package and Linux image builds, and the container migration check passed.
  GitHub CI for this revision is pending.
- Increment 0043 adds [date selection and deadline paging](implementation/0043-schedule-deadline-browsing.md)
  in Schedule. The independent run passed all 362 tests with zero skips,
  including 124 PostgreSQL-only and 54 Chromium tests. A separate browser
  check verified recovery after the cursor task was canceled. Lint, type
  checks, package and Linux image builds, JavaScript checks, and documentation
  links passed. GitHub CI for this revision is pending.
- Increment 0042 adds [upcoming task deadlines](implementation/0042-schedule-deadlines.md)
  to Schedule. The preview uses the viewer's local calendar date and the
  existing workspace read permissions. Independent verification passed all 362
  tests with zero skips, including 124 PostgreSQL-only and 54 Chromium tests.
  The preview smoke test, lint, type checks, package and Linux image builds,
  JavaScript checks, and documentation links passed. GitHub CI for this revision
  is pending.
- Increment 0041 adds [workspace Schedule](implementation/0041-workspace-schedule.md)
  for ongoing and upcoming events, sorted by start time. Independent verification
  passed all 361 tests with zero skips, including 124 PostgreSQL-only and 53
  Chromium tests. Lint, type checks, package and Linux image builds, JavaScript
  checks, and documentation links passed. GitHub CI for this revision is pending.
- Increment 0040 adds a [local workspace preview](implementation/0040-local-workspace-preview.md)
  with synthetic sign-in, a sample project, a high-priority task, a private
  note, and an upcoming event. The preview passed in headless and desktop
  Chromium with PostgreSQL. The Docker Compose test database reached healthy
  status with the documented startup command. After a Compose container
  restart interrupted the first full run, the independent rerun passed all
  359 tests with zero skips. Ruff, Pyright, package builds, JavaScript checks,
  Worker tests, and documentation links passed. Exact-revision CI is pending.

- Increment 0039 adds [manual task priorities](implementation/0039-task-priority.md).
  Apply Alembic migration `0011_task_priorities` before starting the updated
  workspace. Independent verification passed 359 tests with zero skips,
  including 123 PostgreSQL-only and 52 Chromium tests. Lint, type checks,
  Python package and Linux image builds, and documentation checks passed.
  Container runtime verification and exact-revision GitHub CI remain pending.
- Increment 0038 adds [workspace project grouping](implementation/0038-workspace-projects.md).
  Apply Alembic migration `0010_workspace_projects` before running the updated
  workspace. Independent verification passed 356 tests with zero skips,
  including 121 PostgreSQL-only and 51 Chromium tests. Lint, type checks,
  Python package and Linux image builds, and documentation checks passed.
  The image's runtime migration check and exact-revision GitHub CI remain pending.
- Increment 0037 adds [task status filtering](implementation/0037-task-status-filter.md)
  in the paginated Work views. The filter works with title search and uses the
  existing task lifecycle and visibility rules. Independent verification passed
  353 tests with zero skips, including 119 PostgreSQL-only and 50 Chromium tests.
  Lint, type checks, package builds, and documentation checks passed. The
  container image check and GitHub CI remain pending.
- Increment 0036 adds [work title search](implementation/0036-work-title-search.md).
  The workspace searches authorized titles before pagination, with the term
  in the request body. No schema migration is needed. Independent verification
  passed all 351 tests, including 118 PostgreSQL-only and 49 Chromium tests,
  with zero skips. An earlier Chromium startup timeout passed on retry and in
  the clean full run. Lint, type checks, package builds, and docs checks passed.
- Increment 0035 adds [Railway-only pilot ingress and public verification](implementation/0035-railway-direct-pilot.md).
  Independent verification passed 349 Python tests with zero skips, including
  117 PostgreSQL-only tests and 48 Chromium tests, plus two Node Worker tests.
  Lint, type checks, package builds, and documentation links passed. The
  reviewer also booted the app with the documented anonymous staging settings
  and confirmed all five expected responses locally.
  Real topology, HTTPS, callback log privacy, and identity remain unverified.
- Increment 0034 adds [authenticated pilot ingress](implementation/0034-authenticated-pilot-ingress.md).
  Independent verification passed 338 Python tests with no skips, two Worker
  tests, lint, formatting, type checks, and the package build. Live provider
  traffic, callback log privacy, and sign-in verification remain pending.
- Increment 0033 adds [idle database connection cleanup](implementation/0033-idle-database-connections.md).
  The optional `FLOWPILOT_DATABASE_POOL=disabled` setting closes PostgreSQL
  connections after each use. Independent verification passed 331 tests with
  zero skips, including 113 PostgreSQL-only and 48 Chromium tests. Lint,
  formatting, typecheck, package build, JavaScript syntax, and documentation
  checks passed. The rebuilt container migrated a disposable schema and left
  zero PostgreSQL sessions open after repeated readiness checks. Live Railway
  sleep and usage measurements are pending.
- Increment 0032 adds [Railway deployment preparation](implementation/0032-railway-pilot.md),
  including a scoped readiness probe and support for Railway's PostgreSQL URL.
  The local container reported readiness after migrating a disposable schema.
  Independent local verification passed 325 tests with zero skips, including
  112 PostgreSQL-only and 48 Chromium tests. Lint, formatting, typecheck,
  package build, JavaScript syntax, and documentation links passed.
  GitHub CI for this working tree, staging, and sign-in verification are pending.
  [Portfolio evidence](PORTFOLIO.md) records implemented skills and unused services.
- Increment 0031 adds [hosted workspace configuration and packaging](implementation/0031-hosted-workspace.md).
  Hosted requests require the configured HTTPS host, and the container includes
  migrations. The image smoke check verified the non-root runtime, timezone
  data, health and readiness behavior, proxy trust defaults, and Alembic head
  `0009_workspace_invitations`. Independent local verification passed all 319
  tests with no skips, including 111 PostgreSQL-only and 48 Chromium tests.
  Live sign-in and deployment infrastructure are pending.
- Increment 0030 adds [workspace sharing](implementation/0030-workspace-sharing.md).
  Authors can review and share tasks and events, and work now supports visibility filters.
- Increment 0029 adds [recipient-consented invitations](implementation/0029-workspace-invitations.md).
  Upgrade the workspace database to `0009_workspace_invitations` before use.
  Merged as `abb2f3f` in [PR #36](https://github.com/marcusdeo68/FlowPilot/pull/36).
  Independent verification passed 303 tests. All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44890351123) passed.
- Increment 0028 adds the signed-in [workspace access view](implementation/0028-workspace-access.md).
  Merged as `48e0d31` in [PR #35](https://github.com/marcusdeo68/FlowPilot/pull/35).
  Independent verification passed 298 tests. All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44888015611) passed.
- Increment 0027 adds [reminder settings](implementation/0027-reminder-settings.md)
  for category, event lead time and future snooze duration in the signed-in tab.
  Independent verification passed 294 tests with no skips, including 103
  PostgreSQL-only and 43 Chromium tests. All local quality checks passed.
  Merged as `7191f6b` in [PR #34](https://github.com/marcusdeo68/FlowPilot/pull/34).
  All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44788723027) passed.
- Increment 0026 adds [opt-in in-app reminders](implementation/0026-in-app-reminders.md)
  for due-today tasks and imminent events. It merged in [PR #33](https://github.com/marcusdeo68/FlowPilot/pull/33)
  as `65526b4` after all six [candidate checks](https://github.com/marcusdeo68/FlowPilot/actions/runs/44786936394) passed.
  All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44787343118) passed.
  Preferences, snooze and dismissals
  are scoped to the workspace and signed-in tab. Independent verification passed
  292 tests with no skips, including 103 PostgreSQL-only and 41 Chromium tests.
  Lint, formatting, build, pinned Pyright, JavaScript syntax and documentation links passed.
- Increment 0025 adds [manual workspace events](implementation/0025-manual-workspace-events.md).
  It merged in [PR #32](https://github.com/marcusdeo68/FlowPilot/pull/32) as `c7c0dcc`.
  Independent verification passed 287 tests, including 101 PostgreSQL-only and
  38 Chromium tests. All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44725777822) passed.
- Increment 0024 adds [private sticky notes](implementation/0024-private-sticky-notes.md).
  Apply migration `0008_private_notes` before using the updated workspace API.
  Merged in [PR #31](https://github.com/marcusdeo68/FlowPilot/pull/31) as `f37cc67`.
  Independent verification passed 281 tests. All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44703461529) passed.
- Increment 0023 adds [upcoming events in Today](implementation/0023-today-upcoming-events.md)
  and merged in [PR #30](https://github.com/marcusdeo68/FlowPilot/pull/30) as `ede9df1`.
  Independent verification passed 275 tests. All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44696407800) passed.
- Increment 0022 adds [recent pending reviews in Today](implementation/0022-today-pending-reviews.md)
  and merged in [PR #29](https://github.com/marcusdeo68/FlowPilot/pull/29) as `1a8f5f5`.
  Independent verification passed 273 tests. All six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44687589352) passed.
- Increment 0021 adds [due work in Today](implementation/0021-today-due-work.md) and
  merged as `8926287` in [PR #28](https://github.com/marcusdeo68/FlowPilot/pull/28).
  All 271 local tests and all six [post-merge jobs](https://github.com/marcusdeo68/FlowPilot/actions/runs/44665476923) passed.
- Increment 0020 merged as `14c3826` in [PR #27](https://github.com/marcusdeo68/FlowPilot/pull/27).
  Both local runs passed 270 tests. All six post-merge checks passed in
  [run 44662271014](https://github.com/marcusdeo68/FlowPilot/actions/runs/44662271014).

- Increment 0020 adds the [signed-in private inbox](implementation/0020-signed-in-private-inbox.md).
  It connects manual source intake, paginated browsing, evidence display, and
  versioned suggestion review to the existing workspace API.
- Increment 0019 merged as `a0900bf` in [PR #26](https://github.com/marcusdeo68/FlowPilot/pull/26).
  All six post-merge checks passed in [run 44658310282](https://github.com/marcusdeo68/FlowPilot/actions/runs/44658310282).

- Increment 0019 adds the [task lifecycle and due view](implementation/0019-task-lifecycle-and-due-view.md)
  in the signed-in workspace, using the existing audit and authorization rules.
  The builder and independent runs passed 265 tests without skips. The pull
  request records the separate recheck of the refresh-feedback fix and CI.

- Increment 0018 merged as `513b438` in [PR #25](https://github.com/marcusdeo68/FlowPilot/pull/25).
  All six post-merge checks passed in [run 44652349255](https://github.com/marcusdeo68/FlowPilot/actions/runs/44652349255).

- Increment 0018 adds [manual task creation and editing](implementation/0018-manual-task-editing.md)
  in the signed-in workspace. Apply audit migration `0007_task_details_audit`
  before starting the updated verified API. Independent local verification on
  the task editor changes based on `02d1c1a` passed 261 tests with zero skips
  (148 ordinary, 91 PostgreSQL, 22 Chromium). Lint, format, typecheck, package
  builds, JavaScript syntax, migration revision and documentation links passed.

- Increment 0017 adds the [signed-in workspace screen](implementation/0017-workspace-screen.md)
  to the verified browser app. It supports selection, creation, paginated work,
  and sign-out with the existing session.

- Increment 0016: [browser login adapter](implementation/0016-browser-login.md)
  adds opt-in provider-neutral redirects, same-origin completion, bounded code
  exchange and strict token/client verification before session issuance. Builder
  and independent full runs passed 251 tests without skips (147 ordinary, 87
  PostgreSQL, 17 Chromium). Ruff, Pyright, package builds, JavaScript syntax and
  documentation link checks passed. Live identity provider setup remains open.
- Increment 0015 merged in PR #17 as `a7dc846`; all six post-merge jobs passed in
  [run 44026104641](https://github.com/marcusdeo68/FlowPilot/actions/runs/44026104641).

- Increment 0015: [login transactions](implementation/0015-login-transactions.md)
  is implemented internally; eight targeted tests passed. Builder and independent
  full suites passed 189 tests with no skips (113 ordinary, 61 PostgreSQL,
  15 Chromium). Independent lint, format, pinned Pyright, sdist/wheel build,
  JavaScript syntax and doc links passed. Exact-candidate CI remains required before merge. No login routes, provider, or new authenticated UI exists.
- Increment 0014 merged in PR #16 as `46cb903`; all six post-merge checks passed
  in [run 44016668450](https://github.com/marcusdeo68/FlowPilot/actions/runs/44016668450).

- Increment 0014: [authorized work pagination](implementation/0014-work-pagination.md)
  is implemented. Additive `work-page` browsing preserves private visibility and
  the existing list contract. Builder and independent full suites passed 181 tests
  with zero skips: 111 ordinary, 55 PostgreSQL, 15 Chromium. Independent lint,
  format, pinned Pyright, sdist/wheel build, JavaScript syntax and doc links passed.
  Exact-candidate CI is required before merge.
- Increment 0013 merged in PR #15 as `6209526`; all six post-merge jobs passed in
  [run 43975170827](https://github.com/marcusdeo68/FlowPilot/actions/runs/43975170827).

- Increment 0013: [local PostgreSQL verification](implementation/0013-local-postgres-tests.md)
  adds a separate synthetic test Compose project on loopback port 5433. Docker
  reports PostgreSQL 17.12 and database `flowpilot_test`. First local full run:
  177 passed, one browser teardown error (FP-013). After the diagnosed fixture fix,
  builder and independent full suites passed all 177 tests without skips. Independent
  lint, format, typecheck, package build and JavaScript syntax passed; dedicated
  PostgreSQL suite passed 51 tests. See the implementation note for commands.

- Development resource recommendations and compact agent handoffs are saved in
  [DEVELOPMENT_RESOURCES.md](DEVELOPMENT_RESOURCES.md), recorded 2026-11-15.
  Docker installation and isolated test database startup are now verified;
  local full-suite verification passed; remaining workflow improvements are planned.

- Increment 0012: [bounded browser sessions](implementation/0012-browser-sessions.md)
  merged as `7ac632b` in [PR #14](https://github.com/marcusdeo68/FlowPilot/pull/14).
  Optional exact loopback origin, opaque hashed
  credentials, token-bounded expiry, CSRF, atomic logout and lifecycle audit are
  implemented. Independent audit signed off source `2e31179` after fixing FP-012.
  Local checks: 124 passed (13 Chromium), 53 real-database checks skipped locally;
  lint, format, build and typecheck passed. All six jobs in
  [run 43495939794](https://github.com/marcusdeo68/FlowPilot/actions/runs/43495939794)
  passed: 111 ordinary tests per platform/Python combination, 51 PostgreSQL checks
  and 15 Chromium workflows. Final candidate `05ee451` passed all six jobs in
  [run 43500166899](https://github.com/marcusdeo68/FlowPilot/actions/runs/43500166899)
  before merge. No sign-in UI, real provider or live account is connected.

- Earlier product planning named Gmail, Google Calendar, Slack, and Google Keep.
  Increment 0024 established native Notes. Configurable popup reminders, task
  organization, and approved email and Slack composition remain product goals.
  [Product intent](PRODUCT.md#intended-integrations-and-capabilities),
  [roadmap](ROADMAP.md) and [security boundaries](SECURITY.md) capture the scope;
  notification delivery remains open.

- Engineering workflow: [PR #11](https://github.com/marcusdeo68/FlowPilot/pull/11)
  makes `AGENTS.md` load the [engineering guardrails](ENGINEERING_GUARDRAILS.md)
  at startup. Each deliverable requires a read-only planner, independent audit
  and live verification; a debugger investigates repeated unexplained failures.
  Merged as `8ca01e7` after independent review.
  [Run 43378096613](https://github.com/marcusdeo68/FlowPilot/actions/runs/43378096613)
  verified final candidate `2cd4d56`: all six jobs passed, including 88 ordinary tests,
  43 PostgreSQL checks, six Chromium workflows, and zero Pyright diagnostics.
  Local lint, formatting, typecheck, build and six Chromium workflows also passed.
  [Post-merge run 43378664219](https://github.com/marcusdeo68/FlowPilot/actions/runs/43378664219)
  passed all six jobs for merged `8ca01e7`.

- The [application typecheck](implementation/application-typecheck.md) runs the
  pinned Pyright command alongside lint and tests. The initial audit found nine
  diagnostics in identity configuration, route annotations and stored work parsing.

- Increment 0010: [manual-source inbox](implementation/0010-private-source-inbox.md)
  merged in [PR #9](https://github.com/marcusdeo68/FlowPilot/pull/9).
  [All six jobs passed](https://github.com/marcusdeo68/FlowPilot/actions/runs/43308565337),
  including the PostgreSQL source privacy, pagination and signed HTTP tests.
- Increment 0011: [dashboard focus](implementation/0011-dashboard-focus.md)
  fixes FP-011 in [PR #10](https://github.com/marcusdeo68/FlowPilot/pull/10).
  Reconciled with current main; loading, retry, overlapping responses and browser
  calendar dates have focused Chromium regressions (13 Chromium workflows passed
  locally). The PR records independent verification, exact-candidate CI and merge
  history; those checks are required before sign-off.
- Increment 0009: [private task review](implementation/0009-private-task-review.md)
  merged in [PR #8](https://github.com/marcusdeo68/FlowPilot/pull/8).
  [Run 43307757893](https://github.com/marcusdeo68/FlowPilot/actions/runs/43307757893)
  passed all six jobs for fedca96, including the real PostgreSQL review tests.
  Local suite: 91 passed, 40 PostgreSQL checks skipped locally.

- Foundation and verification increment merged in [PR #1](https://github.com/marcusdeo68/FlowPilot/pull/1).
- 38 tests passed locally and in the Windows/Linux Python 3.11/3.12 CI matrix for
  the PR revision. Lint, formatting, package builds, and JavaScript syntax passed.
- SQLite dashboard is local-only with synthetic/manual data. Its HTTP endpoints
  are not yet wired to verified identity or the separate PostgreSQL service.
- PostgreSQL migration and internal authorized work/source services merged in
  [PR #4](https://github.com/marcusdeo68/FlowPilot/pull/4): 16 real PostgreSQL
  integration checks and 39 ordinary tests passed. The legacy HTTP API is separate.
- Browser maintenance increment merged in
  [PR #5](https://github.com/marcusdeo68/FlowPilot/pull/5). All six CI jobs passed:
  four platform/Python combinations, PostgreSQL, and Chromium. Local verification
  passed 45 tests including six browser workflows; PostgreSQL's 16 tests passed in CI.
- Increment 0007's separately configured bearer-verified workspace API merged in
  [PR #6](https://github.com/marcusdeo68/FlowPilot/pull/6). Run 43227745975 passed
  76 ordinary/backend/token tests, 20 PostgreSQL/API tests, and six Chromium tests,
  plus lint, formatting, package builds, and JavaScript syntax. Local full suite
  passed 82 tests; 20 real-database checks ran in CI. The demo remains separate.
- Run and verification commands: [README](../README.md). Design:
  [implementation 0004](implementation/0004-verification-and-access-policies.md).
- Increment 0008's verified-user workspace onboarding and versioned owner-only
  membership administration merged in [PR #7](https://github.com/marcusdeo68/FlowPilot/pull/7).
  Run 43285798866 passed all six jobs: 81 backend/contract tests, 35 real
  PostgreSQL/service/API tests, and six Chromium workflows, plus lint, formatting,
  package builds, and JavaScript syntax. Local full suite: 87 passed, 35 real-database
  checks explicitly skipped. Updated Python 3.12.16 environment verified unchanged.

## Open issues and verification gaps

| ID | Type / status | Evidence and impact | Next action / closure evidence |
| --- | --- | --- | --- |
| FP-009 | Coverage expansion / planned | Chromium covers the local workflow; Firefox/WebKit, mobile navigation, visual comparison, and full accessibility auditing are not yet covered. | Add these checks alongside the upcoming authenticated frontend. No unverified accessibility claim. |
| FP-010 | Deployment readiness / planned | The signed-in workspace has hosted transport and container coverage with synthetic identity. Live identity configuration, invitation delivery, request limits, session retention, and production database roles and operations remain incomplete. | Keep staging synthetic and verify transport, sign-in, and workspace isolation through the actual load balancer before using real accounts. |
| FP-043 | Railway staging verification gap | Railway does not publish a stable edge peer range and private service requests bypass the HTTP edge. [0035](implementation/0035-railway-direct-pilot.md) limits the pilot to a trusted, dedicated environment. | Verify actual public ingress, private reachability, and callback log privacy with synthetic staging before hosted sign-in. |
| FP-044 | Railway idle usage / verification gap | Railway counts outbound traffic for inactivity, and persistent database connections can interfere with sleep. [0033](implementation/0033-idle-database-connections.md) removes the app's retained connections when enabled. | Verify sleep, first authenticated request latency, and combined app and database usage in Railway staging. |

Do not put secrets, message bodies, or private customer data in reproductions.
New confirmed defects get a stable FP identifier, reproduction steps or a failing
test, impact, next action, and a linked fix with passing regression evidence.
Keep resolved entries so the reason for a fix remains discoverable.

## Resolved setup and behavior issues

| ID | Resolution | Evidence |
| --- | --- | --- |
| FP-054 | Clear old Work filters when following an accepted inbox task. | The browser workflow sets project, Completed, and High filters before accepting an open task, follows **Go to work list**, and checks the filters and the resulting task row. |
| FP-053 | Clear stale workspace data and the cached write role after forbidden task, project, event, or sharing actions. | A denied task change in Today could leave review and event titles visible. A denied project creation in Work could leave project names and write controls visible. Regression cases cover stale responses and task and project write denials. |
| FP-052 | Restart the affected Schedule list if a later page repeats a visible ID. | Move a visible deadline or event across the page boundary in another session, then load more. Chromium checks the retry, preserved sibling panel, and current ordering. |
| FP-051 | Restart Due tasks if a task moves across the page boundary. | The audit found that rescheduling an already listed task could repeat it with an older version still on screen. Chromium reschedules a listed task before paging and verifies that retry shows it once in the new position. |
| FP-050 | Clear the Schedule deadline preview when an event or sharing request is denied. | The audit found that a 403 on an event change could leave task titles visible after workspace access ended. Chromium denies an event change and verifies that both lists clear until workspace refresh. |
| FP-049 | Keep the Schedule cursor event stable through the page query. | The audit found that a reschedule between the cursor check and page query could repeat the cursor event. PostgreSQL coverage verifies that a competing writer cannot lock that row until the page query finishes. |
| FP-048 | Clear cached project names when the active workspace rejects work access. | The project list is cached per workspace. A current 403 now clears the cache, and Chromium verifies the selector no longer shows project names. |
| FP-047 | Preserve a task's project when a tab has an older project list. | A task can reference a project created from another session. The editor retains its project ID when the catalog has yet to refresh. Chromium verifies that editing the title keeps the assignment. |
| FP-046 | Reload a status-filtered page after a task moves to a new status. | A Chromium regression found that starting a task left it displayed in the Open filter because the browser replaced only that row. It now checks that the task leaves Open and appears under Active. |
| FP-045 | Return a clean validation error for malformed Unicode. | The search audit found that a lone escaped surrogate led FastAPI's validation response to fail while encoding it. A PostgreSQL HTTP regression sends the same payload and verifies a 422 response. |
| FP-042 | Accept a standard PostgreSQL URL for the app and migrations. | The engine rejected hosting URLs beginning with `postgresql://`. Coverage verifies psycopg selection with both accepted schemes and preservation of connection options and escaped credentials. |
| FP-041 | Allow the hosted proxy test to dispose of its synthetic SQLite connection after the readiness request. | The audit reproduced a swallowed SQLite thread-affinity error at cleanup. The focused pytest run with error-level logging passes without the cleanup error. |
| FP-040 | Make the public listener's probe rules and the migration requirement explicit. | The audit confirmed that a trusted public route can reach the app's probe paths unless the listener blocks them. AWS also documents fail-open when all targets are unhealthy. [0031](implementation/0031-hosted-workspace.md) records both constraints and the staging checks. |
| FP-039 | Keep canceled events free of work actions. | The existing Chromium lifecycle caught a Share button after cancellation. The fix keeps browser sharing available for scheduled events and preserves the terminal action check. |
| FP-038 | Enable author edits from Shared work. | Audit found that hiding the create button also stopped the visible edit action. Chromium verifies editing both shared tasks and events and restoring edit focus on cancel. |
| FP-037 | Recover an accepted workspace outside the bounded list. | Audit found that accepting a workspace beyond the first 100 could leave it out of the selector. Chromium omits the workspace on acceptance and on refresh and verifies an active-membership read supplies its current role. |
| FP-036 | Observe live waiting locks in the invitation expiry test. | The first local run missed the worker under a transaction-cached activity snapshot. The regression checks live PostgreSQL locks, holds the unchanged row past expiry and verifies acceptance fails. |
| FP-035 | Clear expired reminders while a poll is pending. | Audit found that a network delay could leave an already-started event or previous-day task visible. Chromium holds a request across both cutoffs and checks that the popup clears each expired title. |
| FP-034 | Compare retained event instants in UTC. | With PostgreSQL set to America/New_York, an event crossing the fall clock change appeared to end before it started. The integration regression uses a non-UTC session, preserves the valid interval and checks that a repeated edit stays a no-op. |
| FP-033 | Preserve untouched event instants when rescheduling. | Audit reproduced a one-hour change to the start when the browser and server disagreed about Havana's offset and the user moved only the end. The Chromium regression simulates offset disagreement and checks the original start survives. |
| FP-032 | Publish the actual local timestamp format in OpenAPI. | The first event candidate advertised RFC 3339 date-time fields that commonly include an offset. The PostgreSQL-backed HTTP test checks the generated pattern accepts the local payload and rejects an offset. |
| FP-031 | Protect an open note draft during workspace operations. | Review found that changing or refreshing the workspace could clear an editor or a pending save. Chromium verifies the workspace controls unlock only after the Notes editor closes. |
| FP-030 | Clear both Today lists after a current workspace access denial. | The two reads can finish in either order during a permission change. Chromium returns a successful pending-review response after a 403 and verifies the private title stays hidden. |
| FP-029 | Pause suggestion review when the date field contains a partial entry. | Chromium can show part of a date while reporting an empty value. The browser regression verifies it blocks acceptance until the entry is completed or cleared. |
| FP-028 | Require a fresh workspace role before showing inbox write controls after a 403. | Review traced a member-to-observer downgrade followed by a successful inbox refresh using a stale role. Chromium verifies the user can reread their source while writes stay hidden. |
| FP-027 | Pause Work items navigation while an inbox write is pending. | Opening Work items before an acceptance committed could show a list without the new task. Chromium holds the review response and verifies the Work items button is paused until the request settles. |
| FP-026 | Preserve the confirmed save message when a work-list reload fails. | Audit traced the Due tasks refresh error clearing the confirmation after a successful status write. Chromium returns a 503 on the refresh and checks both the confirmation and the retry prompt. |
| FP-025 | Pause work-view switching during a pending status save. | Audit traced an old status appearing when the new view read before the write committed. Chromium checks that the selector pauses on save and permits view changes after a conflict. |
| FP-024 | Keep saved text when the corresponding editor field is unchanged. | Review found that loading a title or description into a browser field can normalize line endings. The Chromium test edits only the due date and checks that both original CRLF values are preserved. |
| FP-023 | Make editor fields read-only while a save is pending. | Review found that typing after submission could lose later edits when a successful save closed the form. The Chromium test pauses the PATCH and checks all fields before releasing it. |
| FP-022 | Compute elapsed time before subtracting it from the OAuth response budget. | Windows Python 3.11 post-merge run 44591896009 passed a timeout of `5.000000000000028` to the socket. A frozen-clock transport regression reproduced the same rounding error with the strict five-second assertion. |
| FP-020 | Ignore obsolete work responses before processing session errors. | Review found a delayed 401 from the previous selection could clear the current view. The new Chromium test holds an old 200 or 401 until the new list is visible. |
| FP-021 | Include a newly created workspace in the current selection even when the capped list omits it. | Review traced creation of a name sorted past the first 100 through the alphabetical API list. The UI now includes and selects the authorized creation response, then loads work through the membership-checked API. |
| FP-019 | Callback GET and rejected cross-origin completion leave login cookies untouched. | Independent review found unsolicited requests could cancel pending sign-in. HTTP regressions assert no cookie deletion and no exchange for those requests. |
| FP-018 | Browser form pages use `strict-origin` referrers. | Chromium first rejected a legitimate form POST with null Origin. Real HTTPS provider journeys now verify exact Origin, origin-only referrer, and incumbent Strict cookie preservation. |
| FP-017 | Login checks the expected client during strict token verification. | Existing session round-trip tests caught the extra identity field. Restoring the original result shape preserved their assertions and the new wrong-client check passed. |
| FP-016 | Deadline checks avoid adjusting sockets closed after response EOF. | An independent real-socket probe reproduced a valid JSON response rejected on Windows. The `Connection: close` success regression passes. |
| FP-015 | Code exchange applies a response deadline that interrupts the connection. | Real socket tests exercise slow headers and body while the connection remains active. Connection and DNS limits are documented in [0016](implementation/0016-browser-login.md). |
| FP-014 | Pending-login expiry is checked after acquiring the row lock. | Independent audit and failing regression reproduced consumption after expiry while waiting on an unchanged row lock. Lock-first fix passed eight focused tests and independent full suite of 189 without skips. |
| FP-013 | Windows session-test server uses a fixture-local Selector loop to avoid Proactor reset cleanup leaking server connections. No assertion removed. | Reproduced twice before fix; debugger confirmed leaked active counts. Independent focused suite passed twice and full PostgreSQL/Chromium run passed all 177 tests with no skips. |
| FP-012 | Cookie-name normalization now matches the framework; whitespace cannot hide duplicate or mixed credentials. | Independent audit reproduced five failing regressions before the fix. All five and signed HTTP regressions pass in `2e31179`; independent re-review and all six CI jobs in run 43495939794 passed. |
| FP-003 | GitHub CLI and repository connection verified | Initial push succeeded; PR #1 created and merged using CLI. Sandboxed credential access can still differ from normal host access. |
| FP-011 | An empty DB showed 1 due task; outages showed sample tasks. Due counts over recent rows also missed older records. | Chromium initially failed with expected 0, actual 1. The focus endpoint now counts persisted work; empty, outage/retry, and older-due-item regressions pass locally. |
| FP-004 | Python/PATH dependency addressed for this checkout | Managed `.venv`, committed dependency lock, and Cursor process tasks; fresh CI environments passed. |
| FP-005 | Completion no longer silently confirms a commitment | Dashboard exposes individual Confirm/Start/Complete actions; browser regression passed in PR #5. |
| FP-006 | Environment moved outside sync directory after locks recurred | Copy mode alone did not solve repeated update failures. Fresh environment now lives under local application data, linked by `.venv`; old/residual files are preserved and ignored. See implementation 0007. Exact lock origin remains unconfirmed. |
| FP-001 | Supported TestClient dependency, without warning suppression | httpx2 regression suite passed in PR #5 on Windows/Linux Python 3.11/3.12. |
| FP-002 | Real-browser workflow job implemented | Six Chromium checks passed locally and in CI in PR #5. See FP-009 for remaining coverage. |
| FP-007 | Empty dialog cancellation fixed | Required-title validation no longer blocks Cancel/Close; reproduced failing test now passes in Chromium. |
| FP-008 | Readable server validation errors and recovery | Structured error fields render as text; form remains open and Save re-enables. Chromium regression passed. |

## Next implementation milestones

These are planned capabilities, not reported bugs. Stage 1 is incomplete.

1. PostgreSQL storage/service slice implemented in
   [implementation 0005](implementation/0005-postgres-work-storage.md), merged and
   CI verified. Includes seven tables, workspace-qualified relationships,
   stored-membership authorization, private sources, evidence sharing, and audit
   transactions. Remaining Stage 1 tables and live identity-provider setup are still planned.
2. Increment 0007's signed-access-token API and PostgreSQL HTTP checks are verified.
   Workspace creation/discovery and member administration are verified in 0008.
   Increment 0012 adds optional browser sessions and 0016 adds opt-in browser
   login with synthetic provider coverage. The signed-in workspace and invitation
   acceptance are implemented with synthetic coverage. Next verify compatible
   identity, the HTTPS edge, and workspace isolation in synthetic staging.
3. Private task review (0009) and manual source discovery (0010) now have API
   implementations. Increment 0020 added interactive inbox review and
   authenticated Chromium coverage for capturing a source and accepting a task.
4. Verify an isolated Railway deployment with synthetic data and the free
   allowance. Review access controls before inviting friends or connecting any
   live provider.

## Check cadence and handoff

- During implementation: targeted tests after meaningful behavior changes; record
  discovered issues here and add regression tests for confirmed defects.
- Before merge: applicable lint/format/tests/build checks and successful CI for
  the exact revision. Record what was not tested.
- After merge: verify the PR merged and local main matches remote. Inspect any
  failed main-branch checks before building on that revision.
- Dependencies: weekly Dependabot update PRs are configured. GitHub vulnerability
  alerts and security-update PRs are enabled. Updates require normal validation.
- Between sessions: there is no scheduled development agent, uptime monitor, or
  continuous bug triage process. CI is configured for main pushes/PRs, manual runs,
  and a daily 10:17 UTC check; it does not watch a running application. The daily
  schedule has not yet been observed firing. Add deployment monitoring when there
  is a deployed environment.
