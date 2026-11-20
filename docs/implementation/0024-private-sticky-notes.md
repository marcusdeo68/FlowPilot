# Implementation 0024 — Private sticky notes

Open **Notes** in the signed-in workspace to write a plain-text card up to 2,000
characters long. For example, capture “Bring the workshop agenda” and add a
second line as you plan. Archive the note when finished. Use **Archived notes**
to find and restore it. Notes are visible only to their author in the selected
workspace. Observers and read-scoped sessions can browse their own saved notes.

The signed workspace routes use the existing bearer or browser session checks.
Cookie writes use CSRF. The service resolves active membership and scopes every
row and cursor by workspace and author. Notes page by creation time and ID, so
edits preserve card order and moving the last note on a page preserves its
cursor. The browser displays only literal text.

Each edit, archive, or restore locks the note and compares its expected version.
The updated note and a metadata-only audit record commit together. Conflicts
keep the draft visible until its author closes the editor and refreshes. A save
with an uncertain outcome also requires an explicit refresh before retry.
Close the editor before switching or refreshing workspaces. An admitted write
can still commit if the session ends. Ending the session or leaving Notes clears
its private UI state.

Apply `alembic upgrade head` to the workspace database before starting the
updated API. Revision `0008_private_notes` creates notes and append-only audit
history. A downgrade can remove the empty schema. It refuses to drop saved
notes. Archiving retains text. Permanent deletion and retention controls remain
future work. Use synthetic data on loopback with the current login setup.

PostgreSQL coverage includes owner and workspace checks, archive and restore,
cursor traversal, version races, audit rollback, and migration behavior.
Chromium covers editing and archiving, stale drafts, an uncertain create,
read-only sessions, and late responses after switching workspaces. See [STATUS](../STATUS.md) and the PR
for verification. The next roadmap item is manual event entry.
