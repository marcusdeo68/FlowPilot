# FlowPilot roadmap

The product direction is a unified cross-app work coordination hub. The first proof remains narrow: reliably turn source changes into reviewed tasks/commitments/events, then prepare a useful follow-up. Stages are dependencies, not delivery promises.

Gmail, Google Calendar, and Slack are the intended integration set. FlowPilot
provides native private Notes for quick capture.
The product must centralize communication and task organization while reducing
overwhelm. Each integration still needs its own API, scope, privacy and account
support review; naming the targets does not select the first pilot or connect them.

## Stage 0 — Local foundation (scaffolded)

- [x] FastAPI local app and liveness/readiness endpoints.
- [x] SQLite records for synthetic/manual commitments.
- [x] Explicit commitment transitions, record versions, and append-only status events.
- [x] Product, architecture, API, security, learning, and implementation notes.
- [x] Create the GitHub repository and connect the workspace (public by user choice).
- [x] Install/use a Python runtime, validate the local app, and add automated quality checks.

## Stage 1 — Multi-source work model and access foundation (next implementation segment)

Before live provider data, replace the single-user local storage model with the basic multi-user domain and authorization design:

Implemented portions include typed work contracts, PostgreSQL persistence, and a
separate verified-token workspace API. Workspace onboarding and member administration
are increment 0008. Stage 1 remains incomplete: live sign-in, remaining unified
records, and authenticated dashboard wiring still need implementation and review.

- [x] Initial PostgreSQL schema, reversible migration, and real database CI tests
  for manual typed work, evidence privacy, and audit transactions (increment 0005).
- [x] Separate signed-access-token workspace API factory with stored-member authorization (0007).
- [x] API workspace creation/discovery, owner-only member administration, and last-owner protection (0008).
- [x] Signed-in workspace access view for owners to manage memberships and review recent changes (0028).
- [x] Register a synthetic profile and accept or decline a workspace invitation in the browser (0029).
- [x] Private manual-source task suggestion, correction, dismissal, and version-bound acceptance (0009).
- [x] Cursor-paginated owner-only source inbox with current review state (0010).
- [x] Optional token-bounded browser sessions with CSRF, revocation and real-browser coverage (0012).
- [x] Authorized creation-order work pagination for browsing beyond capped lists (0014).
- [x] Internal single-use, browser-bound PKCE login transaction storage and audit (0015).
- [x] Opt-in generic authorization-code browser adapter with synthetic provider tests (0016).
- [x] Browser workspace selection, creation, and authorized work browsing (0017).
- [x] Create private tasks and edit owned task details in the signed-in workspace (0018).
- [x] Track a task through its status changes and find the earliest unfinished deadlines (0019).
- [ ] Live identity-provider setup, invitation delivery, remaining Stage 1 records,
  and dashboard persistence migration.
- Users, workspaces, memberships, roles, and server-side authorization boundaries.
- Provider connections with owner, provider, granted scopes, and connection/revocation status.
- Source items with provider identity, timestamps, link, minimal retained content, and visibility metadata.
- Typed work items for commitments, tasks, and events; relationships to source evidence and projects.
- Proposals, human review state, action proposals, exact-payload approvals, executions, and audit events.
- Synthetic fixtures; no OAuth connection or real messages in this segment.

The detailed design and acceptance criteria are in `docs/implementation/0002-unified-work-model.md`.

## Stage 2 — Unified manual workflow UI (shell started)

- Today / Command Center for changes, due work, events, blockers, and approvals.
- [x] Signed-in Today view for due-today and overdue tasks (0021).
- [x] Surface recent pending private reviews in the signed-in Today view (0022).
- [x] Open a specific pending suggestion and its evidence directly from Today (0048).
- [x] Surface authorized upcoming and ongoing manual events in signed-in Today (0023).
- [x] Create, edit, archive, and restore native private sticky notes (0024).
- [x] Browse, create, reschedule, and cancel manual workspace events (0025).
- [x] Opt-in reminders for due-today tasks and imminent events in an open workspace tab (0026).
- [x] Choose reminder categories, event lead time, and snooze duration for the signed-in tab (0027).
- [x] Review and share private tasks and events, and browse shared work by visibility (0030).
- [x] Search authorized work by title across pages (0036).
- [x] Filter authorized tasks by status and combine with title search (0037).
- [x] Create workspace projects, group tasks, and filter Work items (0038).
- [x] Set and filter task priorities (0039).
- [x] Open an interactive local workspace preview with synthetic records (0040).
- [x] Browse ongoing and future manual events in chronological order in Schedule (0041).
- [x] See upcoming task deadlines alongside events in Schedule (0042).
- [x] Choose a start date and page through unfinished task deadlines in Schedule (0043).
- [x] Carry a selected Schedule date into Due tasks and filter tasks while managing them (0044).
- [x] Page through matching deadlines while managing tasks in Due tasks (0045).
- Unified Inbox with source evidence and review/edit/confirm/dispute actions.
- Tasks & Projects and a schedule view.
- Action review UI that makes sender account, recipients, target, and content visible before approval.
- Seeded synthetic sources to validate the product without provider access.
- [ ] Configurable popup reminders for important/upcoming items and deadlines,
  with timing, snooze/dismiss controls, grouped updates and duplicate-alert
  suppression. Define browser/OS permission, privacy and closed-app delivery
  behavior before claiming notifications work outside an open FlowPilot view.
