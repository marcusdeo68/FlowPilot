# Implementation 0045 — Page through Due tasks

Select **Due tasks** under **Work items**. The list starts with the 20 earliest
unfinished deadlines matching the applied date, if one is selected. **Load more**
adds up to 20 more and keeps the same date. For example, if 21 tasks are due
on Monday, the last task appears on the second page with its usual task actions.

Due tasks now calls `GET /api/v2/workspaces/{workspace_id}/work-due-page`.
The existing query accepts an optional `from_date`. It verifies workspace
membership and filters for visible unfinished tasks before applying the cursor.
The last task's ID and version are the cursor. The server checks the version
under a shared row lock to keep the page boundary stable during the query.
Today still uses `/work-due` and applies the viewer's local day. Its API
response shape and the Schedule deadline list remain compatible.

A temporary page failure leaves the rows already loaded on screen. A stale
cursor or a task appearing again after another session reschedules it clears
the list. **Retry work list** starts again with the applied date.
The browser pauses task actions during a page append and pauses paging
while a task edit or update is active. After a write, the list reloads from
page one. Results reflect current records across requests.

PostgreSQL coverage checks paging with and without a date, including same-day
ties and cursor rejection. Chromium checks task actions after paging, both
retry paths, and Today’s existing behavior. See [STATUS](../STATUS.md) for
results. No migration is required. The next hosted milestone is synthetic
Railway staging verification once the staging environment is available.
