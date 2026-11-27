# Implementation 0037 — Filter work by task status

In **Work items**, choose a **Task status** to find Open, Active, Blocked,
Completed, or Canceled tasks. For example, select **Shared work**, choose
**Blocked**, and search for “budget” to find blocked shared budget tasks.
Choose **Any status** to restore all work types in that view. The filter
works in All work, Shared work, and My private work. Today, Due tasks, and
Events retain their own lists.

The browser sends the selected status with its authorized work-page request.
It uses the same status field in the JSON body when title search is active.
PostgreSQL applies the bound status and task kind filters alongside workspace
and visibility checks before pagination. A canceled event therefore stays out
of the Canceled task results. The five values come from the existing task
lifecycle, and the API rejects unsupported values.

Changing a filter restarts pagination. If a task changes status while its page
is open, the refreshed list reflects the new status. An authorized cursor can
still locate the next page if its task changes status between requests. The
browser keeps the selected filter through in-app refreshes of the same workspace
and resets it on workspace changes, sign-out, or a browser reload. Clearing title
search leaves the status filter on.

PostgreSQL verification covers invalid statuses, visibility, status changes
between pages, and matching tasks while excluding events. Chromium exercises
combining title search with a status and starting a task from the filtered
results. There is no schema migration. This increment filters existing work
and leaves project grouping for a later increment.
