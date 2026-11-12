# Implementation 0004 - Verification and access policy groundwork

Status: implemented and locally verified. This is the first portion of Stage 1;
PostgreSQL, migrations, verified request identity, and policy wiring remain open.

## Changes and reasons

The project now has a managed Python environment, a committed `uv.lock`, pytest
regression tests, Ruff checks, package builds, and GitHub Actions for Python 3.11
and 3.12 on Windows and Linux. A lock records exact dependency resolutions so a
fresh checkout can reproduce the environment. CI uses read-only repository
permissions, immutable action revisions, and no retained checkout credentials.
Dependabot proposes dependency and action updates; it cannot merge them itself.

Workspace-scoped Cursor/VS Code settings select `.venv`, enable pytest discovery,
and provide Run local app and Tests tasks. They use the environment executable
directly, avoiding terminal activation and global PATH dependence. No machine-wide
editor settings were changed. Future projects belong under the user's CODE folder;
this existing checkout remains in its original location until explicitly migrated.

The existing SQLite event table now rejects updates and deletes with triggers.
Tests intentionally fail an audit insertion and verify that the state change
rolls back too. A concurrent-write test proves only one client can apply a given
record version. These are observable invariants rather than tests of private
implementation details. SQL injection-shaped text is stored as text.

The local HTTP service accepts only localhost and 127.0.0.1 hostnames and rejects
browser writes from foreign origins or cross-site fetches. The dashboard receives
a restrictive Content Security Policy, anti-framing, no-referrer, and MIME-sniffing
protection. These reduce browser attacks on a running local demo; they do not
authenticate a user. Clients outside a browser can omit Origin, so loopback and
synthetic-data restrictions remain essential. Development OpenAPI pages are
excluded from CSP because their generated UI uses external scripts/styles.

The dashboard now exposes Confirm, Start, Resume, and Resolve & confirm as explicit
steps. Only active commitments can be completed with the checkbox. Previously
one click silently walked several lifecycle transitions. On a conflict it reloads
state before retrying, retaining the server as the authority.

## Access and domain concepts

`access.py` encodes owner/member/observer capabilities, inactive membership denial,
workspace matching, private-source ownership, and evidence projection. Owners
cannot read another member's private source. Shared summaries and shared excerpts
are distinct decisions; source bodies and provenance URLs are not inherited.
Connection actions require an active writer who owns an unrevoked connection.
Unknown roles and visibility values fail closed.

These are pure functions: no network, database, or framework dependency. They are
not authentication and are not currently applied to the legacy local API. Future
services must load membership from stored records using verified identity, scope
every repository query, authorize the work item before projecting evidence, and
record an explicit source-owner sharing decision. A client must never construct
its own Membership or self-assert a role. Python annotations alone are not a trust
boundary; the policies also reject unknown values at runtime.

`work.py` defines discriminated commitment, task, and event contracts. The `kind`
field selects a concrete schema. Tasks do not inherit commitment confirmation;
events require offset-aware timestamps, an IANA display zone, and a positive
interval. The schemas describe canonical state, not permission to create arbitrary
states. Future command services must establish initial states and authorize
rescheduling, assignment, sharing, and transitions. No new work routes exist yet.

## Verification and remaining limits

Run the commands in README for tests, formatting, linting, and package builds.
API checks use isolated temporary databases and synthetic values. JavaScript has
a syntax check; interactive browser automation is a remaining gap. The environment
currently emits an upstream Starlette/httpx deprecation warning; tests still pass.

Next: introduce PostgreSQL/SQLAlchemy and reversible Alembic migrations, test
composite workspace relationships and source/evidence isolation against real
PostgreSQL, then select verified authentication and wire service authorization.
Keep the unauthenticated SQLite dashboard on loopback until that is complete.
No live providers, sending, AI extraction, or AWS resources were enabled here.

## Portfolio evidence

This increment demonstrates reproducible environments, CI matrices, concurrency
control, transaction failure testing, database constraints, browser request
boundaries, authorization policy testing, and typed domain modeling. Useful future
tooling includes PostgreSQL integration tests, Playwright for browser workflows,
and CodeQL for static analysis. Each should be introduced when it verifies an
implemented feature rather than merely adding another tool name.

References: [uv installation](https://docs.astral.sh/uv/getting-started/installation/),
[GitHub Python CI](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
