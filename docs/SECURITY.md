# Security and privacy boundaries

## Current risk boundary

The default dashboard/legacy API is a local development scaffold without identity
or workspace authorization. The separate workspace API verifies access tokens and
stored membership, but has no real provider/browser login configured and remains
local-only too. Run both on `127.0.0.1` with synthetic data. Do not expose/deploy
either or connect personal email, chat, notes, or calendar accounts yet.

## Implemented in the local scaffold

- Loopback-only run instructions.
- Validated and size-limited API inputs; unknown fields are rejected.
- Parameterized SQL, deterministic lifecycle rules, and stale-update rejection.
- State and event history saved in one transaction.
- Local database and secrets excluded from Git.

These controls do not make the scaffold suitable for real user data.

Increment 0004 adds database triggers rejecting event updates/deletes, allowed-host
checks, foreign-origin browser write rejection, and security headers for the
dashboard. Pure access policies have isolation tests but are not wired into the
legacy API. These local protections are not authentication or network deployment
readiness; see `docs/implementation/0004-verification-and-access-policies.md`.

The first browser dashboard is also local-only. It uses same-origin calls to the unauthenticated manual API and includes sample-only inbox/schedule examples. Keep the server bound to loopback and do not deploy this version to AWS or expose it to a network. The dashboard does not connect external accounts and has no permission to send email or messages.

## Required before multi-user or real provider data

Increment 0016 optionally exposes generic authorization-code login, requiring
explicit same-issuer HTTPS endpoints, PKCE, issuer response binding, bounded code
exchange and existing strict token verification plus exact client/API scopes.
Callback GET never issues a session; same-origin completion POST checks existing
Strict cookies before issuance. Disable callback query access logging. No provider
is configured and no live data is permitted. See [0016](implementation/0016-browser-login.md).

Increment 0015 adds digest-only, five-minute, single-use pending login records
bound to issuer/audience/client/callback configuration. Consumption is audited
atomically and does not authenticate a user. Browser initiation/callback protections,
provider review and returned-token verification are still required before exposing
login routes. See [0015](implementation/0015-login-transactions.md).

Increment 0012 optionally enables token-bounded opaque browser sessions on one
explicit loopback origin. Credentials are hashed at rest; active-session writes
and logout require exact Origin plus CSRF. Safe reads reject supplied foreign
Origin/Fetch Metadata. SameSite alone does not isolate localhost ports. Cookie
Secure is mandatory for configured HTTPS and omitted only for explicit loopback
HTTP development. No proxy/public origin is supported. Revocation denies later
authentication but cannot cancel admitted operations. Session/audit retention,
request limits, provider revocation and full login remain deployment gaps; see
[the session design](implementation/0012-browser-sessions.md).

Increment 0007's separate API verifies configured RS256 access tokens and resolves
stored memberships. Configuration of a live identity provider remains open.
The legacy dashboard remains unauthenticated. Signing-key refresh is throttled;
request limits, HTTPS/proxy deployment, invitation consent, retention, and operational
controls remain open; keep both factories local and synthetic. See implementation
0007 for the accepted token profile, trusted key endpoint, and provider review.

Increment 0005 implements internal PostgreSQL service checks for active stored
membership, workspace isolation, source ownership, evidence projection, and atomic
audit. Increment 0007 separately wraps that service with verified access-token requests.
The old HTTP API remains unauthenticated. Separate database runtime/migration roles,
retention/deletion, backups, and deployment controls
remain required. Test database credentials in CI/Compose are synthetic only.

Increment 0008 adds owner-only membership administration with exact versions,
workspace-serialized last-owner checks, and atomic append-only permission history.
New workspaces register only the verified issuer/subject as their owner. Grants
target already registered same-issuer users by ID; there is no public user search
or email delivery. Deactivation denies later workspace operations, retains private
ownership/audit attribution, and does not revoke an identity's unrelated memberships.
Direct database administration can bypass application invariants; runtime database
roles and reviewed invitation consent are still deployment requirements.

Increment 0028 exposes the existing owner-only controls in the signed-in
workspace. The browser binds authenticated requests to the session token already
held by the tab. A supplied binding that mismatches the current cookie fails
authentication. Owner roster and history clear when the view loses access or
changes context. See [0028](implementation/0028-workspace-access.md).

Increment 0029 adds local consent for workspace invitations. Only the registered
recipient can accept the exact offer. Acceptance verifies the inviter's active
owner role and membership version under the workspace lock. Offers expire after
seven days. Invitation decisions and resulting membership changes commit with
append-only audit. The original direct grant stays available through the signed
synthetic API. Production delivery and abuse controls need review before that
API can handle real accounts. See [0029](implementation/0029-workspace-invitations.md).

