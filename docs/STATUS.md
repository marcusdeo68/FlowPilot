# FlowPilot maintenance and implementation tracker

Updated: 2026-11-12. This file records implementation evidence, known issues, and
the next increment. Implementation notes explain design; GitHub Actions records
verification for each revision. Update this file when an item's state changes.

## Current checkpoint

- Foundation and verification increment merged in [PR #1](https://github.com/marcusdeo68/FlowPilot/pull/1).
- 38 tests passed locally and in the Windows/Linux Python 3.11/3.12 CI matrix for
  the PR revision. Lint, formatting, package builds, and JavaScript syntax passed.
- SQLite dashboard is local-only with synthetic/manual data. Tested access policies
  are not yet wired to authenticated requests or tenant-aware storage.
- Run and verification commands: [README](../README.md). Design:
  [implementation 0004](implementation/0004-verification-and-access-policies.md).

## Open issues and verification gaps

| ID | Type / status | Evidence and impact | Next action / closure evidence |
| --- | --- | --- | --- |
| FP-001 | Dependency warning / open | pytest reports Starlette's httpx TestClient deprecation. Tests pass; a future upstream release could remove compatibility. | Evaluate supported replacement against official release guidance; close when the supported client passes the API suite without the warning. |
| FP-002 | Test coverage gap / open | Dashboard JavaScript has a syntax check; no automated real-browser workflow tests. API tests cannot detect broken buttons, focus handling, or DOM rendering. | Add browser checks for capture, explicit transitions, conflict recovery, and safe text rendering. Close when these run in CI. |

Do not put secrets, message bodies, or private customer data in reproductions.
New confirmed defects get a stable FP identifier, reproduction steps or a failing
test, impact, next action, and a linked fix with passing regression evidence.
Keep resolved entries so the reason for a fix remains discoverable.

## Resolved setup and behavior issues

| ID | Resolution | Evidence |
| --- | --- | --- |
| FP-003 | GitHub CLI and repository connection verified | Initial push succeeded; PR #1 created and merged using CLI. Sandboxed credential access can still differ from normal host access. |
| FP-004 | Python/PATH dependency addressed for this checkout | Managed `.venv`, committed dependency lock, and Cursor process tasks; fresh CI environments passed. |
| FP-005 | Completion no longer silently confirms a commitment | Dashboard exposes individual Confirm/Start/Complete actions; see implementation 0004. Browser regression coverage is still FP-002. |

## Next implementation milestones

These are planned capabilities, not reported bugs. Stage 1 is incomplete.

1. PostgreSQL storage/service slice implemented in
   [implementation 0005](implementation/0005-postgres-work-storage.md), pending final
   CI/merge verification. Includes seven tables, workspace-qualified relationships,
   stored-membership authorization, private sources, evidence sharing, and audit
   transactions. Remaining Stage 1 tables and HTTP identity are still planned.
2. Verified authentication and server-resolved memberships; wire access policies
   into every repository/service path and test unauthorized requests.
3. Synthetic source/proposal review workflow, then dashboard integration and
   browser tests. Preserve explicit evidence sharing and human review boundaries.
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
  continuous bug triage process. CI runs on pushes/PRs; it does not watch a running
  application. Add deployment monitoring when there is a deployed environment.
