import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from flowpilot_api.repository import VersionConflict
from flowpilot_api.work import Event, EventScheduleChange, WorkDetails
from flowpilot_api.work_service import Principal
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.postgres


def schedule(**changes):
    return {
        "time_zone": "America/New_York",
        "starts_at": "2030-06-14T23:30:00.123456",
        "ends_at": "2030-06-15T00:30",
        **changes,
    }


def test_manual_event_versions_audit_and_event_only_browsing(workspace_client):
    client, workspace, _, users, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}"
    member = {"Authorization": "Bearer " + sign("member")}
    owner = {"Authorization": "Bearer " + sign("owner")}
    task = client.post(
        base + "/work", headers=member, json={"item": {"kind": "task", "title": "Other work"}}
    ).json()
    response = client.post(
        base + "/work-events",
        headers=member,
        json={"title": "  Overnight workshop  ", "schedule": schedule()},
    )
    assert response.status_code == 201
    item = response.json()
    assert item["visibility"] == "private" and item["version"] == 1
    assert item["creator_id"] == str(users["member"])
    assert item["data"] == {
        "kind": "event",
        "status": "scheduled",
        "title": "Overnight workshop",
        "description": None,
        "time_zone": "America/New_York",
        "starts_at": "2030-06-15T03:30:00.123456Z",
        "ends_at": "2030-06-15T04:30:00Z",
    }
    shared = client.post(
        base + "/work",
        headers=member,
        json={"item": {**item["data"], "title": "Shared workshop"}, "visibility": "workspace"},
    ).json()
    browse = base + "/work-page?kind=event&limit=1"
    first = client.get(browse, headers=member).json()
    assert first == {"items": [shared], "next_after": shared["id"]}
    assert client.get(browse + "&after=" + shared["id"], headers=member).json() == {
        "items": [item],
        "next_after": None,
    }
    assert client.get(browse, headers=owner).json() == {"items": [shared], "next_after": None}
    assert client.get(browse + "&after=" + item["id"], headers=owner).status_code == 404
    assert client.get(browse + "&after=" + task["id"], headers=member).status_code == 404

    work_path = base + "/work/" + item["id"]
    edit = work_path + "/event-details"
    assert client.get(edit, headers=member).json() == {
        "version": 1,
        "starts_at": "2030-06-14T23:30:00.123456",
        "ends_at": "2030-06-15T00:30:00",
        "time_zone": "America/New_York",
    }
    assert client.get(edit, headers=owner).status_code == 404
    details = {"title": "Rehearsal", "description": "Bring the draft"}
    result = client.patch(edit, headers=member, json={"details": details, "expected_version": 1})
    assert result.status_code == 200
    expected_data = {**item["data"], **details}
    assert result.json()["data"] == expected_data
    command = {"details": details, "expected_version": 2}
    assert client.patch(edit, headers=member, json=command).json() == result.json()
    for change, message in (
        ({"time_zone": "UTC", "ends_at": "2030-06-15T05:00"}, "Provide both times"),
        ({"time_zone": "America/New_York", "ends_at": "2030-06-14T23:00"}, "end must follow start"),
    ):
        rejected = client.patch(edit, headers=member, json={**command, "schedule": change})
        assert rejected.status_code == 422 and message in rejected.text
    assert client.get(work_path, headers=member).json() == result.json()
    moved = client.patch(
        edit,
        headers=member,
        json={**command, "schedule": schedule(time_zone="UTC")},
    ).json()
    assert moved["version"] == 3
    assert moved["data"]["starts_at"] == "2030-06-14T23:30:00.123456Z"
    assert client.patch(edit, headers=member, json=command).status_code == 409
    canceled = client.post(
        work_path + "/transitions",
        headers=member,
        json={"expected_version": 3, "target": "canceled"},
    ).json()
    assert canceled["data"]["status"] == "canceled" and canceled["version"] == 4
    assert (
        client.patch(edit, headers=member, json={**command, "expected_version": 4}).status_code
        == 409
    )
    audit = client.get(work_path + "/history", headers=member).json()
    assert [(event["operation"], event["version"]) for event in audit] == [
        ("created", 1),
        ("details_changed", 2),
        ("details_changed", 3),
        ("status_changed", 4),
    ]
    assert all(event["actor_id"] == str(users["member"]) for event in audit)
    assert all("title" not in event and "starts_at" not in event for event in audit)


