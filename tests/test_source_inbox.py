from uuid import UUID, uuid4

import pytest
from flowpilot_api.inbox import InboxService
from flowpilot_api.work_service import ManualSource, Principal, SourceNotFound
from sqlalchemy import text

pytestmark = pytest.mark.postgres


def source(work, principal, ws, label):
    return work.create_source(
        principal,
        ws,
        ManualSource(
            reference="manual:" + label,
            summary=label,
            excerpt="Synthetic detail only",
        ),
    )


def test_inbox_pages_ties_and_new_arrivals_without_skipping_older_sources(setup):
    work, ws, _, _ = setup
    inbox, member = InboxService(work.engine), Principal("test", "member")
    ids = [source(work, member, ws, str(i)) for i in range(4)]
    with work.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE source_items SET created_at = '2026-01-01T00:00:00Z' WHERE workspace_id=:ws"
            ),
            {"ws": ws},
        )
    expected = sorted(ids, reverse=True)
    first = inbox.page(member, ws, limit=2, after=None)
    assert [item.id for item in first.items] == expected[:2]
    assert first.next_after == expected[1]
    newest = source(work, member, ws, "New arrival")
    second = inbox.page(member, ws, limit=2, after=first.next_after)
    assert [item.id for item in second.items] == expected[2:]
    assert second.next_after is None
    assert inbox.page(member, ws, limit=1, after=None).items[0].id == newest
    assert inbox.page(member, ws, limit=1, after=expected[-1]).items == []


def test_cursor_does_not_disclose_foreign_sources(setup):
    work, ws, other, _ = setup
    member, owner, outsider = (Principal("test", name) for name in ("member", "owner", "outsider"))
    inbox = InboxService(work.engine)
    own = source(work, member, ws, "Private member source")
    foreign = source(work, outsider, other, "Other workspace")
    assert inbox.page(owner, ws, limit=10, after=None).items == []
    for cursor in (own, foreign, uuid4()):
        with pytest.raises(SourceNotFound):
            inbox.page(owner, ws, limit=10, after=cursor)


def test_signed_source_inbox_projection_and_read_only_behavior(workspace_client):
    client, ws, _, _, sign = workspace_client
    base = f"/api/v2/workspaces/{ws}"
    path = base + "/sources"
    headers = {"Authorization": "Bearer " + sign("member")}
    readonly = {"Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:read"})}
    assert client.get(path).status_code == 401
    assert (
        client.get(path, headers={"Authorization": "Bearer " + sign("outsider")}).status_code == 403
    )
    assert client.get(path, headers=readonly).json() == {"items": [], "next_after": None}
    for query in ("?limit=0", "?limit=101", "?after=invalid"):
        assert client.get(path + query, headers=readonly).status_code == 422
    sid = client.post(
        path,
        headers=headers,
        json={
            "reference": "synthetic:private",
            "summary": "Set review date",
            "excerpt": "For owner only",
        },
    ).json()["id"]
    (item,) = client.get(path, headers=readonly).json()["items"]
    assert set(item) == {"id", "summary", "created_at", "review"}
    assert UUID(item["id"]) == UUID(sid) and item["review"] is None
    pid = client.put(f"{path}/{sid}/task-proposal", headers=headers).json()["id"]
    assert client.get(path, headers=readonly).json()["items"][0]["review"] == {
        "id": pid,
        "state": "pending_review",
    }
    accepted = client.post(
        f"{base}/proposals/{pid}/review",
        headers=headers,
        json={"expected_version": 1, "decision": "accept"},
    ).json()
    assert accepted["work_id"] is not None
    assert client.get(path, headers=readonly).json()["items"][0]["review"] == {
        "id": pid,
        "state": "accepted",
    }
    other = {"Authorization": "Bearer " + sign("owner")}
    assert client.get(path, headers=other).json()["items"] == []
    assert client.get(path + "?after=" + sid, headers=other).status_code == 404
