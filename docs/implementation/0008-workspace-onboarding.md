# Implementation 0008 - Workspace onboarding and membership administration

Status: merged in PR #7. Run 43285798866 passed all six CI jobs for commit
7347ff0: 81 backend/contract tests, 35 real PostgreSQL/service/API tests, and six
Chromium workflows, plus lint, formatting, JavaScript syntax, and package builds
on Windows/Linux Python 3.11/3.12. Local full suite: 87 passed, 35 PostgreSQL
checks explicitly skipped because they run against a real database in CI.

## What this enables

A verified API user can create a workspace, discover their active workspaces, and
read their own internal user ID without manual database setup. Workspace owners
can list members, grant membership to an already registered user of the same
issuer, explicitly change roles/active state, and inspect membership audit history.
The legacy dashboard remains a separate local demo. Browser login, a real identity
provider, and invitation/consent screens are not introduced here.

## Request and data path

The existing bearer dependency verifies signature, issuer, audience, and API scope.
Creating a workspace uses the verified issuer/subject to get or create an internal
user. The request contains only a workspace name, not an owner ID or role claim.
In one transaction the server creates the workspace, creates an active owner
membership, and records a workspace_created event. An audit failure rolls back
the user creation too. Read-only discovery never creates a user as a side effect.

The issuer/subject uniqueness constraint plus INSERT ON CONFLICT DO NOTHING handles
simultaneous onboarding for one identity. Separate explicit workspace-create
requests create separate workspaces; that endpoint is not idempotent. Clients must
not blindly retry a timed-out create. Future UI should prevent double submission;
request-key idempotency is a future reliability increment.

Stored-membership resolution now lives in `member_context.py`. Both work and admin
services use it, avoiding divergent interpretations of active membership or roles.
API scopes remain separate from membership: read scope permits only authorized
reads, write scope is also required for mutations, and only stored owners may
administer membership. There is no public account directory.

## Example: transfer ownership before leaving

An owner wants to leave. Removing or demoting that sole active owner returns 409.
They first promote an existing member to owner using that member's exact version.
They can then deactivate their own membership using their own exact version.
The same bearer token is still a valid identity, but future workspace operations
are denied because stored membership is inactive. Other workspace memberships
are unaffected; private work/source records retain their original ownership.

Rejoining an inactive membership requires an explicit versioned change; calling
the add-member endpoint cannot silently reactivate someone or overwrite their
role. A former member cannot reactivate themselves. An active owner must authorize
the change, which is recorded in history. This is not account deletion or a data
retention workflow.

## Concurrency and transaction reasoning

Every membership mutation locks its workspace row before resolving the actor and
locking the target membership. Consequently, two owners cannot both observe two
owners and remove themselves concurrently. One completes first; the second sees
the new owner count and is rejected. Changes in different workspaces do not share
this lock. Version checks separately reject stale client edits.

Existing work operations hold a shared lock on their actor's membership during
their transaction. Removal waits for an in-flight operation, then later operations
are denied. An already authorized response may finish in transit; removing a
member cannot retract bytes already delivered or cached by their device.

The rule applies to all exposed membership mutation paths. Direct database
administrators can bypass application policy. Separate runtime/migration roles and
operational access controls remain deployment requirements, not guarantees supplied
by a cross-row CHECK constraint.

## Migration and audit

Revision 0002_membership_admin adds membership versions and a workspace_events
table. Foreign keys bind actor and target to historical memberships in the same
workspace. Events contain IDs, operation, before/after role and active state,
version, and time; no email, token, or message content. Triggers reject updates,
deletes, and TRUNCATE. Permission changes and their event commit together.

Before upgrading, the migration rejects existing workspaces without an active
owner. It does not guess who should own an orphaned workspace; an operator must
repair development data explicitly. Readiness now checks a central schema revision
constant, so an old schema returns 503 rather than being described as ready.

Downgrading this revision on a disposable development database preserves users,
workspaces, work, and the current membership roles/active flags. It removes the new
version column and membership audit history; it does not undo business changes or
restore old permission decisions. Never treat migration rollback as a data backup.

## API contract

- GET /api/v2/me: own internal user ID, or 404 before onboarding.
- GET /api/v2/workspaces: active workspaces for the verified identity only.
- POST /api/v2/workspaces: `{ "name": "Synthetic team" }`; creates caller as owner.
- GET /api/v2/workspaces/{id}/members: owner-only member IDs, roles, active flags,
  and versions. Lists include inactive records for explicit reactivation.
- POST /api/v2/workspaces/{id}/members: `{ "user_id": "UUID", "role": "member" }`.
- PATCH /api/v2/workspaces/{id}/members/{user_id}: role, active (strict boolean),
  and expected_version (positive strict integer), all explicit.
- GET /api/v2/workspaces/{id}/membership-history: owner-only bounded audit history.

Lists default to 50 and cap at 100. Full pagination is not implemented. Unknown
JSON properties and invalid/blank/NUL workspace names fail validation. Member and
observer roles cannot list administration history or grant roles. Membership reads
still require stored owner capability, even with an API read scope.

## Privacy and current product limits

This is a manual membership grant, not an email invitation. A target first completes
their own onboarding and deliberately shares their own user ID; an owner can then
grant them access to workspace-visible records. The API does not enumerate another
user's identity claims or send a message. Real invitations should add recipient
confirmation, expiration, and reviewed notification delivery before a production
team onboarding experience. Membership never exposes personal sources by inheritance.

No new provider, network credential, OAuth scope, or AWS resource is introduced.
Compatible identity-provider setup, browser sessions, dashboard migration, request
limits, and retention/deletion controls remain open. Use synthetic data on loopback.

## Verification and learning

Local baseline and contract tests are run before CI. The real PostgreSQL suite
tests atomic onboarding, concurrent identity registration, role authorization,
issuer/workspace isolation, stale versions, reactivation, ownership transfer,
concurrent owner departures, permission revocation, audit rollback/immutability,
migration rollback, and signed-token HTTP requests. The evidence above verifies
the exact merged source; PostgreSQL is tested in CI rather than replaced with SQLite mocks.

Trace create_workspace through its transaction and explain why a user and workspace
must not survive an audit failure. Then trace two concurrent owner departures:
explain what the workspace row lock protects versus what expected_version protects.
Finally, explain why deactivating membership should not transfer private messages
or delete audit attribution.

References: [PostgreSQL row locks](https://www.postgresql.org/docs/17/explicit-locking.html),
[PostgreSQL INSERT conflicts](https://www.postgresql.org/docs/current/sql-insert.html).
