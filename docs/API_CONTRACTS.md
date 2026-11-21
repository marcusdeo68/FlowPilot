# API contracts — foundation increment

Legacy local demo base path: `/api/v1`. All responses are JSON. IDs are UUIDs and timestamps are UTC ISO 8601 strings. This API remains unauthenticated and synthetic-only. The separate workspace API is described below.

## Operations

| Method and path | Purpose | Expected results |
|---|---|---|
| `GET /healthz` | Process liveness | `200 {"status":"ok"}` |
| `GET /api/v1/focus?day=YYYY-MM-DD` | Local dashboard snapshot: 50 recent rows plus the whole-database nonterminal due count for that day | 200; invalid/missing day 422 |
| `GET /readyz` | Database readiness | `200` when the local DB is reachable; otherwise `503` |
| `POST /api/v1/commitments` | Create a manually entered candidate | `201`, initial state `detected` |
| `GET /api/v1/commitments?status=&limit=` | List latest records, optionally by state | `200`, maximum 100 items |
| `GET /api/v1/commitments/{id}` | Read one record | `200` or `404` |
| `POST /api/v1/commitments/{id}/transitions` | Apply an allowed state transition | `200`, `404`, or `409` for invalid/stale change |
| `GET /api/v1/commitments/{id}/events` | Read the lifecycle event history | `200` or `404` |

## Create body

```json
{
  "title": "Confirm the event room",
  "details": "Check availability for the recruiting event",
  "owner_name": "Jordan Lee",
  "due_date": "2026-11-20",
  "evidence_excerpt": "I will confirm the room by Friday."
}
```

Only `title` is required. Unknown properties are rejected. Text fields have length limits and are trimmed. Data entered in this local foundation is user-provided and may still be sensitive; use synthetic examples.

## Transition body

```json
{
  "target_status": "confirmed",
  "expected_version": 1,
  "reason": "Organizer reviewed the evidence"
}
```

Allowed transitions are documented in `docs/ROADMAP.md` and enforced by server-side domain rules. A stale `expected_version` or an illegal transition returns `409 Conflict`; clients should fetch the current record before retrying. This API does not represent an external action approval.

## Separate workspace API (increment 0007)

Factory: `flowpilot_api.workspace_api:create_workspace_app`. This factory mounts
no legacy `/api/v1` endpoints or dashboard. Configuration and accepted token profile
are in [implementation 0007](implementation/0007-verified-workspace-api.md).
The optional browser sign-in adapter appears below. A live identity provider
remains unconfigured. Increment 0008 adds API workspace onboarding and membership
administration using the same verified tokens.

All resource endpoints require a verified bearer access token or an enabled
browser session (0012), plus `flowpilot:read`;
writes additionally require `flowpilot:write`. Stored membership/role and object
visibility determine actual access. The path workspace UUID is a selector, not
authorization. Unknown JSON fields are rejected.

Base: `/api/v2/workspaces/{workspace_id}`.

| Method and suffix | Purpose |
| --- | --- |
| `GET /work?limit=50` | Authorized private/shared work, maximum 100 |
| `POST /work` | Create a typed item in its initial state; defaults private |
| `GET /work/{id}` | Authorized work record |
| `POST /work/{id}/transitions` | Explicit target and expected version |
| `POST /work/{id}/share` | Creator explicitly shares work at expected version |
| `POST /sources` | Store an immutable bounded synthetic/manual source |
| `GET /sources/{id}` | Read source as its owner; shared evidence is separate |
| `POST /work/{id}/evidence` | Source owner links evidence with explicit visibility/version |
| `GET /work/{id}/evidence` | Project only evidence authorized for this viewer |
| `GET /work/{id}/history` | Authorized append-only work audit history |

Example create body:

```json
{"item":{"kind":"task","title":"Review synthetic plan"},"visibility":"private"}
```

