# Architecture decisions

## 0017 - Keep browser credentials opaque and server-revocable

Exchange only a verified, read-scoped access token on an explicit loopback origin.
Store a random credential's digest and verified identity/scopes rather than the
provider token. Bound expiry to the original token; do not add sliding renewal.
Origin and CSRF checks protect cookie writes while existing services keep checking
membership. This supports future browser login without choosing a provider or
weakening the current identity contract. Retention, full sign-in/callback and
deployment controls remain separate work; see [0012](implementation/0012-browser-sessions.md).

## 0016 - Review a source-derived task before creating canonical work

Keep one private proposal per manual source. A correction keeps the proposal
pending and invalidates its previous version. Accept only the exact version and
commit task, private evidence, and review history in a single transaction.
See [implementation 0009](implementation/0009-private-task-review.md).

## 0015 - Provision workspaces from verified identity and serialize owner changes

Create users/workspaces/initial owner/audit together using the verified principal,
not client-selected owner fields. Use a shared resolver for stored membership.
All role/active-state mutations lock the workspace before member rows, then check
the exact target version and last-active-owner rule. Keep departed memberships
and private ownership for history; reactivation is explicit. Initial manual grants
target registered same-issuer IDs; invitation delivery/consent is a later flow.
See implementation 0008 for the concurrency proof, privacy boundary, and limitations.

## 0014 - Separate the verified workspace API from the legacy demo

Introduce an explicit bearer-authenticated API factory with a strict RS256
access-token profile and scoped PostgreSQL services. Do not mount legacy
unauthenticated routes into it, accept caller-asserted identity headers, or use
token role claims as workspace membership. No live provider is chosen; a compatible
provider/session flow still needs configuration and review. See implementation 0007.

## 0013 - Introduce PostgreSQL behind an internal authorized service first

Use SQLAlchemy Core transactions, psycopg, and explicit Alembic migrations. Keep
SQL values bound, scope relationships with composite workspace foreign keys, and
resolve membership inside every service transaction. Freeze migration definitions
instead of importing live models. Keep the legacy local UI operational while
verified request identity and remaining Stage 1 records are implemented; do not
expose the new service through self-asserted identity headers. See implementation 0005.

## 0012 - Establish reproducible verification and pure policies first

Use uv with a committed dependency lock, pytest invariants, Ruff, and a Windows/Linux
CI matrix before replacing persistence. Keep authorization policies independent
of HTTP and storage so cross-workspace privacy rules can be reviewed and tested.
Wire them only to verified identities and stored membership; standalone policy
tests do not establish API authentication. See implementation 0004 for boundaries.

## 0001 — Use a Python modular monolith first

**Decision:** Build the first backend as a single FastAPI application with separate domain, API, and persistence modules.

**Why:** Python fits the project's AI/API learning goals; FastAPI and Pydantic make HTTP contracts and validation visible. One deployable process is easier to learn and operate while requirements change.

**Trade-off:** Module boundaries need care because the application is not physically split. We will add services only when operational needs justify their network and deployment complexity.

## 0002 — Keep lifecycle decisions deterministic

**Decision:** Model work item transitions as explicit rules in ordinary code.

**Why:** A model may misread context. It can propose a status change, but server-side rules and authorized users determine what becomes canonical state.

## 0003 — Use SQLite only for local development

**Decision:** The current scaffold uses Python's standard-library SQLite driver for synthetic local data; the next multi-user storage design uses PostgreSQL and Alembic migrations.

**Why:** The first lifecycle could be learned without cloud infrastructure. SQLite is not suitable as the team's shared product database.

## 0004 — Reject stale state updates

**Decision:** Require an expected record version for status transitions and increment the version after accepted changes.

**Why:** A stale client should be told to reload instead of silently overwriting newer work. This is optimistic concurrency control.

## 0005 — Record state history atomically

**Decision:** Write a canonical state change and its event history in one transaction.

**Why:** The audit trail should not diverge from the state after a partial write.

## 0006 — External actions require exact human approval

**Decision:** Future email, messaging, calendar, and other provider actions must be approved against the exact destination and payload version that will execute.

**Why:** A generated tool call is not user authorization. Any edit invalidates the approval; execution re-checks identity and permissions and uses idempotency protection.

## 0007 — Position FlowPilot as a unified work coordination hub

**Decision:** Expand the product statement from an email commitment assistant to a cross-app work coordination hub while preserving commitment-to-completion as the core workflow.

**Why:** Gmail, Slack, Teams, notes, calendars, and future sources all matter because they carry overlapping work signals. The product's value comes from linking those signals to trackable work, not duplicating each provider's full UI.

**Trade-off:** The integration surface, permissions, and privacy model are larger than the first concept. We will add one connector at a time and validate with a constrained pilot.

## 0008 — Add provider integrations through adapters

**Decision:** Normalize source references behind provider-specific connector modules; keep provider scopes, webhooks, and APIs out of the core work-item model.

**Why:** Provider capability and access rules differ and change. Adapters limit the impact of those differences and make unsupported use cases explicit.

## 0009 — Start with manual/synthetic workflow, then read-only integration

**Decision:** Build and evaluate the unified workflow with synthetic/manual data before connecting a live source. The first live provider will be selected only after a scope and policy review.

**Why:** Gmail, Slack, Teams, and Keep each have distinct permission and account constraints. Designing the domain and UI with fixtures lowers risk and avoids assuming every API is available to every user.

## 0010 — Serve the first UI as a same-origin local web shell

**Decision:** Start with a small static dashboard served by FastAPI and use the existing local API for manual commitment capture and lifecycle changes. The first shell has no frontend build dependency and uses synthetic display-only inbox/schedule examples.

**Why:** This makes the product's daily workflow tangible while preserving the current local-only, synthetic-data boundary. Same-origin requests avoid adding a separate development server and cross-origin policy before there is an authenticated frontend architecture.

**Trade-off:** This is a deliberately small UI foundation, not a scalable client architecture. Before production, choose an authenticated frontend/session model, implement authorization, threat-model browser request protections, and decide whether static hosting or a separately deployed frontend is justified.

## 0011 — Use AWS as the planned deployment learning target

**Decision:** After access controls and PostgreSQL migrations exist, deploy the modular monolith as a container on ECS Fargate, store images in ECR, use RDS PostgreSQL, Secrets Manager, CloudWatch, Terraform, and GitHub Actions OIDC.

**Why:** This exercises practical cloud delivery, IAM, containers, managed data, infrastructure as code, observability, and secure CI/CD without prematurely splitting a learning project into microservices.

**Trade-off:** AWS creates ongoing cost and operational responsibility, and the current local API is not safe for public deployment. Do not provision resources until security readiness and a spending limit are agreed; budget alerts are delayed rather than real-time.
