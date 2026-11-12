# Implementation 0005 - PostgreSQL work storage and authorized services

Status: internal storage/service slice implemented; hosted verification in progress.
The PostgreSQL adapter is an internal synthetic-data foundation. The dashboard
continues to use its existing unauthenticated SQLite API.

## What changed and why

Alembic manages an explicit, reversible PostgreSQL schema. SQLAlchemy manages
connections and transactions through psycopg. The schema covers users, workspaces,
memberships, manual sources, typed work items, evidence links, and append-only
audit events. Provider connections, projects, proposals, approvals, and executions
will be later migrations; no placeholder token store or sending code is present.

The initial migration is a frozen schema definition. It does not import evolving
application models, which would make replaying an old migration depend on future
code. Migrations are an operator command, not an automatic startup side effect.
The SQLAlchemy adapter requires an explicit PostgreSQL URL and hides SQL parameter
values in exceptions. It never silently selects a different database.

## Data path and authorization

`WorkService` receives an internal Principal containing issuer and subject, resolves
it through stored users, then loads the active workspace membership inside the
operation's transaction. Issuer and subject together distinguish identities from
different identity providers. A future HTTP authentication dependency must verify
these values; they must never come from a body or self-asserted identity header.
No new HTTP routes are enabled by this increment.

Each work query scopes both workspace and visibility. Private work belongs to its
creator; even workspace owners cannot read it by guessing its UUID. Workspace IDs
are selectors whose membership must be proven. Foreign and absent work IDs both
produce WorkNotFound. Observer writes and inactive memberships fail authorization.
Membership row locks keep a concurrent removal from racing past an in-flight
operation; after removal commits, the next operation is denied. Membership
administration and protection of the last active owner are not implemented yet.

Creation establishes initial states: tasks start open, commitments detected,
events scheduled. It cannot use a canonical schema to create a completed task.
Status changes lock the current row, require the expected version, validate the
typed lifecycle, update state, and append an attributed audit event atomically.
This serializes competing writes while still detecting stale client versions.

## Concrete source-privacy example

A member manually stores a synthetic source and creates a private task. Sharing
the task explicitly increments its version and records an audit event; it does
not share the source. Only the source owner can link evidence or choose private,
summary_shared, or excerpt_shared visibility. A workspace owner sees either no
evidence, the approved summary, or the approved excerpt. No source ID, reference,
or URL is inherited in that response. The source owner can inspect their linked
summary and excerpt once authorized to view the work item.

Sources are immutable through this service. Before adding source updates or sync,
version evidence and require renewed consent when an approved excerpt changes.
Editing/revoking a share and retention/deletion workflows remain future commands.
The sharing decision stores actor, time, and selected visibility in evidence_links.
Audit history deliberately stores operation, actor, status, and version rather
than message content. Manual source creation adds a source-targeted audit event
in the same transaction; it is excluded from work history and has no body text.

An owner can retrieve their own manual source by ID through the internal service;
other viewers receive SourceNotFound even if they can read a shared excerpt.

## Constraints as a second boundary

Composite foreign keys include workspace identity. Linking work in workspace A
to a source in B fails even if an application check is accidentally omitted.
Membership references also keep creator, assignee, and source owner in the same
workspace. These constraints do not replace authorization: an inactive member
still has a historical row, so the service must recheck active membership.

PostgreSQL checks enforce valid kind/status combinations and event intervals.
Pydantic additionally validates IANA zones and offset-aware timestamp inputs.
Database triggers reject audit updates/deletes and TRUNCATE. Administrators can still
alter triggers; before deployment use separate migration/runtime roles, backups,
and a reviewed database permission model. Row-level security is not enabled.

## Local setup

Install Docker separately if desired, then from the checkout:

```powershell
docker compose up -d --wait
$env:FLOWPILOT_DATABASE_URL = 'postgresql+psycopg://flowpilot:synthetic-dev-only@127.0.0.1:5432/flowpilot_dev'
uv run --locked alembic upgrade head
uv run --locked alembic current
docker compose stop
```

The Compose database binds to loopback and uses explicitly synthetic development
credentials. The named volume preserves development records. No AWS resources
are involved. Do not use these credentials or this Compose definition in production.
`alembic downgrade base` drops the seven tables and their data; use it only on a
disposable development database. It does not migrate or delete legacy SQLite data.

## Verification

The integration suite requires FLOWPILOT_TEST_DATABASE_URL with a database name
ending `_test`. Every test creates its own random schema, applies migrations, and
cleans up only that schema. It never truncates public tables. GitHub Actions runs
these tests against a fresh PostgreSQL 17 service; the normal cross-platform suite
skips them when no test URL is set. CI includes migration downgrade/upgrade,
cross-workspace reads/writes and foreign keys, observer denial, inactive membership,
source-owner sharing, stale versions, concurrent writers, audit failure rollback,
append-only enforcement, and event timestamps. Local PostgreSQL availability and
hosted results will be recorded before merge.

## Next increment and learning

Select and implement verified identity, authenticated route/session protection,
membership administration, and policy wiring before replacing the dashboard's
SQLite API. Then add proposal review and synthetic source workflows. Current
internal service tests do not authenticate any network request.

Trace `create_work` through `_member`, INSERT RETURNING, `_stored`, `_audit`, and
the transaction context. Explain why a foreign key cannot enforce active membership,
and why a workspace-qualified source link still needs a source-owner check.

References: [SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/core/connections.html),
[Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
