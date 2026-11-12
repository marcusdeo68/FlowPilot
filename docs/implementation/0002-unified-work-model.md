# Implementation 0002 — Unified work model and access foundation

**Status: policies/contracts in 0004; PostgreSQL work/source services in 0005; verified-token API in 0007; workspace onboarding and owner-only membership administration in 0008. Real identity-provider setup, browser login, invitation consent/delivery, remaining records, and dashboard migration remain open.** Stage 1 is incomplete. The legacy local dashboard remains unauthenticated and synthetic-only.

## Product change this supports

FlowPilot is expanding from a commitment-focused API into a cross-app work coordination hub. The core remains the same: notice a meaningful change, preserve where it came from, turn it into reviewed work, track it, and help a person complete the next action. Gmail, Slack, Teams, notes, calendars, and future sources become inputs to that workflow, not separate autonomous agents.

The first implementation still must not connect personal accounts. It should establish the domain and authorization foundations with synthetic fixtures.

## Why this is the next segment

The current API has no authentication, workspace boundary, provider ownership, or source visibility model. Adding real connectors first would risk exposing private email or messages across a team. A shared data model also prevents each connector from inventing its own task semantics.

## Proposed core records

| Record | Responsibility | Important boundary |
|---|---|---|
| `users` | Authenticated product identities | Identity provider remains an implementation choice |
| `workspaces` | Team ownership boundary | Membership grants workspace access, not blanket source-content access |
| `memberships` | User, workspace, role, active state | Authorization is checked server-side for each resource |
| `provider_connections` | Provider, account owner, scopes, status, consent/revocation timestamps | Tokens belong to an account owner; never expose raw tokens in API responses or logs |
| `source_items` | Normalized provider object reference, timestamps, link, minimal retained content, visibility | Preserve original provider identity and enforce source permissions |
| `work_items` | A typed commitment, task, or event with status, owner, schedule, project, and version | Distinct type semantics, deterministic transitions, workspace ownership |
| `evidence_links` | Relationship between source content and proposed/accepted work | Keep quoted text bounded and only visible to authorized viewers |
| `proposals` | Candidate work or state change awaiting review | Model output is untrusted and never writes canonical state directly |
| `action_proposals` | Exact provider operation, account, target, payload, version/hash, expiry | Must be immutable after approval or approval becomes invalid |
| `approvals` | Authenticated actor and approved action version | Approval includes explicit user intent for that specific effect |
| `executions` | Attempt, idempotency key, provider result, verification state | Retrying must not duplicate an external action |
| `audit_events` | Actor, record, operation, timestamp, relevant before/after state | Exclude secrets and unnecessary body content |

Avoid one generic JSON blob for all tasks, events, commitments, and provider payloads. Use typed fields and explicit relationships so constraints and queries can be reviewed.

## Visibility rule to encode

An item's workspace is not its only access boundary. A personal email or direct message stays private to its connected account owner by default. Derived work may be shared only when a policy allows it, with a clear choice about whether evidence text or only selected task fields are visible. The first version should be conservative and support private source items plus explicitly shared derived work.

## Design acceptance criteria

Before writing migrations or routes, define:

1. Role capabilities for workspace owner, member, and read-only participant.
2. Which work items may be shared and who may view their evidence.
3. Provider connection ownership and behavior when an owner leaves a workspace.
4. Source-item retention, deletion, re-sync, and provider revocation behavior.
5. Typed state models for commitment, task, and event; which transitions require review.
6. The fields that bind action approval and what invalidates an approval.
7. How workspace identity is obtained from authentication rather than request JSON.

## Proposed v1 access policy

This is the implementation baseline for the first synthetic multi-user slice. It must be encoded in server-side services and reviewed through cross-workspace and private-source checks before any account integration is enabled.

| Role | Workspace access | Shared work | Membership and connections |
|---|---|---|---|
| `owner` | Read workspace records | Create, assign, edit, archive | Invite/remove members, change roles, manage workspace settings; cannot read personal source content without its owner's explicit share |
| `member` | Read workspace-visible records | Create and update shared work; propose changes and actions | Cannot manage membership or another user's provider connection |
| `observer` | Read workspace-visible records | Read only; cannot confirm proposals or approve/execute actions | Cannot manage membership, settings, or provider connections |

An owner role is not an override for source-owner privacy. Action approval must be by an authenticated person with the relevant capability; workspace ownership alone does not authorize sending through another person's connection. Removing the last owner is rejected until ownership is transferred.

