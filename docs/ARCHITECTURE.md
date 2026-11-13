# Architecture

## Starting shape

FlowPilot remains a Python modular monolith. A single FastAPI application can host the API, domain rules, provider adapters, proposal processing, approval service, and background jobs while each stays in a clear module. This makes the early system easier to learn and operate than a collection of microservices.

```text
Provider APIs / manual import
          │
Provider-specific connectors
          │
Normalized source items ── access/visibility metadata
          │
Proposal pipeline (AI may suggest; deterministic code validates)
          │
Canonical work items ── tasks / commitments / events
          │
Unified UI + action proposals
          │
Human approval → idempotent executor → provider verification
```

## Current code and next persistence step

The default local dashboard uses the legacy SQLite adapter. A separate verified
workspace API uses PostgreSQL, SQLAlchemy transactions, and Alembic migrations for
users, workspaces, memberships, manual sources, evidence, typed work, and audit.
Workspace onboarding and owner-only membership administration are increment 0008.
Private task proposals and review history are increment 0009. Provider connections,
projects, action proposals, approvals, and executions remain future
records. Every tenant-owned record needs a workspace key and server-enforced
authorization. The live authentication provider/session flow remains unconfigured;
AWS is the planned later deployment target.

## Module boundaries

Increment 0012 adds optional opaque browser sessions to the verified API.
`browser_sessions.py` stores credential digests, verified identity/scopes, exact
origin/audience binding, absolute expiry and atomic lifecycle audit.
`session_routes.py` enforces origin, CSRF and cookie rules; existing business
services continue to recheck stored permissions. It does not connect the dashboard
or configure a login provider. See [0012](implementation/0012-browser-sessions.md).

Increment 0008 adds `MembershipService` and a shared stored-membership resolver.
Workspace creation establishes the verified caller as owner with an atomic audit.
Role/active-state changes lock the workspace before actor/target memberships and
require the target version, serializing last-owner decisions. The new migration
adds membership versions and immutable workspace history; it rejects pre-existing
ownerless workspaces rather than guessing an owner. No invitation delivery or
browser login is implemented.

Increment 0007 adds a separate `workspace_api:create_workspace_app` factory with
signed access-token verification and API scopes before invoking the PostgreSQL
service. Its request identities are verified issuer/subject pairs. It does not
mount legacy routes or the dashboard. A real identity provider and browser login/session
flow remain unconfigured; API onboarding is now in 0008. See implementation 0007 for token-profile
requirements and the explicit separation from the local demo.

Increment 0005 adds PostgreSQL migrations and an internal `WorkService` using
SQLAlchemy transactions and psycopg. The service resolves issuer/subject through
stored membership on every operation, scopes queries by workspace and visibility,
and commits state plus audit together. Composite foreign keys prevent tenant-mixed
relationships. Increment 0007 wraps it with separately verified HTTP routes.
The dashboard still uses the separate legacy SQLite API. See implementation 0005
for the exact storage boundary and deferred records.

Increment 0004 introduces pure `access.py` policy functions and `work.py`
discriminated contracts with isolated regression tests. They establish rules for
the next persistence adapter; the legacy SQLite HTTP endpoints do not yet resolve
verified identities or invoke these policies. Do not infer tenant isolation from
the presence of the policy module.

- **API:** HTTP routes, request authentication, authorization dependencies, and error mapping.
- **Domain:** work item semantics, permitted lifecycle transitions, and approval invariants.
- **Connectors:** provider-specific OAuth scopes, API calls, webhook verification, and normalization.
- **Sources:** provider references, minimal source snapshots, provenance, retention, and visibility.
- **Proposals:** extraction inputs/outputs and human review state; model responses are untrusted.
- **Workflow:** deterministic state changes, background work, retries, idempotency, and scheduled checks.
- **Actions:** exact action payloads, approval versions, provider execution, and outcome verification.
- **Persistence:** PostgreSQL repositories and versioned migrations.
- **Frontend:** Today, unified inbox, tasks/projects, schedule, review/send, and connection settings.

## Data isolation and visibility

Workspace membership is not enough to disclose every source item. A personal Gmail message or direct message stays private to its account owner by default. Shared work may be visible to a workspace only when a policy allows the derived fields and evidence to be shared. Records should carry source visibility and owner identity so the API can authorize reads and prevent accidental cross-team exposure.

Tokens are associated with a provider connection and its owner, never with a workspace-wide implicit identity. The connector records granted scopes and consent/revocation state. Read and action scopes should be separately requested where provider flows support it.

## Request and processing flows

### Ingest and propose

Fetch or receive a provider change → verify the provider request → deduplicate using provider event identity → store a minimal source reference → apply source access policy → optionally extract a structured proposal → validate schema and evidence references → place it in a review queue. A retry must not create duplicate source items or proposals.

### Review and track

An authenticated user views only authorized proposals, reviews source evidence, and confirms or corrects fields. Domain rules determine what can become canonical work state. Status changes and their audit events commit together.

### Prepare and execute an action

Generate an editable draft → bind approval to the exact target and payload version → require approval from an authorized user → re-check permission and expiry → execute with an idempotency key → save provider result → verify the provider state. A model response alone cannot bypass any step.

## Provider strategy

Each integration is an adapter, not a source of product-specific UI logic. Add one provider at a time after confirming its API supports the intended data, the required scopes, review requirements, retention limits, and user visibility model. Do not assume an API exposed to enterprise administrators is available for ordinary personal accounts.

## Local scaffold boundary

The current SQLite database is appropriate only for local development with synthetic data. It lacks migrations, identity, tenant isolation, and production backup/recovery controls. Keep the existing domain rules useful while replacing the persistence adapter; do not treat a file database as the multi-user product database.

## Local web shell

The first dashboard is a dependency-free static client served by the local FastAPI process. It reads and writes only the existing synthetic/manual commitment API. The task view uses DOM text nodes for API values and same-origin `fetch` requests; sample inbox and schedule content is presentation-only and is not persisted or connected to a provider. This shell is a learning and product-validation surface, not an authenticated web application. Keep the local process bound to loopback until request identity, workspace authorization, CSRF strategy for cookie auth, and production hosting controls are implemented.

## AWS deployment target (planned)

The initial cloud deployment should remain one containerized modular monolith. Use ECR for immutable image versions, ECS on Fargate for the API/web process, RDS PostgreSQL in private subnets, Secrets Manager for runtime secrets, CloudWatch for logs/metrics/alarms, and Terraform for reproducible infrastructure. A load balancer and public endpoint should be introduced only after authentication and operational security are ready. CI/CD should use GitHub Actions OIDC with an IAM trust condition scoped to the exact repository and deployment branch/environment; no long-lived AWS key belongs in GitHub secrets. See `docs/implementation/0003-local-dashboard-and-cloud-path.md` for sequence, trade-offs, and the resume skill map.
