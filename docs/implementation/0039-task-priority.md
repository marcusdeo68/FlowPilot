# Implementation 0039 — Task priorities

Set **Task priority** to Low, Normal, or High when creating or editing a task.
For example, mark “Prepare budget” High, then choose **High** in the
**Priority filter**. The filter combines with project, title, status, and
visibility in the paginated Work views. Selecting a priority filter also
prefills it for new tasks created in that view.

The work creation route accepts `priority`, and the task details route accepts
it in the versioned edit payload. Older edit requests that omit priority keep
the current value. A task priority change advances the version and records
a details change. Filtering runs in PostgreSQL before pagination under the
existing visibility rules. The sharing preview shows task priority, and a
priority change invalidates an older sharing approval.

Apply `alembic upgrade head` before starting the updated workspace.
Migration `0011_task_priorities` stores Low and High overrides. Tasks with no
override read as Normal, including existing tasks. The database accepts
overrides only for tasks and safeguards downgrade while overrides exist.
Today and Due tasks continue to order by deadline.

PostgreSQL coverage exercises defaults, filters, private-task visibility,
versioned edits and downgrade behavior. Chromium covers changing a priority
and finding the task in its new filter. This increment gives tasks a manual
priority and leaves suggested priorities for a later increment.
