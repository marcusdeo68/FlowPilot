from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

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


def test_due_tasks_order_scope_and_limit(workspace_client):
    client, ws, other, _, sign = workspace_client
    base = f"/api/v2/workspaces/{ws}"
    due_path = base + "/work-due"

    def authorization(name, **overrides):
        return {"Authorization": "Bearer " + sign(name, overrides=overrides)}

    def create(title, *, due=None, visibility="workspace", actor="member", path=base):
        response = client.post(
            path + "/work",
            headers=authorization(actor),
            json={
                "visibility": visibility,
                "item": {"kind": "task", "title": title, "due_date": due},
            },
        )
        assert response.status_code == 201
        return response.json()["id"]

    def transition(item, target, version):
        response = client.post(
            base + f"/work/{item}/transitions",
            headers=authorization("owner"),
            json={"target": target, "expected_version": version},
        )
        assert response.status_code == 200
        assert response.json()["version"] == version + 1

    create("Private earlier", due="2025-01-01", visibility="private")
    create(
        "Foreign earlier", due="2025-01-02", actor="outsider", path=f"/api/v2/workspaces/{other}"
    )
    create("Undated")
    canceled = create("Canceled earlier", due="2025-01-03")
    transition(canceled, "canceled", 1)
    completed = create("Completed earlier", due="2025-01-04")
    transition(completed, "active", 1)
    transition(completed, "completed", 2)
    commitment = client.post(
        base + "/work",
        headers=authorization("member"),
        json={
            "visibility": "workspace",
            "item": {"kind": "commitment", "title": "Promise", "due_date": "2025-01-05"},
        },
    )
    assert commitment.status_code == 201
    older = create("Older tied", due="2025-01-06")
    newer = create("Newer tied", due="2025-01-06")
    transition(newer, "active", 1)
    transition(newer, "blocked", 2)
    later = create("Later active", due="2025-01-07")
    transition(later, "active", 1)

    assert client.get(due_path).status_code == 401
    assert client.get(due_path, headers=authorization("outsider")).status_code == 403
    observer = authorization("observer", scope="flowpilot:read")
    for limit in (0, 101, "invalid"):
        assert client.get(due_path, params={"limit": limit}, headers=observer).status_code == 422
    focus = client.get(due_path, params={"limit": 2}, headers=observer)
    assert focus.status_code == 200
    assert [item["id"] for item in focus.json()["items"]] == [newer, older]
    assert focus.json()["has_more"] is True
    entire = client.get(due_path, headers=observer).json()
    assert [item["id"] for item in entire["items"]] == [newer, older, later]
    assert entire["has_more"] is False
    own_view = client.get(due_path, headers=authorization("member")).json()["items"]
    assert [item["data"]["title"] for item in own_view] == [
        "Private earlier",
        "Newer tied",
        "Older tied",
        "Later active",
    ]


def test_upcoming_events_filter_order_scope_and_limit(workspace_client):
    client, workspace, other, _, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}"
    path = base + "/work-events"
    now = datetime.now(UTC)

    def authorization(name, **overrides):
        return {"Authorization": "Bearer " + sign(name, overrides=overrides)}

    def create(
        title,
        start_hours,
        end_hours,
        *,
        visibility="workspace",
        user="member",
        target=base,
        zone="UTC",
    ):
        start = (now + timedelta(hours=start_hours)).astimezone(ZoneInfo(zone))
        end = (now + timedelta(hours=end_hours)).astimezone(ZoneInfo(zone))
        response = client.post(
            target + "/work",
            headers=authorization(user),
            json={
                "visibility": visibility,
                "item": {
                    "kind": "event",
                    "title": title,
                    "starts_at": start.isoformat(),
                    "ends_at": end.isoformat(),
                    "time_zone": zone,
                },
            },
        )
        assert response.status_code == 201
        return response.json()["id"]

    observer = authorization("observer", scope="flowpilot:read")
    assert client.get(path).status_code == 401
    assert client.get(path, headers=authorization("outsider")).status_code == 403
    assert (
        client.get(path, headers=authorization("observer", scope="flowpilot:write")).status_code
        == 403
    )
    for limit in (0, 101, "invalid"):
        assert client.get(path, params={"limit": limit}, headers=observer).status_code == 422
    assert client.get(path, headers=observer).json() == {"items": [], "has_more": False}

    create("Foreign", -3, 2, target=f"/api/v2/workspaces/{other}", user="outsider")
    private = create("Private", -2, 2, visibility="private")
    create("Ended", -3, -1)
    create("Beyond window", 169, 170)
    canceled = create("Canceled", -2, 1)
    response = client.post(
        base + f"/work/{canceled}/transitions",
        headers=authorization("owner"),
        json={"target": "canceled", "expected_version": 1},
    )
    assert response.status_code == 200
    task = client.post(
        base + "/work",
        headers=authorization("member"),
        json={"visibility": "workspace", "item": {"kind": "task", "title": "Not an event"}},
    )
    assert task.status_code == 201
    later = create("Later", 12, 13, zone="America/New_York")
    ongoing = create("Ongoing", -1, 1)
    first = create("First tied event", 3, 4)
    second = create("Same instant in a different zone", 3, 5, zone="America/Los_Angeles")

    capped = client.get(path, params={"limit": 1}, headers=observer).json()
    assert [item["id"] for item in capped["items"]] == [ongoing]
    assert capped["has_more"] is True
    visible = client.get(path, headers=observer).json()
    assert [item["id"] for item in visible["items"]] == [ongoing, *sorted((first, second)), later]
    assert visible["items"][-1]["data"]["time_zone"] == "America/New_York"
    assert visible["has_more"] is False
    own = client.get(path, headers=authorization("member")).json()
    assert [item["id"] for item in own["items"]] == [
        private,
        ongoing,
        *sorted((first, second)),
        later,
    ]
