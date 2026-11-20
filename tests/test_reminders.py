from datetime import UTC, date, datetime, timedelta

import pytest
from flowpilot_api.access import Visibility
from flowpilot_api.work import Event, Task
from flowpilot_api.work_service import Principal
from sqlalchemy import text

pytestmark = pytest.mark.postgres


def test_reminder_candidates_filter_before_independent_limits(setup):
    service, workspace, other, _ = setup
    owner = Principal("test", "owner")
    member = Principal("test", "member")
    outsider = Principal("test", "outsider")
    today = date(2030, 9, 30)
    now = datetime.now(UTC)

    def create_task(actor, title, due, target_workspace=workspace, *, shared=False):
        return service.create_work(
            actor,
            target_workspace,
            Task(title=title, due_date=due),
            visibility=Visibility.WORKSPACE if shared else Visibility.PRIVATE,
        )

    def create_event(actor, title, starts, target_workspace=workspace, *, shared=False):
        return service.create_work(
            actor,
            target_workspace,
            Event(
                title=title, starts_at=starts, ends_at=starts + timedelta(hours=1), time_zone="UTC"
            ),
            visibility=Visibility.WORKSPACE if shared else Visibility.PRIVATE,
        )

    for index in range(8):
        create_task(member, f"Overdue {index}", today - timedelta(days=1))
        create_event(member, f"Ongoing {index}", now - timedelta(minutes=10))
    create_task(owner, "Owner private task", today)
    create_task(outsider, "Other workspace task", today, other, shared=True)
    create_task(member, "Future task", today + timedelta(days=1))
    completed = create_task(member, "Completed task", today)
    service.transition(member, workspace, completed.id, target="active", expected_version=1)
    service.transition(member, workspace, completed.id, target="completed", expected_version=2)
    create_event(owner, "Owner private event", now + timedelta(minutes=6))
    create_event(outsider, "Other workspace event", now + timedelta(minutes=6), other, shared=True)
    create_event(member, "Starts later", now + timedelta(minutes=16))
    canceled = create_event(member, "Canceled", now + timedelta(minutes=1))
    service.transition(member, workspace, canceled.id, target="canceled", expected_version=1)

    shared_task = create_task(owner, "Shared due task", today, shared=True)
    personal_tasks = [create_task(member, f"Due {index}", today) for index in range(5)]
    shared_event = create_event(
        owner, "Shared starting soon", now + timedelta(minutes=3), shared=True
    )
    personal_events = [
        create_event(member, f"Starts soon {index}", now + timedelta(minutes=5 + index))
        for index in range(5)
    ]
    page = service.reminder_candidates(member, workspace, local_date=today)
    assert [row.id for row in page.tasks] == [
        shared_task.id,
        *(task.id for task in personal_tasks[:4]),
    ]
    assert [row.id for row in page.events] == [
        shared_event.id,
        *(event.id for event in personal_events[:4]),
    ]
    assert page.has_more
    observer_page = service.reminder_candidates(
        Principal("test", "observer"), workspace, local_date=today
    )
    assert [row.id for row in observer_page.tasks] == [shared_task.id]
    assert [row.id for row in observer_page.events] == [shared_event.id]
    assert not observer_page.has_more
    only_tasks = service.reminder_candidates(member, workspace, local_date=today, category="tasks")
    assert only_tasks.tasks == page.tasks
    assert only_tasks.events == [] and only_tasks.has_more
    only_early_events = service.reminder_candidates(
        member, workspace, local_date=today, category="events", event_lead_minutes=5
    )
    assert only_early_events.tasks == []
    assert [row.id for row in only_early_events.events] == [shared_event.id, personal_events[0].id]
    assert not only_early_events.has_more


def test_reminder_endpoint_enforces_read_scope_active_membership_and_minimal_payload(
    workspace_client, setup
):
    client, workspace, _, users, sign = workspace_client
    service, _, _, _ = setup
    base = f"/api/v2/workspaces/{workspace}"
    url = base + "/reminders?local_date=2030-09-30"
    write = {"Authorization": "Bearer " + sign("member")}
    read = {"Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:read"})}
    only_write = {
        "Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:write"})
    }
    outsider = {"Authorization": "Bearer " + sign("outsider")}
    assert client.get(url).status_code == 401
    assert client.get(url, headers=only_write).status_code == 403
    assert client.get(url, headers=outsider).status_code == 403
    for value in ("0", "2030-02-30", "2030-10-2", "2030-09-30T00:00:00Z"):
        assert client.get(base + "/reminders?local_date=" + value, headers=read).status_code == 422
    created = client.post(
        base + "/work",
        headers=write,
        json={
            "item": {
                "kind": "task",
                "title": "Due agenda",
                "description": "Private agenda text",
                "due_date": "2030-09-30",
            }
        },
    )
    assert created.status_code == 201
    assert client.get(url, headers=read).json() == {
        "tasks": [{"title": "Due agenda", "id": created.json()["id"], "due_date": "2030-09-30"}],
        "events": [],
        "has_more": False,
    }
    for invalid in (
        "category=notes",
        "event_lead_minutes=4",
        "event_lead_minutes=61",
        "event_lead_minutes=7.5",
    ):
        assert client.get(url + "&" + invalid, headers=read).status_code == 422
    starts = (datetime.now(UTC) + timedelta(minutes=20)).replace(microsecond=0)
    event = client.post(
        base + "/work",
        headers=write,
        json={
            "item": {
                "kind": "event",
                "title": "Later rehearsal",
                "time_zone": "UTC",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
            }
        },
    )
    assert event.status_code == 201
    assert client.get(url, headers=read).json()["events"] == []
    longer = client.get(url + "&category=events&event_lead_minutes=30", headers=read).json()
    assert longer == {
        "tasks": [],
        "has_more": False,
        "events": [
            {
                "id": event.json()["id"],
                "title": "Later rehearsal",
                "starts_at": starts.isoformat().replace("+00:00", "Z"),
            }
        ],
    }
    owner = {"Authorization": "Bearer " + sign("owner")}
    assert (
        client.get(url + "&category=events&event_lead_minutes=30", headers=owner).json()["events"]
        == []
    )
    with service.engine.begin() as connection:
        connection.execute(
            text("UPDATE memberships SET active=false WHERE user_id=:user"),
            {"user": users["member"]},
        )
    assert client.get(url, headers=read).status_code == 403
