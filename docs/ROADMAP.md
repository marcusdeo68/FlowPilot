# FlowPilot roadmap

The product direction is a unified cross-app work coordination hub. The first proof remains narrow: reliably turn source changes into reviewed tasks/commitments/events, then prepare a useful follow-up. Stages are dependencies, not delivery promises.

Gmail, Google Calendar, Slack, and Google Keep are the intended integration set.
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
- [x] Private manual-source task suggestion, correction, dismissal, and version-bound acceptance (0009).
- [x] Cursor-paginated owner-only source inbox with current review state (0010).
- [x] Optional token-bounded browser sessions with CSRF, revocation and real-browser coverage (0012).
- [ ] Live identity-provider setup, login/callback, invitation consent, remaining Stage 1 records,
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
- Unified Inbox with source evidence and review/edit/confirm/dispute actions.
- Tasks & Projects and a schedule view.
- Action review UI that makes sender account, recipients, target, and content visible before approval.
- Seeded synthetic sources to validate the product without provider access.
- [ ] Configurable popup reminders for important/upcoming items and deadlines,
  with timing, snooze/dismiss controls, grouped updates and duplicate-alert
  suppression. Define browser/OS permission, privacy and closed-app delivery
  behavior before claiming notifications work outside an open FlowPilot view.
- [x] First local dashboard shell with a today view and API-backed manual commitment capture.
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
- Prepare Slack messages with the exact sending account, channel/conversation and
  content, and Google Keep note/list creation where the account/API supports it.
  Both follow the same explicit version-bound approval and execution safeguards.
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
- Google Keep: do not assume personal-account note sync is available. Google's published Keep API is oriented toward enterprise administration and domain authorization; validate the intended account model before committing this connector ([Google Keep API overview](https://developers.google.com/workspace/keep/api/guides)).
- Consider Drive, Google Docs, Notion, or other additional sources only when a pilot demonstrates a clear workflow and their access model passes the same review.

## Stage 7 — Pilot and reliability

- Pilot with one small team and a bounded number of sources.
- Measure missed/incorrect proposals, duplicate rate, user corrections, time to resolve, action success, latency, and model/API costs.
- Improve observability, retries, data deletion/export, permission transparency, and recovery from provider outages.

## Stage 8 — AWS delivery and operations (parallel portfolio track)

Build and prove the local container first, then deploy a private development environment only after authentication, workspace authorization, PostgreSQL migrations, and secret handling are in place. The initial AWS target is an ECS service on Fargate, with images in ECR, PostgreSQL in RDS inside private subnets, credentials in Secrets Manager, and application logs/alarms in CloudWatch. Fargate runs containers without requiring the project to manage EC2 hosts ([ECS Fargate overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)); RDS provides a managed PostgreSQL option ([RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)).

- Dockerize the API/UI and add a non-root runtime, health checks, and image scanning.
- Define the network, IAM roles, database, service, and logs as Terraform; keep state remote and encrypted before team use.
- Build/test in GitHub Actions and authenticate to AWS through OIDC with a repository-and-branch constrained trust policy; do not store long-lived AWS keys as repository secrets ([GitHub OIDC for AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)).
- Add CloudWatch alarms, log retention, a deployment rollback path, deletion/backup notes, and an AWS Budget alert before enabling a public endpoint.
- Start with a private, low-cost dev environment and tear it down when idle. Budget alerts are useful but delayed: AWS billing data used by Budgets refreshes at least daily ([AWS Budgets guidance](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)).

This track adds credible resume evidence in containerization, AWS networking/IAM, managed PostgreSQL, Infrastructure as Code, secure CI/CD, observability, and cost-aware operations. It is a later deployment target, not authorization to create AWS resources now.

## Commitment lifecycle in the current scaffold

```text
detected → confirmed → active → completed
    │          │         │  ↘ blocked → active
    └──────────┴─────────┴──→ canceled / disputed
```

The transition table in `services/api/src/flowpilot_api/domain.py` applies to the current local API. The broader work-item lifecycle will be specified in Stage 1 and must preserve event history.
