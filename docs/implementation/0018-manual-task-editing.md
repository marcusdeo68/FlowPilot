# Implementation 0018 — Create and edit tasks in the workspace

After sign-in, members and workspace owners can open **New task** in the selected
workspace. A new task starts private and open. Its creator can then edit its title,
description, and due date. The work list shows the optional description and due
date. A task that its creator already shared keeps its existing visibility.

The browser uses the existing POST work contract for creation and sends the
loaded version with the complete details to PATCH task-details. Both requests
use the session's CSRF token. The API checks read and write scopes, then the
service locks the active membership and visible task before checking authorship
and version. Changes and an append-only `details_changed` event commit together.
The event records actor, time, status and version. Task text is stored on the task.
Submitting identical details at the current version leaves the row and audit
history as they are.

For example, create “Confirm venue” with a due date of 2026-12-04. If another tab
updates the task while the editor is open, the first tab receives a conflict and
keeps its draft visible. Close the editor, refresh the work list and reopen the
task to work from the latest version. Dates travel as calendar dates, so the
browser displays the saved date without a time zone conversion.
The fields stay read-only while a save is pending. When a field is unchanged,
the editor sends its saved text, including any original line endings.

Migration `0007_task_details_audit` extends the existing audit constraint. Apply
`alembic upgrade head` before starting the updated workspace API. The previous
constraint can be restored when there is no task edit history. PostgreSQL rejects
that downgrade once a detail edit is recorded, preserving the audit records.

The editor covers details on a task created by the signed-in identity, including
tasks accepted from that user's private suggestions. Status changes, sharing,
evidence, and external actions use their separate workflows. Changing workspace
or ending the session clears the editor and discards late responses in the browser.
A save already accepted by the server can still commit in its original workspace.

The independent run passed 261 tests with zero skips against local PostgreSQL
and Chromium. The browser test covers task creation, editing, a pending save,
existing multiline content, and recovery from a conflicting edit. PostgreSQL
tests cover scope and membership checks, stale versions, audit rollback, and
the downgrade restriction. Lint, formatting, Pyright, packaging, JavaScript
syntax, and local documentation links passed. See [STATUS](../STATUS.md) for the
checkpoint and the PR for exact-revision CI. The next increment can add task
status controls or the private inbox review surface.
