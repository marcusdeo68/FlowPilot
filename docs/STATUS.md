# FlowPilot maintenance and implementation tracker

Updated: 2026-11-20. This file records implementation evidence, known issues, and
the next increment. Implementation notes explain design; GitHub Actions records
verification for each revision. Update this file when an item's state changes.

## Current checkpoint

- Increment 0025 adds [manual workspace events](implementation/0025-manual-workspace-events.md).
  Events can be created, browsed, rescheduled and canceled in the signed-in workspace.
  The existing work schema supports the increment. In-app reminders are next.
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
| FP-010 | Deployment readiness / planned | Verified API, onboarding/admin API, browser sessions, and the opt-in sign-in adapter have synthetic coverage. Live identity configuration, invitation consent, request limits, session retention, and production database roles/operations remain incomplete. | Keep loopback/synthetic-only; verify each capability before network exposure. |

Do not put secrets, message bodies, or private customer data in reproductions.
New confirmed defects get a stable FP identifier, reproduction steps or a failing
test, impact, next action, and a linked fix with passing regression evidence.
Keep resolved entries so the reason for a fix remains discoverable.

## Resolved setup and behavior issues

| ID | Resolution | Evidence |
| --- | --- | --- |
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
   login with synthetic provider coverage. Next choose and configure a compatible
   identity provider, implement invitation acceptance, and migrate the dashboard.
3. Private task review (0009) and manual source discovery (0010) now have API
   implementations. Next: interactive review and authenticated browser coverage.
4. Only after access controls: provider review and one read-only pilot. AWS
   provisioning also needs an agreed spending limit and deployment readiness.

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
