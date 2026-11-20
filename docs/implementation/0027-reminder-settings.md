# Implementation 0027 — Reminder settings

Open **Reminder settings** in a signed-in workspace. Choose **Due tasks**,
**Upcoming events**, or both. Events can appear 5, 15, 30, or 60 minutes before
their start. Choose 5, 15, or 30 minutes for future snoozes. For example, choose
upcoming events and 30 minutes to see a workshop scheduled in 20 minutes.
The reminder toggle still controls whether the tab fetches and shows reminders.

When enabled, the workspace sends the selected category and lead time to the
reminder endpoint. PostgreSQL queries only included categories with their
usual visibility rules, and uses the database clock for the event window.
The default remains both categories, 15 minutes of event lead, and five minutes
per snooze. A category or lead change clears the prior popup and invalidates
its pending request before fetching again. A snooze-duration change affects
future actions and keeps existing snooze deadlines.

Preferences, snoozes, and dismissals stay in memory per workspace in the open
signed-in tab. They reset when the page reloads or the session ends. The feature
uses the existing authorization and session binding and requires no schema or
provider change. Notification permissions and delivery outside an open tab
remain future work. The next increment can address workspace access management.

PostgreSQL verifies allowed categories, event windows, invalid options, and
authorization. Chromium exercises opt-in, workspace scoping, configured
snooze, reload behavior, and late responses after category changes. See
[STATUS](../STATUS.md) for verification.