- Authentication and server-side workspace/member/role authorization.
- Tenant isolation tests and review of every query and background job for object-level access checks.
- PostgreSQL migrations, backups, recovery, encryption at rest, retention, deletion, and export procedures.
- Provider token encryption, owner binding, refresh/revocation, minimal OAuth scope requests, and consent history.
- Source-level access controls; a workspace membership must not automatically expose personal mail or direct messages.
- Webhook signature verification, request validation, idempotency, retry limits, and rate limiting.
- Structured logs that exclude message bodies, tokens, and unnecessary personal data.
- Audit events with authenticated actor identity and access controls.
- A data-flow and threat review before adding a model provider, connector, or deployment target.
- For AWS: private database networking, least-privilege task/execution roles, encrypted secrets, image provenance/scanning, log retention without source bodies, a constrained GitHub OIDC trust policy, and reviewed Terraform plans.

## AI and source-content trust boundaries

Emails, chat messages, notes, documents, links, and attachments are untrusted content. A message can contain prompt injection or malicious instructions. FlowPilot should keep source text separate from system policy, limit what gets sent to a model, preserve the origin of extracted evidence, validate structured output, and treat every model response as a proposal. Do not follow instructions found inside imported content.

## External action approval

Sending email or messages, changing events, and editing provider data are external side effects. Each action proposal must identify the connected account, provider, exact target, content/payload version, requested operation, and expiry. Approval is recorded against that exact payload. Any edit invalidates approval. The executor must re-check authorization immediately before execution, use an idempotency key, record the provider response, and verify the final state. A model-generated draft or tool call is never approval.

For email, show sender account, recipients, subject, body, and attachments in a clear review step. A convenient send button is appropriate after the user sees and approves those details; do not silently send generated text.

The intended Slack messaging flow must show the sending account, exact channel
or conversation, and content. It uses the same version, expiry, permission
recheck, idempotency, and result verification rules.

## Private native notes

Notes use server-enforced author and workspace scoping. A workspace owner has
access to their own notes. Archiving retains the text. Each mutation records its
actor, operation, time, and version without copying the note body into audit.
Use synthetic content on loopback while deletion, retention, and production
database access controls are pending. See [0024](implementation/0024-private-sticky-notes.md).

## Manual workspace events

The signed-in event editor creates private work. Browsing applies active
membership and work visibility before pagination. Only the creator can edit a
scheduled event's fields. The existing versioned cancellation policy permits
active writers to cancel events visible to them, including shared events.
Cookie writes require CSRF. Changes and metadata-only audit events commit together.
See [0025](implementation/0025-manual-workspace-events.md).

## Workspace sharing

Authors with write capability can review a private work item and the exact
evidence projection visible to other members. Confirmation binds to the
reviewed work version. Linking evidence increments that version and requires
a fresh review. Sharing publishes the canonical fields and history to the
workspace and retains the separate source and evidence authorization rules.
See [0030](implementation/0030-workspace-sharing.md).

## Reminder privacy

Popup reminders must respect the viewer's source/work visibility. Permission to
see a deadline in FlowPilot does not justify exposing private email or note text
in a lock-screen notification. Review notification permissions and preview content,
plus browser/OS delivery and closed-app behavior, before implementation. Timing,
snoozing, dismissal and duplicate-alert suppression should reduce interruption
overload. Increment 0026 displays reminders only on a visible signed-in
workspace page after opt-in. It requests visible item IDs, titles, and timing,
and keeps snooze and dismissal keys in tab memory. Cookie reminder reads require
the tab's existing session token to prevent a replacement cookie in another tab
from authorizing the old page. See [0026](implementation/0026-in-app-reminders.md).

## Provider-specific review notes

- Gmail read scopes for message bodies are restricted. Google states that storing or transmitting restricted-scope data on servers requires a security assessment; verify current OAuth verification and policy obligations before a live integration ([scope reference](https://developers.google.com/workspace/gmail/api/auth/scopes), [Workspace user data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)).
- Slack permissions are scope-based and can grant access to conversation content or message posting. Request only the scopes required for an explicitly selected workflow ([Slack scopes](https://api.slack.com/scopes)).
- Microsoft Graph has delegated and application Teams message permissions with materially different reach; broad application permissions may require administrator consent ([permissions reference](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0)).
- Future note imports require their own review of account support, authorization scopes, and retention before a connector is added.
