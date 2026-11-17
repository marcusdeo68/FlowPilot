from uuid import uuid4

import pytest
from flowpilot_api.access import AccessDenied, Visibility
from flowpilot_api.work import Task
from flowpilot_api.work_service import Principal, WorkNotFound
from sqlalchemy import text

pytestmark = pytest.mark.postgres


def test_work_pages_traverse_beyond_the_old_cap_without_mutations(setup):
    service, ws, _, _ = setup
    owner = Principal("test", "owner")
    ids = {
        service.create_work(owner, ws, Task(title=str(i)), visibility=Visibility.WORKSPACE).id
        for i in range(103)
    }

    def audit_count():
        with service.engine.connect() as c:
            return c.execute(text("SELECT count(*) FROM audit_events")).scalar_one()

    before = audit_count()
    seen, cursor = [], None
    while True:
        page = service.list_work_page(Principal("test", "observer"), ws, limit=100, after=cursor)
        seen.extend(i.id for i in page.items)
        if page.next_after is None:
            break
        cursor = page.next_after
        assert len(seen) <= 103
    assert len(seen) == len(set(seen)) == 103
    assert set(seen) == ids
    assert audit_count() == before


def test_work_pages_ties_updates_and_new_arrivals(setup):
    service, ws, _, _ = setup
    member = Principal("test", "member")
    ids = [service.create_work(member, ws, Task(title=str(i))).id for i in range(5)]
    with service.engine.begin() as c:
        c.execute(
            text("UPDATE work_items SET created_at='2026-01-01Z' WHERE workspace_id=:ws"),
            {"ws": ws},
        )
    expected = sorted(ids, reverse=True)
    first = service.list_work_page(member, ws, limit=2)
    assert [i.id for i in first.items] == expected[:2]
    assert first.next_after == expected[1]
    service.transition(member, ws, expected[-1], target="active", expected_version=1)
    newest = service.create_work(member, ws, Task(title="New arrival"))
    second = service.list_work_page(member, ws, limit=2, after=first.next_after)
    last = service.list_work_page(member, ws, limit=2, after=second.next_after)
    assert [i.id for i in second.items + last.items] == expected[2:]
    assert last.next_after is None
    assert service.list_work_page(member, ws, limit=1).items[0].id == newest.id
    assert service.list_work_page(member, ws, after=expected[-1]).items == []


def test_work_pages_privacy_and_membership(setup):
    service, ws, other, users = setup
    member, owner, outsider = (Principal("test", n) for n in ("member", "owner", "outsider"))
    private = service.create_work(member, ws, Task(title="Private"))
    shared = service.create_work(member, ws, Task(title="Shared"), visibility=Visibility.WORKSPACE)
    foreign = service.create_work(outsider, other, Task(title="Foreign"))
    assert [i.id for i in service.list_work_page(owner, ws).items] == [shared.id]
    for cursor in (private.id, foreign.id, uuid4()):
        with pytest.raises(WorkNotFound):
            service.list_work_page(owner, ws, after=cursor)
    for limit in (0, 101):
        with pytest.raises(ValueError):
            service.list_work_page(member, ws, limit=limit)
    with service.engine.begin() as c:
        c.execute(
            text("UPDATE memberships SET active=false WHERE user_id=:id"), {"id": users["member"]}
        )
    with pytest.raises(AccessDenied):
        service.list_work_page(member, ws, after=shared.id)


def test_work_page_signed_http_contract(workspace_client):
    client, ws, _, _, sign = workspace_client
    base = f"/api/v2/workspaces/{ws}"
    path = base + "/work-page"
    write = {"Authorization": "Bearer " + sign("member")}
    read = {"Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:read"})}
    assert client.get(path).status_code == 401
    assert (
        client.get(
            path,
            headers={
                "Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:write"})
            },
        ).status_code
        == 403
    )
    assert (
        client.get(path, headers={"Authorization": "Bearer " + sign("outsider")}).status_code == 403
    )
    assert client.get(path, headers=read).json() == {"items": [], "next_after": None}
    for query in ("?limit=0", "?limit=101", "?after=invalid"):
        assert client.get(path + query, headers=read).status_code == 422
    for title in ("First", "Second"):
        response = client.post(
            base + "/work", headers=write, json={"item": {"kind": "task", "title": title}}
        )
        assert response.status_code == 201
    first = client.get(path + "?limit=1", headers=read).json()
    assert len(first["items"]) == 1 and first["next_after"] == first["items"][0]["id"]
    last = client.get(path + "?limit=1&after=" + first["next_after"], headers=read).json()
    assert len(last["items"]) == 1 and last["next_after"] is None
    assert first["items"][0]["id"] != last["items"][0]["id"]
    assert (
        client.get(
            path + "?after=" + first["next_after"],
            headers={"Authorization": "Bearer " + sign("owner")},
        ).status_code
        == 404
    )
    assert isinstance(client.get(base + "/work", headers=read).json(), list)
