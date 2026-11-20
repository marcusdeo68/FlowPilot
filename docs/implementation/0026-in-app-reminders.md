# Implementation 0026 — In-app reminders

Turn on **In-app reminders** after selecting a workspace. If a task is due today
or an event starts within 15 minutes, its name appears in a group under the
workspace navigation. For example, create a synthetic agenda task due today and
an event that starts in 10 minutes. **Snooze 5 minutes** clears that group until
the affected items are eligible again after the snooze. **Dismiss reminders**
suppresses that occurrence for the current sign-in in this tab.

The browser sends its local calendar date to a read-only workspace endpoint.
PostgreSQL filters by active membership, work visibility, date or start time,
and work status before taking up to five candidates of each kind. This lets a
due-today task or a near event appear even when many tasks are overdue or events
are already in progress. The payload contains each candidate's ID, title, and
deadline or start instant. The API compares event starts to its own clock and
returns the start in UTC for a stable occurrence key.

The browser polls sequentially while the tab is visible. A separate timer
clears expired reminders at the event start or local midnight even if a poll
is still in flight. Turning the feature
off, switching workspaces, or ending the session clears the popup immediately
and invalidates pending responses. Cookie reads carry the tab's session binding
so a replacement cookie cannot return data to an older page using its stale
token. Opt-in, snooze, and dismissal state live in memory per workspace until
the session or page ends. Dismissal keys use the ID and due date or start instant.
A title edit keeps the same key. Rescheduling changes it.

The endpoint returns bounded groups. Items beyond the batch can be found in
Work items. Snoozes reappear only after a fresh authorized poll, as available
within the batch. Missed, already-started, or overdue items do not trigger
catch-up reminders. This increment requires no database migration or outside
service. Browser/OS notifications, cross-device settings, and closed-app
delivery are future capabilities. The next increment can add open-tab timing
and category controls.

PostgreSQL tests cover visibility, the bounded task and event filters, read
scope, membership revocation and payload fields. Chromium tests cover opt-in,
retry, grouped popup, snooze, dismissal, a reschedule, stale workspace responses,
and cookie replacement. See [STATUS](../STATUS.md) for verification evidence.
