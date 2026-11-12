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

The current code has FastAPI routes, Pydantic schemas, a deterministic commitment lifecycle, and a SQLite repository. It is a local synthetic-data scaffold, not the product's multi-user storage design.

The next data-model segment should move persistence to PostgreSQL with SQLAlchemy and Alembic migrations. It must introduce users, workspaces, memberships, provider connections, source items, source evidence, typed work items, proposals, approvals, executions, and audit events. Every tenant-owned record needs a workspace key and server-enforced authorization. The selected authentication provider and deployment target are still undecided; avoid inventing them in the domain layer.

## Module boundaries

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
