# Learning guide for the current foundation

This project assumes basic Python and Java knowledge, but limited experience with web services and production systems. The goal is to understand the request path and trade-offs, not memorize every line.

## Concepts in this increment

- **HTTP API:** routes map an HTTP method and URL to validated input and a response.
- **Pydantic schema:** a boundary that parses untrusted JSON and rejects invalid or unexpected fields.
- **Domain rule:** a product rule expressed independently of HTTP and storage. Here, not every status can transition to every other status.
- **Repository:** the module that translates domain operations into SQL.
- **Parameterized SQL:** values are sent separately from SQL syntax, preventing input from being interpreted as executable SQL.
- **Transaction:** a group of database writes that either all commit or all roll back.
- **Optimistic concurrency:** a client supplies the version it read; the server rejects the update if the record changed since then.
- **Append-only event history:** changes are recorded as new rows rather than overwriting past events.
- **Liveness vs readiness:** liveness answers whether the process responds; readiness checks whether a required dependency is available.

## Walk the request path

For a status update, start in `services/api/src/flowpilot_api/main.py` at the transition route. Follow the validated `CommitmentTransition` schema to `repository.transition_commitment`, then to `domain.can_transition` and the transaction in `database.py`. Note where the record version is checked, where the event is inserted, and how failures become HTTP `409` responses.

## Questions to be able to answer

1. Why can the model suggest a state change but not decide whether that change is legal?
2. Why are the status update and event insertion inside the same transaction?
3. What race does `expected_version` prevent?
4. Why does loopback binding not substitute for authentication in a deployed service?
5. Why must imported email be treated as data rather than trusted instructions?

## Verification and access policy exercises (increment 0004)

Read `tests/test_api.py` alongside `database.py`: deliberately failing an event
insert proves that the status update rolls back. Explain why a test that only
checks a successful response would miss this failure mode.

Read `access.py` and `tests/test_access.py`: compare workspace membership with
source ownership. Explain why an owner can read a shared task but cannot inherit
another member's private email. The policies are not yet wired into HTTP routes.

Read `work.py`: compare task and commitment states, then try an event with no
timestamp offset. Explain why an IANA display zone alone does not identify a
unique instant around daylight-saving changes.

Read `uv.lock` and `.github/workflows/ci.yml`: explain how a lock and fresh CI
environment reduce "works on my machine" failures. Track current gaps and the
next implementation milestone in [STATUS.md](STATUS.md).

## PostgreSQL and migration exercises (increment 0005)

Read `migrations/versions/0001_work_storage.py`: find a composite foreign key.
Explain which accidental cross-workspace relationship it blocks and why it cannot
decide whether a member is active. Trace a service transition from `_member` to
the work row lock, expected-version check, UPDATE RETURNING, and audit insertion.

Read `tests/test_postgres.py`: explain why each test uses its own schema and why
the test database must be explicitly named. Compare a migration downgrade on a
disposable test database with running that command on retained development data.

## Browser regression exercises (increment 0006)

Read the empty-dialog and whitespace-title tests in `tests/test_browser.py`.
Explain why the API suite passed even though Cancel and validation messages were
broken. Find the boundary where a structured error becomes user-visible text,
and explain why textContent matters for an injection-shaped title.

## Identity and authorization exercises (increment 0007)

Trace a token from HTTPBearer to signature/claim validation, API scopes, stored
membership, workspace query, and optimistic concurrency. Explain why all of these
checks are needed even when the signature is valid. Find the tests where an
observer includes an owner role claim and is still denied, and where an ID-token
type is rejected before an access token can be accepted.

## Workspace administration exercises (increment 0008)

Read `membership_service.py` beside the concurrent-owner-departure test. Explain
why checking an owner count without first taking the workspace lock would race,
and why a membership version alone would not protect two different owner rows.

Trace create_workspace: find the issuer/subject uniqueness constraint, the owner
membership insertion, and audit write. Explain why a failure must roll back all
three, while a read-only workspace-discovery request must not register an account.

Compare deactivating a membership with deleting an identity or source. Explain
why an expired privilege should deny new requests while preserving audit attribution
and keeping private source ownership with its original user.

## Review concurrency

Exercise for [0009](implementation/0009-private-task-review.md): open a proposal
in two clients and correct the title in one. Predict what happens when the other
accepts the old version. Then explain why the row lock alone cannot tell which
title a person actually reviewed.

## Paginating a private inbox

Exercise for [0010](implementation/0010-private-source-inbox.md): write down
four sources with identical capture times. Predict which IDs appear on each
two-item page, then add a newer source between requests. Why must the cursor
lookup use the same privacy filter as the list?

## Resources

For [0011](implementation/0011-dashboard-focus.md), compare a workspace with no
records to an unreachable workspace. Which one can safely display zero? Explain
why the 50 most recent rows cannot answer a question about every due commitment.

- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)
- [Pydantic model documentation](https://docs.pydantic.dev/latest/concepts/models/)
- [SQLite transactions](https://www.sqlite.org/lang_transaction.html)
- [PostgreSQL tutorial](https://www.postgresql.org/docs/current/tutorial.html)
