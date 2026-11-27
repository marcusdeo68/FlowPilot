from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from psycopg.errors import LockNotAvailable
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.postgres


def test_schedule_pages_visible_events_in_start_order(workspace_client, setup):
    client, workspace, other, users, sign = workspace_client
    service, *_ = setup
    base = f"/api/v2/workspaces/{workspace}"
    schedule = base + "/work-schedule"
    now = datetime.now(UTC)
    writer = {"Authorization": "Bearer " + sign("member")}
    reader = {"Authorization": "Bearer " + sign("observer", overrides={"scope": "flowpilot:read"})}
    foreign = {"Authorization": "Bearer " + sign("outsider")}

    def create(title, days, *, duration=1, visibility="workspace", path=base, headers=writer):
        start = now + timedelta(days=days)
        response = client.post(
            path + "/work",
            headers=headers,
            json={
                "visibility": visibility,
                "item": {
                    "kind": "event",
                    "title": title,
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(days=duration)).isoformat(),
                    "time_zone": "UTC",
                },
            },
        )
        assert response.status_code == 201
        return response.json()

    assert client.get(schedule).status_code == 401
    assert client.get(schedule, headers=foreign).status_code == 403
    assert client.get(schedule, headers=reader).json() == {"items": [], "next_after": None}
    assert (
        client.get(
            schedule,
            headers={
                "Authorization": "Bearer "
                + sign("observer", overrides={"scope": "flowpilot:write"})
            },
        ).status_code
        == 403
    )

    later = create("Beyond Today", 10)
    hidden = create("Private event", 2, visibility="private")
    moved = create("Reschedule this", 3)
    first = create("Same start A", 1)
    second = create("Same start B", 1)
    ongoing = create("Ongoing", -1, duration=2)
    ended = create("Ended", -3)
    canceled = create("Canceled", 4)
    outsider = create("Foreign", 1, path=f"/api/v2/workspaces/{other}", headers=foreign)
    task = client.post(
        base + "/work",
        headers=writer,
        json={"visibility": "workspace", "item": {"kind": "task", "title": "Not an event"}},
    )
    assert task.status_code == 201
    assert (
        client.post(
            base + f"/work/{canceled['id']}/transitions",
            headers=writer,
            json={"expected_version": 1, "target": "canceled"},
        ).status_code
        == 200
    )

    def page(**params):
        response = client.get(schedule, headers=reader, params=params)
        assert response.status_code == 200
        return response.json()

    ordered = [ongoing, *sorted((first, second), key=lambda event: event["id"]), moved, later]
    for index, item in enumerate(ordered):
        params = {"limit": 1}
        if index:
            params.update(after=ordered[index - 1]["id"], after_version=1)
        assert page(**params) == {
            "items": [item],
            "next_after": item["id"] if index < len(ordered) - 1 else None,
        }
    assert page(after=later["id"], after_version=1) == {"items": [], "next_after": None}
    # A still-scheduled pivot can end between requests. Its position stays usable.
    assert page(after=ended["id"], after_version=1)["items"] == ordered
    own = client.get(schedule, headers=writer).json()["items"]
    assert own == [*ordered[:3], hidden, *ordered[3:]]
    assert later not in client.get(base + "/work-events", headers=reader).json()["items"]

    def try_to_lock_pivot(_connection, _cursor, statement, *_args):
        if "AND (starts_at, id) >" not in statement:
            return
        competing_locks.append(moved["id"])
        with (
            service.engine.connect() as writer_connection,
            pytest.raises(DBAPIError) as blocked,
        ):
            writer_connection.execute(
                text("SELECT id FROM work_items WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": moved["id"]},
            )
        assert isinstance(blocked.value.orig, LockNotAvailable)

    competing_locks = []
    event.listen(service.engine, "before_cursor_execute", try_to_lock_pivot)
    try:
        assert page(after=moved["id"], after_version=1)["items"] == [later]
    finally:
        event.remove(service.engine, "before_cursor_execute", try_to_lock_pivot)
    assert competing_locks == [moved["id"]]

    for params in (
        {"limit": 0},
        {"limit": 101},
        {"after": later["id"]},
        {"after_version": 1},
        {"after": later["id"], "after_version": 0},
        {"after": "invalid", "after_version": 1},
    ):
        assert client.get(schedule, params=params, headers=reader).status_code == 422

    result = client.patch(
        base + f"/work/{moved['id']}/event-details",
        headers=writer,
        json={
            "details": {"title": "Rescheduled", "description": None},
            "expected_version": 1,
            "schedule": {
                "starts_at": (now + timedelta(days=12)).replace(tzinfo=None).isoformat(),
                "ends_at": (now + timedelta(days=13)).replace(tzinfo=None).isoformat(),
                "time_zone": "UTC",
            },
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2
    for pivot in (hidden["id"], outsider["id"], task.json()["id"], moved["id"], str(uuid4())):
        response = client.get(schedule, headers=reader, params={"after": pivot, "after_version": 1})
        assert response.status_code == 404
        assert response.json() == {"detail": "Work item not found"}
    assert (
        client.get(
            schedule, headers=reader, params={"after": canceled["id"], "after_version": 2}
        ).status_code
        == 404
    )
    assert page()["items"] == [*ordered[:3], later, result.json()]
    assert (
        client.patch(
            base + f"/members/{users['observer']}",
            headers={"Authorization": "Bearer " + sign("owner")},
            json={"expected_version": 1, "role": "observer", "active": False},
        ).status_code
        == 200
    )
    assert client.get(schedule, headers=reader).status_code == 403
