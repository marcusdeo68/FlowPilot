# Implementation 0042 — Upcoming deadlines in Schedule

Choose **Schedule** in **Work view** or **Open schedule** on Today. The
**Upcoming deadlines** section shows up to five unfinished tasks due today or
later. Timed events remain in the Events section below it. Choose **Open due
tasks** to manage tasks in the existing Due tasks view, which also includes
overdue deadlines. For example, at 10:30 p.m. on January 2 in Los Angeles, a
January 2 task still appears in Schedule even though the UTC date is January 3.

Schedule requests `GET /api/v2/workspaces/{workspace_id}/work-due?limit=5&from_date=YYYY-MM-DD`
using the browser’s local calendar date. The server validates the date and
passes it to the existing due-task service. PostgreSQL applies the inclusive
bound, active membership, work visibility, and unfinished task filters before
sorting or counting the extra row. The extra row determines whether to show the
limit notice. Today and Due tasks keep calling the route without a lower bound.

A due date identifies a calendar day. Its label is formatted with a UTC
formatter against a UTC date literal so it stays on the saved day in every
browser time zone. Events still display their scheduled times with time zones.
The sections load and retry independently. A current access denial while
loading Schedule or using its event and sharing controls clears both sections.
Responses from a workspace the user has left are discarded.

PostgreSQL coverage exercises date validation, inclusivity, visibility,
and limit calculation. Chromium covers a browser day that differs from UTC,
the limit notice, retry while events remain visible, navigation to Due tasks,
and access changes. See [STATUS](../STATUS.md) for execution evidence.

No migration is needed. Try both sections with the
[local workspace preview](0040-local-workspace-preview.md). The deadline section
is a preview of the five earliest matches. It reloads when reopening Schedule,
refreshing workspaces, or retrying. A future increment can add paginated deadline
browsing from a chosen date.