The task creator can replace task details with
`PATCH /api/v2/workspaces/{workspace_id}/work/{work_id}/task-details`. Send
`{"expected_version":1,"details":{"title":"Confirm venue","description":null,"due_date":"2026-12-04"}}`.
All three detail keys are required. Use null to clear description or due date.
The endpoint requires active write membership and the existing API write scopes.
It returns the updated stored work or 409 for a stale version. See
[increment 0018](implementation/0018-manual-task-editing.md).

A transition body is `{"target":"active","expected_version":1}`. Sharing uses
`{"expected_version":1}`. Linking evidence uses `source_id`, `visibility`
(`private`, `summary_shared`, or `excerpt_shared`), and `expected_version`.
Writes return the resulting record and incremented version. Source creation returns
its ID. Creates return 201; successful reads/changes return 200. Authentication
failure returns 401, denied capabilities 403, absent/inaccessible objects 404,
conflicting/stale/illegal changes 409, invalid input 422, and identity/readiness
dependency failure 503. Error responses do not return SQL values or token contents.

Public `/healthz` checks process liveness; `/readyz` checks the PostgreSQL revision.
Neither grants access to resources. These operations do not approve or execute any
email, calendar, or provider side effect.

## Workspace onboarding and administration (increment 0008)

| Method and path | Contract |
| --- | --- |
| `GET /api/v2/me` | Own internal user ID; 404 before onboarding |
| `GET /api/v2/workspaces?limit=50` | Caller's active workspaces only; empty for a new identity |
| `POST /api/v2/workspaces` | `{ "name": "Synthetic team" }`; atomically registers verified identity if needed, creates workspace/owner and audit; 201 |
| `GET /api/v2/workspaces/{id}/members?limit=50` | Owner-only active/inactive members with versions |
| `POST /api/v2/workspaces/{id}/members` | `{ "user_id": "UUID", "role": "member" }`; owner grants already registered same-issuer user membership; 201 |
| `PATCH /api/v2/workspaces/{id}/members/{user_id}` | Explicit `role`, strict boolean `active`, and positive integer `expected_version`; owner-only |
| `GET /api/v2/workspaces/{id}/membership-history?limit=50` | Owner-only attributed permission history |

Read/write scopes follow the rules above. The create-workspace caller cannot choose
an owner identity or self-assert a role in JSON. A role change, removal, or reactivation
requires the current membership version. Stale/duplicate/no-op changes and last-owner
removal/demotion return 409; unknown targets return 404 and denied administration
returns 403. Lists cap at 100; full pagination remains future work.

An inactive member is denied subsequent work/source requests even if their bearer
token has not expired. Their private source ownership is not transferred. An owner
must explicitly grant another active owner before leaving. This is manual membership
granting, not a delivered email invitation or an invitation acceptance workflow.
Workspace creation is not idempotent: do not retry automatically after an ambiguous
timeout. See [implementation 0008](implementation/0008-workspace-onboarding.md).

## Optional browser session contract (increment 0012)

Opt-in browser login (0016) adds GET/POST `/api/v2/login`, GET
`/api/v2/login/callback` and POST `/api/v2/login/complete`. Default-disabled;
explicit endpoints/client and browser origin are required. Callback GET presents
a form; exact-Origin completion POST consumes/exchanges/verifies before issuing
the existing session. No live provider is configured. See
[login contracts and compatibility](implementation/0016-browser-login.md).

Enabled only with an exact loopback `FLOWPILOT_BROWSER_ORIGIN`. The configured
origin must also be the API's origin. Existing bearer-only requests remain valid.

| Method and path | Contract |
| --- | --- |
| `POST /api/v2/session` | Verified read-scoped bearer, exact Origin, no session cookie; 201 with `expires_at` (Unix seconds), `csrf_token`, `can_write` and HttpOnly session cookie |
| `GET /api/v2/session` | Active cookie, safe same-origin read; same fields, no renewal |
| `DELETE /api/v2/session` | Exact Origin, active cookie's `X-CSRF-Token`; atomic revocation then cookie deletion, 204 |

