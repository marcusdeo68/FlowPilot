import pytest
from alembic import command
from flowpilot_api.work import Task, TaskDetails
from flowpilot_api.work_service import Principal
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.postgres


def edit_body(version=1, **changes):
    return {
        "expected_version": version,
        "details": {
            "title": "  Confirm venue  ",
            "description": "  Check the draft  ",
            "due_date": "2026-12-04",
            **changes,
        },
    }


def test_task_edit_contract_versions_and_audit(workspace_client):
    client, workspace, _, users, sign = workspace_client
    headers = {"Authorization": "Bearer " + sign("member")}
    base = f"/api/v2/workspaces/{workspace}/work"
    created = client.post(base, headers=headers, json={"item": {"kind": "task", "title": "Draft"}})
    assert created.status_code == 201
    initial = created.json()
    item = f"{base}/{initial['id']}"
    path = item + "/task-details"

    response = client.patch(path, headers=headers, json=edit_body())
    assert response.status_code == 200
    edited = response.json()
    assert edited["data"] == {
        "kind": "task",
        "title": "Confirm venue",
        "description": "Check the draft",
        "due_date": "2026-12-04",
        "status": "open",
    }
    assert edited["version"] == 2
    for key in ("id", "visibility", "creator_id", "owner_id", "created_at", "workspace_id"):
        assert edited[key] == initial[key]
    assert edited["visibility"] == "private"
    assert client.patch(path, headers=headers, json=edit_body()).status_code == 409
    assert client.patch(path, headers=headers, json=edit_body(2)).json() == edited

    cleared = client.patch(
        path, headers=headers, json=edit_body(2, description=None, due_date=None)
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["description"] is None
    assert cleared.json()["data"]["due_date"] is None
    assert cleared.json()["version"] == 3
    audit = client.get(item + "/history", headers=headers).json()
    assert [(event["operation"], event["version"]) for event in audit] == [
        ("created", 1),
        ("details_changed", 2),
        ("details_changed", 3),
    ]
    assert {event["actor_id"] for event in audit} == {str(users["member"])}
    assert all("title" not in event and "description" not in event for event in audit)


def test_task_edit_checks_scope_visibility_kind_and_payload(workspace_client):
    client, workspace, other, _, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}/work"
    member = {"Authorization": "Bearer " + sign("member")}
    owner = {"Authorization": "Bearer " + sign("owner")}
    observer = {"Authorization": "Bearer " + sign("observer")}
    read_only = {"Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:read"})}
    outsider = {"Authorization": "Bearer " + sign("outsider")}

    def create(kind, visibility="private"):
        response = client.post(
            base,
            headers=member,
            json={"item": {"kind": kind, "title": "Draft"}, "visibility": visibility},
        )
        assert response.status_code == 201
        return response.json()["id"]

    private, shared, commitment = create("task"), create("task", "workspace"), create("commitment")
    for actor, item, status in [
        ({}, private, 401),
        (owner, private, 404),
        (owner, shared, 403),
        (observer, shared, 403),
        (read_only, private, 403),
        (outsider, shared, 403),
        (member, commitment, 404),
    ]:
        assert (
            client.patch(f"{base}/{item}/task-details", headers=actor, json=edit_body()).status_code
            == status
        )
    foreign = f"/api/v2/workspaces/{other}/work/{shared}/task-details"
    assert client.patch(foreign, headers=outsider, json=edit_body()).status_code == 404
    path = f"{base}/{shared}/task-details"
    for payload in [
        edit_body(True),
        edit_body(0),
        edit_body(title="  "),
        edit_body(due_date=0),
        edit_body(due_date="2026-02-30"),
        edit_body(due_date="20261204"),
        edit_body(status="completed"),
        {"expected_version": 1, "details": {"title": "Omitted"}},
    ]:
        assert client.patch(path, headers=member, json=payload).status_code == 422
    result = client.patch(path, headers=member, json=edit_body())
    assert result.status_code == 200 and result.json()["visibility"] == "workspace"
    assert (
        client.get(f"{base}/{shared}", headers=observer).json()["data"]["title"] == "Confirm venue"
    )


def test_edit_rolls_back_if_append_only_history_cannot_be_written(setup):
    service, workspace, _, _ = setup
    principal = Principal("test", "member")
    initial = service.create_work(principal, workspace, Task(title="Draft"))
    with service.engine.begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION fail_edit_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected edit audit failure'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER fail_edit BEFORE INSERT ON audit_events
            FOR EACH ROW WHEN (NEW.operation = 'details_changed') EXECUTE FUNCTION fail_edit_audit()""")
        )
    with pytest.raises(DBAPIError, match="injected edit audit failure"):
        service.edit_task(
            principal,
            workspace,
            initial.id,
            expected_version=1,
            details=TaskDetails(title="Changed", description=None, due_date=None),
        )
    assert service.get_work(principal, workspace, initial.id) == initial
    assert [event["operation"] for event in service.history(principal, workspace, initial.id)] == [
        "created"
    ]


def test_task_edit_history_prevents_lossy_downgrade(setup, pg):
    service, workspace, _, _ = setup
    engine, config = pg
    principal = Principal("test", "member")
    initial = service.create_work(principal, workspace, Task(title="Draft"))
    updated = service.edit_task(
        principal,
        workspace,
        initial.id,
        expected_version=1,
        details=TaskDetails(title="Changed", description=None, due_date=None),
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006_login_transactions")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0007_task_details_audit"
        )
    assert service.get_work(principal, workspace, initial.id) == updated
    assert [event["operation"] for event in service.history(principal, workspace, initial.id)] == [
        "created",
        "details_changed",
    ]
