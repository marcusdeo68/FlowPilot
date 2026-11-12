# Security and privacy boundaries

## Current risk boundary

The current API is a local development scaffold with no authentication or user/workspace authorization. Run it only on `127.0.0.1`, use synthetic data, and do not expose or deploy it. It has no provider credentials or model APIs. Do not connect a personal inbox, chat account, notes account, or calendar to this version.

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

Increment 0007's separate API verifies configured RS256 access tokens and resolves
stored memberships. It has no live identity-provider setup or browser login yet.
The legacy dashboard remains unauthenticated. Unknown-key refresh rate limiting,
request limits, HTTPS/proxy deployment, provisioning, retention, and operational
controls remain open; keep both factories local and synthetic. See implementation
0007 for the accepted token profile, trusted key endpoint, and provider review.

Increment 0005 implements internal PostgreSQL service checks for active stored
membership, workspace isolation, source ownership, evidence projection, and atomic
audit. No network request can yet obtain a verified Principal for that service.
The old HTTP API remains unauthenticated. Separate database runtime/migration roles,
retention/deletion, membership administration, backups, and deployment controls
remain required. Test database credentials in CI/Compose are synthetic only.

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

## Provider-specific review notes

- Gmail read scopes for message bodies are restricted. Google states that storing or transmitting restricted-scope data on servers requires a security assessment; verify current OAuth verification and policy obligations before a live integration ([scope reference](https://developers.google.com/workspace/gmail/api/auth/scopes), [Workspace user data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)).
- Slack permissions are scope-based and can grant access to conversation content or message posting. Request only the scopes required for an explicitly selected workflow ([Slack scopes](https://api.slack.com/scopes)).
- Microsoft Graph has delegated and application Teams message permissions with materially different reach; broad application permissions may require administrator consent ([permissions reference](https://learn.microsoft.com/graph/permissions-reference?view=graph-rest-1.0)).
- Google's Keep API is described for enterprise administration and supports domain authorization paths. Validate that it supports the intended personal-account workflow before promising a Keep connector ([Keep API overview](https://developers.google.com/workspace/keep/api/guides)).