Unsafe cookie requests require exact Origin plus CSRF. Foreign supplied Origin
and cross-origin Fetch Metadata are denied on reads too. Missing/invalid/expired
sessions return 401, origin/CSRF/scope failures 403, and session-storage outages
503. Bearer-plus-cookie or duplicate credentials return 401. Expired/revoked or
malformed cookies can be cleared by same-origin DELETE without CSRF or persisted
state mutation. Retrying logout is safe. Session exchange is not idempotent: an
ambiguous response may leave an unused row until expiry; no automatic retries.
Scopes/expiry come from verified claims and permissions remain live service checks.
The `can_write` field describes the session's API scope. A write also requires
the appropriate active workspace membership and object access.
See [0012](implementation/0012-browser-sessions.md) for limitations.

## Remaining cross-app contract (design only)

The next contract must distinguish records with different trust and authorization meanings:

- `source_items`: provider, provider item ID, owner connection, event time, source link, visibility, and minimal retained content.
- `work_items`: typed commitment, task, or event with workspace, owner, status, due/start/end times, and version.
- `evidence_links`: source item plus a bounded quote/span supporting a proposal or work item.
- `proposals`: proposed work/state changes with evidence references, confidence/abstention, reviewer, and review state.
- `action_proposals`: provider connection, operation, target, exact payload, payload version/hash, and expiry.
- `approvals`: authenticated approver and approved action version; changing the payload makes the approval stale.
- `executions`: idempotency key, attempt/result, provider response reference, and verification status.

Every endpoint must derive permissions from authenticated identity. A client-supplied
workspace selector is not proof of access. Typed work and manual source/evidence
services now exist; provider ownership, exact-payload action approvals,
executions, and the authenticated frontend remain future work.

## Private task review (workspace API)

Work browsing: `GET /api/v2/workspaces/{workspace_id}/work-page?limit=50&after=<UUID>`
returns `{items, next_after}` in descending creation-time/UUID order. Omit `after`
on the first request; null `next_after` ends traversal. Read scope and active stored
membership are required; private work remains creator-only. Inaccessible/unknown
pivots return 404, invalid limit/UUID 422. The existing `/work` list is preserved.
See [work pagination](implementation/0014-work-pagination.md) for live-traversal limits.

Due tasks: `GET /api/v2/workspaces/{workspace_id}/work-due?limit=20` returns
`{items, has_more}`. It includes visible tasks in open, active, or blocked state
with a due date. Earliest dates come first, with descending creation time and UUID
as tie breakers. The limit accepts 1–100 and `has_more` counts only eligible,
authorized tasks. Use `work-page` to browse all work. See
[increment 0019](implementation/0019-task-lifecycle-and-due-view.md).

Upcoming events: `GET /api/v2/workspaces/{workspace_id}/work-events?limit=5`
returns `{items, has_more}`. It requires read scope and active workspace
membership. The response contains authorized scheduled events that end after
the query starts and start before its 168-hour cutoff, including ongoing events.
The limit accepts 1–100. Sort is start time, then ID, ascending. See
[increment 0023](implementation/0023-today-upcoming-events.md).

### Manual events

`POST /api/v2/workspaces/{workspace_id}/work-events` creates a private event with
`title`, optional `description`, and `schedule`. The schedule contains
`starts_at`, `ends_at`, and `time_zone`. For example, pair `2030-06-14T23:30`
and `2030-06-15T00:30` with `America/New_York`. Local timestamps use ISO date and
time without an offset. Seconds and up to six fractional digits are optional.
A skipped or repeated wall time, unknown zone, or reversed interval returns 422.

`GET /api/v2/workspaces/{workspace_id}/work/{work_id}/event-details` returns the
event's version and its server-resolved local times for the editor. The same
path accepts `PATCH` to replace `details` (`title` and nullable `description`)
and accepts a `schedule`. Omit the schedule or send null to preserve all times.
When the zone stays the same, omit or null an individual time to preserve its
exact instant. When the zone changes, supply both local times.
Send `expected_version`. This action is creator-only. A stale version or canceled
event returns 409. The existing versioned `/transitions` endpoint accepts
`target: "canceled"` for a scheduled event. Writes require the verified write
scope, active write membership, and CSRF for cookies.

