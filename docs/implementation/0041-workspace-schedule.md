# Implementation 0041 — Workspace Schedule

Choose **Schedule** from **Work view** or **Open schedule** on Today to see
ongoing and future manual events in chronological order. **Load more** adds the
next 20 entries. For example, a workshop scheduled two weeks from now appears in
Schedule. Open **Events** in **Work view** for event history, including ended and
canceled events. Schedule uses the existing event editor and sharing review.

The browser reads `GET /api/v2/workspaces/{workspace_id}/work-schedule`.
The API resolves a verified reader and active workspace membership before
querying PostgreSQL. The query filters by workspace, visible ownership or
sharing, scheduled status, and an end time still in the future. It orders by
start instant and ID so events with the same start can span page boundaries.
Times display in each event’s saved zone, with the existing UTC fallback.

The next request sends `after` and `after_version` from the last event on the
page. The server looks up that event under the same visibility rules and
holds a shared row lock from the version check through the page query.
The lock keeps its start time stable while the query uses it as a boundary.
This keeps the start time out of the URL and prevents a rescheduled boundary
from silently skipping rows. If it changed, **Retry work list** starts again
from the first page. An event that merely ends while paging can still serve as
a boundary. As in other Work views, each page reads current data. Refresh
after changes in another browser to get the latest ordering.

The PostgreSQL test covers time bounds, same-start ordering, malformed and
stale cursors, read scope, and visibility. The Chromium test covers paging,
retry after a changed cursor, cancellation, and switching workspaces while
a response is pending. See [STATUS](../STATUS.md) for results.

This increment uses the existing event schema. To try it locally, open the
[interactive preview](0040-local-workspace-preview.md), then select Schedule.
It displays manual events. Provider sync and open-tab reminders remain separate
workflows. A future increment can add due tasks to the schedule.
