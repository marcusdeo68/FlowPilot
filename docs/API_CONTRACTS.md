# API contracts — foundation increment

Legacy local demo base path: `/api/v1`. All responses are JSON. IDs are UUIDs and timestamps are UTC ISO 8601 strings. This API remains unauthenticated and synthetic-only. The separate workspace API is described below.

## Operations

| Method and path | Purpose | Expected results |
|---|---|---|
| `GET /healthz` | Process liveness | `200 {"status":"ok"}` |
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
It has no live sign-in/provider/provisioning flow yet.

All resource endpoints require a verified bearer access token and `flowpilot:read`;
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
services now exist; provider ownership, proposals, exact-payload action approvals,
executions, and the authenticated frontend remain future work.