### Source visibility and derived work

- A connected account and its source items are private to the authenticated connection owner by default.
- A source owner may explicitly share a derived work item to the workspace. The share decision records actor, time, and the exact fields made visible.
- Evidence has its own visibility (`private`, `summary_shared`, or `excerpt_shared`). Full message/note bodies and attachments are never exposed to the workspace by inheritance.
- A workspace can track a shared task without being able to open the underlying email or direct message. The UI shows source type and provenance link only when the current user can open it.
- Server queries authorize both workspace membership and source/evidence visibility. A client-supplied workspace ID is only a selector that must be matched against authenticated membership; it is never proof of access.

### Membership departure, revocation, and retention

- On membership removal, immediately deny workspace access and revoke active sessions/permissions associated with that membership.
- A user's provider connection remains owned by that user and is disconnected/revoked when they remove it. Workspace owners cannot take over its token.
- Before an owner leaves, transfer ownership to another active owner. Shared work stays in the workspace with an attributed creator/owner history. Private source items stay private; the departing owner can export/delete them under the account's retention policy.
- Provider revocation stops future sync and action execution. Previously retained source data follows the user-visible retention/deletion policy and is not silently converted into workspace-visible evidence.
- Minimize retention from the start: store provider IDs, timestamps, links, normalized fields, and only bounded excerpts needed for evidence. Set a concrete retention period per provider before live sync, since provider policy and user expectations can differ.

### Typed work lifecycle and approvals

- Use distinct discriminated work item types: `commitment`, `task`, and `event`. All share identity, workspace, title, description, owner, project, version, timestamps, and audit history. Commitments keep confirmation/dispute semantics; tasks keep completion/blocking; events keep start/end/time-zone and cancellation/rescheduling semantics.
- Proposal state is `pending_review`, `accepted`, `corrected`, `dismissed`, or `expired`. A proposal cannot mutate a canonical work item until an authorized person accepts it.
- An action approval binds authenticated approver, provider connection/account, operation, exact target, canonical payload hash, action version, workspace, and expiry. Editing any bound field, revoking the connection, expiring the approval, or losing permission invalidates it.
- Execution uses a unique idempotency key and records requested, attempted, provider-acknowledged, verified, failed, or uncertain outcomes. An uncertain result must be checked against the provider before retry.

### Trusted identity boundary

The authentication dependency supplies a verified principal. The application resolves the principal's active membership and role server-side for every request/job. No API body, query parameter, background task argument, or model output may set the authenticated user or confer workspace authority. Background work carries a server-created principal/connection context and repeats the same policy check when it reads or changes data.

## Implementation acceptance criteria

- PostgreSQL migration creates tenant-aware tables and foreign keys with rollback support.
- Repository functions require an authorized workspace context; no caller can select another tenant by changing an ID.
- Resource queries and background job handlers apply the same authorization/visibility rules.
- Tests cover cross-workspace read/write attempts, private-source evidence, stale updates, illegal transitions, and atomic event history.
- The service still runs with synthetic fixtures and no provider credentials.
- API documentation distinguishes proposals from canonical work and approvals from executions.

## Provider reality check

- Gmail is valuable but full message-read OAuth scopes are classified as restricted. Google states that restricted-scope server storage/transmission requires a security assessment; scope and app verification obligations must be reviewed before implementation ([Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [Google Workspace data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)).
- Slack scopes are granular and determine access to conversation content and posting; connectors must expose the scopes granted to each connection ([Slack scopes](https://api.slack.com/scopes)).
- Teams uses Microsoft Graph permissions with delegated and application modes. Broad message-reading permissions can require administrator consent and have different reach ([Graph permission reference](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0)).
- The published Google Keep API is positioned for enterprise administration. Do not promise consumer note sync until its account/authorization requirements are confirmed ([Keep API overview](https://developers.google.com/workspace/keep/api/guides)).

## Learning path

Study the difference between a tenant and a user-owned integration, object-level authorization, normalization, foreign keys, migrations, token lifecycle, source provenance, and idempotency. Trace one synthetic Slack-style message from `source_item` to `proposal` to reviewed `work_item` and explain which checks run at each boundary.

## Explicitly deferred

No live OAuth, real email/message/note ingestion, autonomous multi-agent runtime, production deployment, or automatic sending is part of this segment. First prove the cross-app domain and access rules locally with synthetic data.
