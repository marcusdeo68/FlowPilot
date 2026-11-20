# Implementation 0025 — Manual workspace events

Open **Today**, then **Open events**, or select **Events** under **Work items**.
Choose **New event**, enter its title and schedule, and save it to your workspace.
For example, add a synthetic workshop that starts at 11:30 p.m. in
`America/New_York` tonight and ends at 12:30 a.m. tomorrow. It appears in Events
and in Today when it overlaps the next seven days. The Events view also retains
ended and canceled records. It pages by when events were added.

The editor sends the local start, local end, and IANA time zone on a same-origin
request. The API tests both possible clock interpretations by converting to UTC
and back. It accepts a wall time only when exactly one instant survives the round
trip and the end follows the start. Enter a repeated hour in UTC when you need
to choose one of its two instants. Browsing shows the event's saved time zone
and falls back to UTC when the browser cannot format that zone.

The creation route delegates to the existing canonical work service. An event
starts private and scheduled. Its creator can edit its title, description, or
schedule. A text-only edit keeps the original instants. Cancellation uses the
existing scheduled-to-canceled transition, with access for active writers who
can see the event. An edited or canceled record and its metadata-only audit entry
commit in the same transaction. A version conflict keeps the draft visible and
requires a refresh before another save. After an unconfirmed response, check the
list before retrying. Ending the session clears the draft and ignores late UI
responses. An operation already accepted by the server can still commit.

PostgreSQL coverage exercises privacy, filtered pagination, version conflicts,
clock changes, an edit racing cancellation, and audit rollback. Chromium covers
entry, daylight-saving validation, rescheduling, cancellation, read-only access,
and recovery from a stale edit. See [STATUS](../STATUS.md) and the PR for results.
No migration or external account is needed for this increment. Calendar sync,
recurrence, and invitations are future capabilities. The next increment can
use the existing deadline and event records for in-app reminders on loopback.
