# Implementation 0023 — Upcoming events in Today

Today shows the five earliest visible scheduled events that overlap the next
168 hours. An event that started an hour ago and ends an hour from now appears,
along with future meetings inside the window. A canceled or ended event drops
out. Each start and end is shown in the event's saved time zone. If the browser
cannot format that zone, it displays both times in UTC.

Today reads `GET /api/v2/workspaces/{workspace_id}/work-events?limit=5`. After checking
read scope and active stored membership, PostgreSQL filters by workspace,
visibility, status, and time before applying the limit. It orders by the start
instant, then the ID. The query uses one transaction timestamp for both window
bounds and asks for one extra row to tell if more matching events exist.

To try it on loopback with the synthetic login setup, post a canonical event to
`POST /api/v2/workspaces/{workspace_id}/work`. Send an `item` with `kind` set to
`event`, a `title`, offset-bearing `starts_at` and `ends_at`, and an IANA
`time_zone` such as `America/New_York`. For example, give “Workshop rehearsal” a
start tomorrow at 9 a.m. Eastern and an end at 10 a.m. The existing creation
route defaults to private. Open Today to see the event in your workspace.

The panel retries its own transient failures and ignores obsolete responses
after navigation. Like the other Today reads, an active access denial clears
the view. PostgreSQL tests cover visibility, scope, filtering, tie order, and
limits. Chromium tests cover time display and UTC fallback, retry, denial,
and late responses.
See [STATUS](../STATUS.md) and the PR for verification.

This is a snapshot of canonical manual or synthetic events in the existing
database. The next increment can add manual event entry in the workspace.
