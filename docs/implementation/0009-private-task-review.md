# 0009 — Review a task suggested from a manual source

A member can now take one synthetic source through to a private, open task in the
verified workspace API. The suggestion copies up to 200 characters of the source
summary as a starting title. It never interprets a message as a command, infers a
deadline, or contacts a provider. Only the source owner can see the suggestion.

## Try the request sequence

Use the configured loopback workspace API, a compatible test identity, and a
workspace where the caller can write. All paths below are relative to
`/api/v2/workspaces/{workspace_id}`. The existing source endpoint accepts a
reference, summary and excerpt. For example, enter “Draft the workshop agenda”
as the summary and “Include breaks” as the excerpt.

| Request | What the caller sees |
| --- | --- |
| `PUT /sources/{source_id}/task-proposal` | Private pending proposal, version 1, no work ID. Repeating the call returns its current state, even after dismissal. |
| `GET /proposals` | Only this member's pending proposals; default 50, max 100. |
| `GET /proposals/{id}` | Exact current title, due date, state and version, including closed proposals. Read the original evidence via the owner-only source endpoint. |
| `PATCH /proposals/{id}` | Send `{"title":"Circulate the agenda","due_date":null,"expected_version":1}`. Both editable fields are required. A correction increments the version and leaves the proposal pending. |
| `POST /proposals/{id}/review` | Send `{"decision":"accept","expected_version":2}`. Response includes a private task ID. Use `dismiss` instead to close without creating work. |

## How the pieces fit

The route verifies API scopes; the service resolves active membership inside
each database transaction. Every lookup includes workspace and source owner.
An observer may read their own prior proposals but may not change them. Even a
workspace owner cannot inspect another person's private review queue.

There are two distinct retry problems. Simultaneous suggestion requests meet a
unique workspace/source constraint and reuse the same proposal. On review,
PostgreSQL locks the proposal row before the service checks both the version
and pending state. A second acceptance therefore sees a closed proposal and
returns 409. A stale version after an edit also returns 409: reload the proposal
and review the new fields. After a lost response, GET the proposal to recover the
result; do not silently replace the expected version and resubmit.

Acceptance inserts the reviewed task, its creation audit, the private evidence
link, the proposal decision, and its audit event on **one connection in one
transaction**. For instance, if the last audit insert fails, the task disappears
on rollback and the original proposal remains pending. An evidence link present
from creation is part of work version 1. Sharing the task later does not share
the excerpt. The proposal audit stores operation, actor, version and time, not
the source body or a copy of each edited title.

## Migration, tests, and limits

Revision `0003_task_proposals` adds only `task_proposals` and `proposal_events`.
Foreign keys tie the proposal to the source and its owner in the same workspace.
Triggers prevent rewriting or truncating review history. Development downgrade
drops proposals and review history while preserving accepted tasks, evidence, and
their work history. A later re-upgrade cannot reconstruct the lost decisions;
do not run suggestion generation after a downgrade expecting deduplication across
that data loss.

Tests in `tests/test_proposals.py` cover input contracts, two concurrent suggestions,
competing accepts, stale corrections, atomic rollback, immutable history, revoked
memberships, tenant/owner privacy, and a signed HTTP correction-to-acceptance path.
The local full suite passed 91 tests (including six Chromium workflows); 40 tests
require PostgreSQL and run in the separate CI job. The browser tests still cover
the legacy UI only.

There is one task suggestion per source. Multiple candidates, events, commitments,
AI extraction, expiry, and outbound action approvals are separate work. Next,
make manual sources discoverable so a client can return to review without
saving source IDs itself. Browser sign-in and UI integration remain open.