def test_manual_event_auth_and_wall_time_validation(workspace_client):
    client, workspace, other, _, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}"
    path = base + "/work-events"
    member = {"Authorization": "Bearer " + sign("member")}
    owner = {"Authorization": "Bearer " + sign("owner")}
    observer = {"Authorization": "Bearer " + sign("observer")}
    outsider = {"Authorization": "Bearer " + sign("outsider")}
    read_only = {"Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:read"})}
    body = {"title": "Draft", "schedule": schedule()}
    schema = client.get("/openapi.json").json()["components"]["schemas"]["LocalEventSchedule"]
    for name in ("starts_at", "ends_at"):
        field = schema["properties"][name]
        assert field["type"] == "string" and "format" not in field
        assert re.fullmatch(field["pattern"], body["schedule"][name])
        assert not re.fullmatch(field["pattern"], body["schedule"][name] + "Z")
    for actor, status in (({}, 401), (observer, 403), (outsider, 403), (read_only, 403)):
        assert client.post(path, headers=actor, json=body).status_code == status
    for invalid, error in (
        (schedule(starts_at="2030-03-10T02:30"), "does not exist"),
        (schedule(starts_at="2030-11-03T01:30"), "occurs twice"),
        (schedule(ends_at="2030-06-14T23:00"), "end must follow start"),
        (schedule(ends_at="2030-06-15T00:30Z"), "without an offset"),
        (schedule(time_zone="Mars/Test"), "valid IANA time zone"),
        (schedule(starts_at="0001-01-01T00:00", time_zone="Asia/Tokyo"), "supported date range"),
    ):
        rejected = client.post(path, headers=member, json={**body, "schedule": invalid})
        assert rejected.status_code == 422 and error in rejected.text
    assert (
        client.post(path, headers=member, json={**body, "visibility": "workspace"}).status_code
        == 422
    )
    assert client.get(base + "/work", headers=member).json() == []
    item = client.post(path, headers=member, json=body).json()
    work = base + "/work/" + item["id"]
    edit = work + "/event-details"
    update = {"expected_version": 1, "details": {"title": "Edited", "description": None}}
    for actor, status in (
        ({}, 401),
        (observer, 403),
        (outsider, 403),
        (read_only, 403),
        (owner, 404),
    ):
        assert client.patch(edit, headers=actor, json=update).status_code == status
    foreign = f"/api/v2/workspaces/{other}/work/{item['id']}/event-details"
    assert client.patch(foreign, headers=outsider, json=update).status_code == 404
    shared = client.post(work + "/share", headers=member, json={"expected_version": 1})
    assert shared.status_code == 200
    assert (
        client.patch(edit, headers=owner, json={**update, "expected_version": 2}).status_code == 403
    )
    # Keep the existing shared-work cancellation policy.
    canceled = client.post(
        work + "/transitions", headers=owner, json={"expected_version": 2, "target": "canceled"}
    )
    assert canceled.status_code == 200


def test_event_edit_preserves_interval_across_postgres_clock_fold(setup):
    service, workspace, _, _ = setup
    actor = Principal("test", "member")
    with service.engine.begin() as connection:
        connection.execute(text("SET TIME ZONE 'America/New_York'"))
    start = datetime(2030, 11, 3, 5, 45, tzinfo=UTC)
    end = datetime(2030, 11, 3, 6, 15, tzinfo=UTC)
    item = service.create_work(
        actor,
        workspace,
        Event(title="Repeated hour", starts_at=start, ends_at=end, time_zone="America/New_York"),
    )
    assert item.data.starts_at.hour == item.data.ends_at.hour == 1
    assert item.data.starts_at.fold == 0 and item.data.ends_at.fold == 1
    updated = service.edit_event(
        actor,
        workspace,
        item.id,
        expected_version=1,
        details=WorkDetails(title="Renamed", description=None),
        schedule=EventScheduleChange(time_zone="America/New_York"),
    )
    assert updated.version == 2
    assert updated.data.starts_at.astimezone(UTC) == start
    assert updated.data.ends_at.astimezone(UTC) == end
    assert (
        service.edit_event(
            actor,
            workspace,
            item.id,
            expected_version=2,
            details=WorkDetails(title="Renamed", description=None),
            schedule=EventScheduleChange(time_zone="America/New_York"),
        )
        == updated
    )


def test_event_edit_serializes_with_cancellation_and_rolls_back_on_audit_failure(setup):
    service, workspace, _, _ = setup
    actor = Principal("test", "member")
    event = Event(
        title="Original",
        starts_at=datetime(2030, 6, 14, 23, tzinfo=UTC),
        ends_at=datetime(2030, 6, 15, tzinfo=UTC),
        time_zone="UTC",
    )
    item = service.create_work(actor, workspace, event)
    timing = EventScheduleChange(**schedule())

    def edit():
        return service.edit_event(
            actor,
            workspace,
            item.id,
            expected_version=1,
            details=WorkDetails(title="Rescheduled", description=None),
            schedule=timing,
        )

    with service.engine.begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION fail_event_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected event audit failure'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER fail_event BEFORE INSERT ON audit_events
            FOR EACH ROW WHEN (NEW.operation = 'details_changed') EXECUTE FUNCTION fail_event_audit()""")
        )
    with pytest.raises(DBAPIError, match="injected event audit failure"):
        edit()
    assert service.get_work(actor, workspace, item.id) == item
    with service.engine.begin() as connection:
        connection.execute(text("DROP TRIGGER fail_event ON audit_events"))

    barrier = Barrier(2)

    def race(command):
        barrier.wait(timeout=10)
        try:
            return command()
        except VersionConflict:
            return None

    def cancel():
        return service.transition(actor, workspace, item.id, target="canceled", expected_version=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        update, cancellation = pool.submit(race, edit), pool.submit(race, cancel)
        results = [update.result(timeout=20), cancellation.result(timeout=20)]
    changed = [saved for saved in results if saved is not None]
    assert len(changed) == 1 and changed[0].version == 2
    assert service.get_work(actor, workspace, item.id) == changed[0]
    assert [entry["version"] for entry in service.history(actor, workspace, item.id)] == [1, 2]
