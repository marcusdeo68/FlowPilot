# Implementation 0044 — Filter Due tasks by date

In **Due tasks**, set **Show due tasks from** and select **Filter due tasks**.
For example, select Monday to manage unfinished tasks due Monday or later.
**Clear due date filter** restores the earliest deadlines, including overdue
work. **Open due tasks** in Schedule carries over the last applied date.
Choosing Due tasks directly from another Work view starts without a date.

The browser keeps the applied date separate from the date field so an unsubmitted
edit cannot change the list. Due tasks passes the date to the existing
`GET /api/v2/workspaces/{workspace_id}/work-due` endpoint as `from_date`.
The server applies workspace permissions and the date before limiting the
results. Today's request keeps its existing local calendar behavior.

The applied date stays in place through retries and task updates. The browser
disables the date controls while an editor or status update blocks Work view
changes, discards superseded list responses, and clears the date when the
workspace or session changes. Try this by applying a date, typing a different
one without submitting, and opening Due tasks from Schedule.

Chromium covers the handoff, retry, task completion, and workspace reset.
Existing PostgreSQL tests verify the date boundary and filtering before the
limit. See [STATUS](../STATUS.md) for results.

Due tasks shows up to 20 results. Schedule can page through more deadlines.
This increment requires no migration. A future increment can page through
filtered results directly in Due tasks. The hosted milestone remains synthetic
Railway staging verification.
