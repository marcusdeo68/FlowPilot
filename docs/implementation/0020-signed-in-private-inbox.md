# Implementation 0020 — Signed-in private inbox

Open **Private inbox** from the signed-in workspace. Owners and members with
write scope can add a manual source with a reference, summary, and excerpt.
The inbox lists the caller's own sources newest first and loads more using
the source cursor. Open a row to read the saved evidence and suggest one task.
Observers and read-scoped sessions can browse their own existing sources.

For example, capture a synthetic note with reference `workshop-01`, summary
“Prepare the workshop packet”, and excerpt “Include the agenda”. Select
**Suggest task**, change the title to “Send the workshop packet”, choose a due
date, and save. **Accept and create task** uses the saved title, date, and
displayed version. The resulting private task is available in Work items, with
the source stored as private evidence. **Dismiss suggestion** closes the review
without creating a task. Both outcomes remain visible in the inbox.

The list uses `GET /sources`. Opening a row fetches the source and the latest
version of the proposal identified in that row. Refresh the inbox to discover a
suggestion created in another tab since the list was loaded. The workspace's
inbox script manages pagination and the opened row independently of the work
list. Source strings are rendered as text. The browser
sends same-origin requests with the session's CSRF token for mutations. The API
checks scopes and the service rechecks active membership and source ownership
inside its transactions. Accepting a proposal commits the task, evidence, and
audit entries together through the existing service.

An unsaved edit or incomplete date pauses the review buttons. Save valid edits
before reviewing the suggestion. After a conflict or unconfirmed decision,
reload source details to check the saved state. A source capture with an uncertain response preserves
the draft and asks for an inbox refresh before another save. For a matching
reference, PostgreSQL prevents a duplicate within that workspace and source
owner. Changing workspace, switching to Work items, and signing out clear the
inbox view and drafts. Switching to Work items pauses during an inbox save so
the work list can read after acceptance. Workspace switching and sign-out can
leave a request running if the server has already admitted it.
If the server denies access, the browser clears the inbox and shows write
controls again only after a fresh workspace role is loaded.

Chromium tests cover browsing past the first page, reviewing a saved correction,
dismissal, a partially entered date, and recovery when a committed response is
lost. The tests also exercise observer downgrade, read-only sessions, and late
responses after a workspace change. See [STATUS](../STATUS.md) and the PR for
test results on the exact revision.

The implementation uses manual synthetic sources, the existing database schema,
and the same loopback login setup. Provider import and inference are later
increments. A next increment can combine due work and pending reviews in a
signed-in Today view.