- [x] First local dashboard shell with a today view and API-backed manual commitment capture.
- [x] Capture and browse private manual sources and review task suggestions in the signed-in workspace (0020).
- [ ] Replace sample-only inbox and schedule cards with typed synthetic source/evidence fixtures.
- [ ] Connect inbox review and task/project screens to the unified work model after Stage 1 access boundaries exist.

## Stage 3 — AI proposal pipeline and evaluation

- Structured proposals for commitments, tasks, dates, owners, events, and changed/canceled work.
- Evidence references into source items; explicit uncertainty and abstention.
- Evaluation data that distinguishes a promise from a suggestion, question, or hypothetical statement.
- Regression checks for duplicates, state reconciliation, prompt injection, quality, latency, and cost.
- Models can propose; deterministic code validates and users confirm. Models do not write canonical state or execute tools.

## Stage 4 — One read-only provider pilot

- Pick the first provider after API, scope, consent, data retention, and verification review.
- Begin with read-only data synchronization and a narrow set of approved sources.
- Add verified webhooks or safe polling, deduplication, backoff, revocation, and user-scoped data visibility.
- Start with synthetic fixtures; only move to consented real data after access controls and retention are ready.

Gmail is a product-relevant candidate, but the official Gmail API classifies full message-read scopes as restricted; storage/transmission of restricted data can bring security assessment requirements. This needs early planning before product architecture depends on broad inbox access ([Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [Google Workspace user data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)).

## Stage 5 — Human-approved actions

- Create editable professional email drafts with exact sender, recipient, subject, body, and attachment preview.
- Prepare Slack messages with the exact sending account, channel or conversation,
  and content. Apply explicit version-bound approval and execution safeguards.
- Start with saving drafts where supported; sending is a separate capability and permission grant.
- Approval binds an authorized user to the exact action payload, account, target, version, and expiry.
- Editing after approval invalidates it; execution re-checks authorization and uses an idempotency key.
- Record provider responses and verify whether the action happened before offering retries.

Gmail `gmail.send` is sensitive, while `gmail.compose` is a restricted scope; the appropriate scope depends on whether FlowPilot only saves drafts or sends email. App verification and any assessment obligations must be addressed before launch ([Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)).

## Stage 6 — Expand sources based on pilot value

- Google Calendar is a target integration for permitted events and deadlines in
  the unified schedule; review its API, minimum scopes, sync and privacy model
  before implementation. Calendar writes require the Stage 5 approval workflow.
- Slack: scope only the channels/conversations a user or app is permitted to access; keep per-provider app permissions explicit ([Slack permission scopes](https://api.slack.com/scopes)).
- Microsoft Teams: review delegated vs application permissions and admin consent requirements for the target chat/channel features ([Microsoft Graph permissions](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0)).
- Consider Drive, Google Docs, Notion, or other additional sources only when a pilot demonstrates a clear workflow and their access model passes the same review.

## Stage 7 — Pilot and reliability

- Pilot with one small team and a bounded number of sources.
- Measure missed/incorrect proposals, duplicate rate, user corrections, time to resolve, action success, latency, and model/API costs.
- Improve observability, retries, data deletion/export, permission transparency, and recovery from provider outages.

## Stage 8 — Hosted portfolio pilot

The first hosted release is a signed-in personal project for a small group of
invited friends. Start at zero cost with one Railway web service, a private
PostgreSQL service in a dedicated environment, and Railway's HTTPS URL. Use synthetic
data during staging. Measure usage and cold starts before promising ongoing
availability. The owner decides whether to pay for upgrades or a custom domain.
See [Railway's free plan](https://docs.railway.com/pricing/free-plan).

- [x] Package the signed-in workspace as a non-root container. Verify exact HTTPS origin, synthetic sign-in and trusted proxy behavior locally. See [0031](implementation/0031-hosted-workspace.md).
- [x] Document the Railway deployment settings and verify migration and readiness behavior locally. See [0032](implementation/0032-railway-pilot.md).
- [x] Add an option to close database connections when work finishes. Verify
  that writes and rollbacks work with PostgreSQL. See [0033](implementation/0033-idle-database-connections.md).
- [ ] Measure Railway sleep, cold-start latency, and combined app and database
  usage during staging.
- [x] Implement and test the Railway-only ingress and a public HTTPS smoke check locally. See [0035](implementation/0035-railway-direct-pilot.md).
- [x] Rehearse packaged startup, migrations, and Railway-mode responses with disposable PostgreSQL (0046).
- [x] Publish a [synthetic workspace demo with screenshots](implementation/0049-workspace-demo.md) for visitors to try while the hosted pilot is unavailable.
- Verify the actual edge and private network, callback log privacy, sign-in compatibility, account isolation, and teardown. Use the smallest deployment that passes these checks.
- Invite friends to use the manual task, notes, events, and reminders workflow with sample content. Collect feedback, then prioritize the next product increment. Keep a short demo and screenshots available if the free app sleeps or reaches its allowance.
- Review one external integration at a time before introducing real accounts or provider data. See [SECURITY](SECURITY.md).

AWS and Terraform were evaluated as a learning path and are deferred. Track
implemented skills and tested services in [portfolio evidence](PORTFOLIO.md).

## Commitment lifecycle in the current scaffold

```text
detected → confirmed → active → completed
    │          │         │  ↘ blocked → active
    └──────────┴─────────┴──→ canceled / disputed
```

The transition table in `services/api/src/flowpilot_api/domain.py` applies to the current local API. The broader work-item lifecycle will be specified in Stage 1 and must preserve event history.
