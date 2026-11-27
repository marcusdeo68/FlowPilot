# Implementation 0047 — Outsider audit of workspace workflows

## Schedule pagination

Schedule loads deadlines and timed events independently. For example, open
five deadlines and move the first one to a later date in another session.
The fifth deadline still identifies a valid page boundary, but the next page
can now include a newer copy of the first deadline.

The deadline and event requests return stable work IDs alongside the data
used for ordering. Comparing incoming IDs with the rows already displayed
lets the browser detect the overlap before showing two versions of the
same item. Retry reads the affected list from its first page using the
current selection. The other Schedule list keeps its place.

Each page reads current records. An item moving *earlier* than the boundary
can still require a refresh to become visible. An open Schedule is not a
snapshot spanning multiple requests.

## Task permissions on Today

Today reads tasks, upcoming events, and review suggestions in separate
requests. A task write can be the first response to tell the page that
access has changed. A forbidden task write must invalidate the other Today
panels too, including reads already in flight. Otherwise a delayed success
can put an old private title back on screen after the denial. Server-side
authorization continues to govern each new request.

Work also caches the project names used in its selectors. When a write
returns a forbidden response, the browser clears those names and discards
the role it had been using to offer write controls. Refreshing workspace
membership lets it decide which actions to offer again.

The audit also checked the written setup instructions against the current
entry points. The README now identifies which features belong to the signed-in
workspace, scopes the SQLite instructions to the loopback dashboard, and
includes syntax checks for the Notes and Inbox scripts.

## Finding an accepted inbox task

After accepting a suggestion, **Go to work list** opens All work and clears
the previous title, status, priority, and project selections. For example,
a previous Completed filter could hide the new open task even after a
successful acceptance. The shortcut changes only the list selection.

See the [maintenance tracker](../STATUS.md) for verification evidence and
the [Railway rehearsal](0046-hosted-image-rehearsal.md) for the remaining
live pilot checks.
