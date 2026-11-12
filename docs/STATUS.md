# FlowPilot maintenance and implementation tracker

Updated: 2026-11-12. This file records implementation evidence, known issues, and
the next increment. Implementation notes explain design; GitHub Actions records
verification for each revision. Update this file when an item's state changes.

## Current checkpoint

- Increment 0010: [manual-source inbox](implementation/0010-private-source-inbox.md)
  adds a paginated, owner-only read model with proposal status.
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
| FP-010 | Deployment readiness / planned | Verified API and onboarding/admin API are implemented and tested. Live identity configuration, browser login/session, invitation consent, request limits, and production database roles/operations remain incomplete. | Keep loopback/synthetic-only; verify each capability before network exposure. |

Do not put secrets, message bodies, or private customer data in reproductions.
New confirmed defects get a stable FP identifier, reproduction steps or a failing
test, impact, next action, and a linked fix with passing regression evidence.
Keep resolved entries so the reason for a fix remains discoverable.

## Resolved setup and behavior issues

| ID | Resolution | Evidence |
| --- | --- | --- |
| FP-003 | GitHub CLI and repository connection verified | Initial push succeeded; PR #1 created and merged using CLI. Sandboxed credential access can still differ from normal host access. |
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
   Next choose/configure a compatible identity provider, implement browser
   login/session and invitation acceptance, and migrate the dashboard. Identity
   verification does not yet supply a working browser sign-in experience.
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
