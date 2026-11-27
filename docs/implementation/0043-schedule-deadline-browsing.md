# Implementation 0043 — Browse task deadlines

Open **Schedule** and choose **Show deadlines from**. Set a date and select
**Show deadlines**. For example, select next Monday to see unfinished tasks
due Monday or later. **Load more deadlines** adds five rows at a time.
The default is today in the browser’s local calendar. The date applies to
tasks, and the adjacent event list keeps its own ordering and paging.

The browser reads `GET /api/v2/workspaces/{workspace_id}/work-due-page` with
`from_date` and an optional cursor made of the last task’s ID and version.
The due-task query checks stored membership and filters work by visibility,
status, and date before paging. It sorts by due date ascending, then by
creation time and ID descending. The server holds a shared lock on the
authorized cursor task through the page query. The version check detects a
change to that task and lets the browser retry from the first page of the
same date. Later pages reflect current records, so reapply the date after
other sessions reschedule or complete tasks.

The PostgreSQL check covers same-day pagination and cursor rejection.
Chromium covers date selection, recovery from a transient paging failure,
workspace switching, and access denial. See [STATUS](../STATUS.md) for results.

Existing Today and Due tasks requests keep their response shape. No migration
or new service is required. Try it in the [local preview](0040-local-workspace-preview.md).
The hosted pilot still needs verification through Railway’s public ingress.
The next local workflow can bring date filtering into **Due tasks** so users
can manage deadlines for a selected period directly.
