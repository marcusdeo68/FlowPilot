# Implementation 0021 — Due work in Today

Select **Today** in the signed-in workspace to see overdue tasks and tasks due
today, with the earliest deadlines first. Work items still offers All work and
Due tasks for browsing. Today uses the existing task actions and authorization.

On load, Today gets the browser's local calendar date and requests 21 rows
through the existing `work-due` endpoint. The server already restricts the rows
to authorized unfinished dated tasks and sorts by due date. The browser compares
the saved calendar dates with the local day, shows up to 20 matches, and reports
overflow only when the 21st row also qualifies. An extra row with a future
deadline cannot cause the overflow notice.

For example, at 10:30 p.m. on January 2 in Los Angeles, an unfinished task due
January 1 shows as overdue, a January 2 task shows as due today, and a January 3
task is outside Today. The cutoff is recalculated when Today reloads. Completing
a task reloads the list so the next eligible task can appear.

The signed-in browser uses the existing PostgreSQL schema and API. Chromium
covers the local-day cutoff across a UTC date boundary, retry after a load
failure, the 20-task limit, and removing a completed task. See [STATUS](../STATUS.md)
and the PR for verification. Pending private reviews are the next increment.
