# API contracts — foundation increment

Base path: `/api/v1`. All responses are JSON. IDs are UUIDs and timestamps are UTC ISO 8601 strings.

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

## Planned cross-app contract (design only)

The next contract must distinguish records with different trust and authorization meanings:

- `source_items`: provider, provider item ID, owner connection, event time, source link, visibility, and minimal retained content.
- `work_items`: typed commitment, task, or event with workspace, owner, status, due/start/end times, and version.
- `evidence_links`: source item plus a bounded quote/span supporting a proposal or work item.
- `proposals`: proposed work/state changes with evidence references, confidence/abstention, reviewer, and review state.
- `action_proposals`: provider connection, operation, target, exact payload, payload version/hash, and expiry.
- `approvals`: authenticated approver and approved action version; changing the payload makes the approval stale.
- `executions`: idempotency key, attempt/result, provider response reference, and verification status.

Every endpoint must derive its workspace and permissions from the authenticated identity. A client-supplied `workspace_id` is not proof of access. This contract is a design target; these resources and controls are not implemented yet.
