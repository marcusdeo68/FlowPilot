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
stored memberships. It has no live identity-provider setup or browser login yet.
The legacy dashboard remains unauthenticated. Signing-key refresh is throttled;
request limits, HTTPS/proxy deployment, browser login, invitation consent, retention, and operational
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

The intended Slack messaging flow must likewise show the sending account, exact
channel/conversation and content. Creating a new Google Keep text or list note is
also a provider write: show the target account, note title and exact text/list contents.
These use the same version, expiry, permission recheck, idempotency and result
verification rules above; a reminder or model suggestion cannot authorize them.

## Planned reminder privacy

Popup reminders must respect the viewer's source/work visibility. Permission to
see a deadline in FlowPilot does not justify exposing private email or note text
in a lock-screen notification. Review notification permissions and preview content,
plus browser/OS delivery and closed-app behavior, before implementation. Timing,
snoozing, dismissal and duplicate-alert suppression should reduce interruption
overload. No reminder scheduler or popup delivery is implemented yet.

## Provider-specific review notes

- Gmail read scopes for message bodies are restricted. Google states that storing or transmitting restricted-scope data on servers requires a security assessment; verify current OAuth verification and policy obligations before a live integration ([scope reference](https://developers.google.com/workspace/gmail/api/auth/scopes), [Workspace user data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)).
- Slack permissions are scope-based and can grant access to conversation content or message posting. Request only the scopes required for an explicitly selected workflow ([Slack scopes](https://api.slack.com/scopes)).
- Microsoft Graph has delegated and application Teams message permissions with materially different reach; broad application permissions may require administrator consent ([permissions reference](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0)).
- Google's Keep API is described for enterprise administration and supports domain authorization paths. Validate that it supports the intended personal-account workflow before promising a Keep connector ([Keep API overview](https://developers.google.com/workspace/keep/api/guides)).
