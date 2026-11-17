# Implementation 0014 - Browse all authorized work

## Behavior and request path

The separate workspace API adds `GET /api/v2/workspaces/{id}/work-page` with
`limit` (1–100, default 50) and optional UUID `after`. It returns `items` and
`next_after`; a null cursor means the current traversal is complete. Existing
`/work` retains its list response and updated-time ordering.

The verified read identity enters `WorkService.list_work_page`, which resolves
active stored membership inside a transaction. A supplied pivot goes through the
existing authorized work lookup. Private, foreign and absent pivots all fail with
the same 404. Queries bind SQL parameters and restrict both workspace and visibility.
Reads do not change work, permissions or audit history.

## Why this structure

Ordering uses creation time and UUID, both descending. A page fetches one extra
authorized row to decide whether another page exists. The last returned UUID is
the continuation cursor. Status updates change `updated_at`, so using that field
would allow a task to move across page boundaries during ordinary work.
Creation ordering and the UUID tie breaker avoid that movement and equal-time
ambiguity. This follows the existing source-inbox pagination pattern without
introducing a second storage adapter or changing the old endpoint contract.

## Concrete example

Request `work-page?limit=2`. If three visible tasks exist, the response contains
two and `next_after` equal to the second task's ID. Request
`work-page?limit=2&after=<that UUID>` to receive the remaining task and a null
cursor. A teammate's private tasks never count toward the extra-row lookahead.
Read-only API scopes and observer memberships can browse permitted shared work.

## Validation and limits

New real-PostgreSQL tests cover traversal beyond the old 100-item cap, timestamp
ties, status updates/new arrivals between pages, empty/end pages, private work visibility,
foreign/unknown cursors, inactive memberships, observer access and unchanged audit
counts. Signed HTTP checks cover authentication, scopes, query validation and the
old list contract. Final execution evidence is recorded in [STATUS](../STATUS.md).

Independent working-tree verification over base `6209526`: full enabled pytest
passed 181 tests with zero skips (111 ordinary, 55 PostgreSQL, 15 Chromium).
Ruff check/format, pinned Pyright 1.1.407 (zero diagnostics), sdist/wheel build,
JavaScript syntax and local documentation links passed. Use README verification
commands and the PostgreSQL/browser environment in implementation 0013. Initial
sandbox network restrictions were resolved by authorized host execution; they
were not counted as passing checks. Candidate CI remains required before merge.

This is a live traversal, not a snapshot across requests. Newer work appears on
refresh; newly shared older work can appear in subsequent pages. If a pivot is
deleted or becomes inaccessible, restart from the first page. Clients must retain
the selected workspace with the cursor and clear their view when authorization
fails. Production query-plan/index tuning and richer filtering are future work;
no schema migration is needed for this synthetic-data increment.

## Next increment

Complete identity-provider review and sign-in/callback before wiring the
authenticated workspace UI. This read capability prepares the Tasks surface but
does not enable live accounts, reminders, AI or provider actions.
