# Implementation 0019 — Task lifecycle and due view

In the signed-in workspace, owners and members can start, block, resume,
complete, or cancel tasks as their current state allows. They can update their
private tasks and visible shared tasks. A shared task's creator retains sole
control over its title, description, and due date. Observers and read-scoped
sessions can browse. Cancel requires confirmation, and completed and canceled
tasks are terminal.

The shell gets the task transition table from the same Python module that
validates writes. The browser posts the requested state, displayed version,
and session CSRF token through the existing transition route. The API checks
scopes. The service checks active membership and visibility, locks the task, and
commits its changed status and audit event together. A stale version or
unconfirmed write requires refresh before retry. The work-view selector pauses
while a status save is pending to avoid reading before the write completes.
Switching workspaces can leave an already-submitted write running. Its late
response cannot affect the newly selected workspace.

The **Due tasks** view sends a read request to `work-due`. PostgreSQL applies
visibility, task state and non-null due date filters before ordering by due date,
creation time, and ID. It fetches one extra eligible row to decide whether to
show the limit notice. The browser shows the earliest 20 deadlines, including
overdue dates. **All work** keeps the existing browse order and pagination. The
due view refreshes after an accepted change so it can backfill a completed or
canceled task with the next eligible result. If the refresh fails, the browser
keeps the save confirmation visible alongside the reload error. This is a live
view of stored dates.

For example, an open task created last month can come first in Due tasks even
if it has dropped past the first page of All work. Start and complete it, then
switch to All work to see its completed status. The due view shows the next
eligible task if more than 20 were available.

The builder and independent full runs passed 265 tests with real PostgreSQL and
Chromium. Due-view tests exercise scope, tenant and visibility boundaries,
deadline ordering, terminal and undated exclusions, and the bounded response.
Chromium covers the full task lifecycle, backfill, stale versions, read-only
controls, the pending-save view lock, late responses after navigation, and a
successful save followed by a failed refresh. See [STATUS](../STATUS.md) and the
PR for the refresh-feedback recheck and exact-revision evidence.

The increment uses the existing workspace PostgreSQL schema and synthetic
browser login setup. Reminder scheduling remains a later roadmap item. The next
increment can connect the authenticated private source inbox and proposal review.
