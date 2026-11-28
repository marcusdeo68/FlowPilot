# Find blocked tasks from Today

Select **View blocked tasks** on Today to open **Work items** with **All work**
and **Blocked** selected. A task waiting for a speaker's reply appears even
if it has no due date. After the reply arrives, a user with write access can
choose **Resume task**. It leaves the blocked list when the update succeeds.

The shortcut clears the previous title search, project, and priority before
opening the list. It uses the existing paginated work endpoint with
`task_status=blocked`. The server applies membership and visibility checks
before returning rows. Opening Today does not fetch a second list of tasks.
The button provides navigation rather than a live count.

Chromium coverage starts with conflicting Work filters, opens the shortcut
by keyboard, checks the read request and focus, and resumes both an undated
task and a future-dated task until the empty state appears. See the
[status filter](0037-task-status-filter.md) for the underlying query and
the [tracker](../STATUS.md) for verification. Hosted pilot verification
still needs the Railway staging origin.