To browse events, pass `kind=event` to `GET /api/v2/workspaces/{workspace_id}/work-page`.
This filter uses the same creation order and pagination contract. An `after` ID
for a different work kind returns 404. See
[increment 0025](implementation/0025-manual-workspace-events.md).

### Browser workspace access

**Workspace access** uses the existing `me`, `workspaces`, `members`, and
`membership-history` routes. On safe cookie requests a supplied `X-CSRF-Token`
must match the cookie session. A mismatch returns 401. Bearer clients authenticate
with verified access tokens. See [0028](implementation/0028-workspace-access.md).

### Workspace invitations

`POST /api/v2/me` returns the idempotently registered profile for the verified
identity and requires write scope. Workspace owners use
`GET|POST /api/v2/workspaces/{workspace_id}/invitations`. To offer a role, send
`user_id` and `role`. To revoke a pending offer, post `expected_version` to
`/api/v2/workspaces/{workspace_id}/invitations/{invitation_id}/revoke`.

`GET /api/v2/invitations?limit=20` lists the current registered user's actionable
invitations. `POST /api/v2/invitations/{invitation_id}/decision` takes `decision`
(`accept` or `decline`) and `expected_version`. Acceptance creates the offered
membership. `GET /api/v2/workspaces/{workspace_id}` verifies active membership and
returns current workspace details for an accepted workspace outside the bounded list.
Lists support limits 1 through 100. An unknown or out-of-scope
invitation returns 404. Expired, stale and conflicting writes return 409. Cookie
writes also require the same-origin CSRF token. See
[0029](implementation/0029-workspace-invitations.md).

### In-app reminder candidates

`GET /api/v2/workspaces/{workspace_id}/reminders?local_date=2030-09-30` returns
`{tasks, events, has_more}`. `local_date` is the viewer's local calendar date in
YYYY-MM-DD format. Unfinished tasks must match that date. Scheduled events must
start after the database statement time and within the selected event window.
The optional `category` is `tasks`, `events`, or `both` (default).
The optional integer `event_lead_minutes` ranges from 5 to 60 and defaults to 15.
An excluded category returns an empty list and does not contribute to `has_more`.
Each list returns up to five authorized items with their ID, title, and relevant
date or start instant. The server filters by active membership and visibility
before applying each limit. Cookie clients send the current session's
`X-CSRF-Token` as a tab-to-session binding. A missing or stale binding returns
401. Bearer clients use the usual read scope. See
[increment 0026](implementation/0026-in-app-reminders.md) and
[increment 0027](implementation/0027-reminder-settings.md).

### Private notes

Paths below are relative to `/api/v2/workspaces/{workspace_id}/notes`.
Notes belong to the verified caller inside the selected workspace. Cookie
writes require the usual CSRF token and all writes require write scope plus
an active owner or member role. Reads require read scope and active membership.

| Method and path | Contract |
| --- | --- |
| `GET /` | `archived=false`, `limit=25` (1–100), and optional UUID `after`. Returns `{items, next_after}` in descending creation time and ID. |
| `POST /` | `{"body":"Plain text"}`. Returns 201 with note version 1. |
| `PATCH /{id}` | `{"body":"New text","expected_version":1}`. Edits an active note. |
| `POST /{id}/state` | `{"archived":true,"expected_version":2}`. Use false to restore. |

Notes return `id`, `body`, `archived`, `version`, `created_at`, and `updated_at`.
The body supports 1–2,000 characters with meaningful text. A foreign or missing
ID or cursor returns 404. A stale version or an edit to an archived note returns
409. Repeating a current value leaves the version and audit history intact.
Validation errors use `{"detail":"Invalid note request"}` and omit the submitted
body. See [increment 0024](implementation/0024-private-sticky-notes.md).

See [the request sequence](implementation/0009-private-task-review.md#try-the-request-sequence)
for source-to-proposal creation, listing, correction, and review contracts.

The [source inbox](implementation/0010-private-source-inbox.md) lists the caller's
manual sources with review status at `GET /api/v2/workspaces/{workspace_id}/sources`.
Continue with the returned `next_after` UUID as the `after` query parameter.
