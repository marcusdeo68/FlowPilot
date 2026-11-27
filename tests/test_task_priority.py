import pytest
from alembic import command
from flowpilot_api.work import Task
from flowpilot_api.work_service import Principal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.postgres


def test_priority_filters_authorized_tasks_and_edits_invalidate_sharing(workspace_client):
    client, workspace, _, _, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}"
    writer = {"Authorization": "Bearer " + sign("member")}
    observer = {"Authorization": "Bearer " + sign("observer")}
    project = client.post(base + "/projects", json={"name": "Pilot"}, headers=writer).json()

    def create(title, *, visibility="workspace", **options):
        response = client.post(
            base + "/work",
            json={
                "item": {"kind": "task", "title": title},
                "visibility": visibility,
                "project_id": project["id"],
                **options,
            },
            headers=writer,
        )
        assert response.status_code == 201
        return response.json()

    normal = create("Budget normal")
    high = create("Budget high", priority="high")
    private = create("Budget private high", visibility="private", priority="high")
    assert normal["priority"] == "normal"
    assert high["priority"] == "high"
    search = {
        "q": "budget",
        "priority": "high",
        "task_status": "open",
        "project_id": project["id"],
        "limit": 1,
    }
    page = client.post(base + "/work-page/search", json=search, headers=observer).json()
    assert [row["id"] for row in page["items"]] == [high["id"]]
    assert page["next_after"] is None
    page = client.get(base + "/work-page", params={"priority": "normal"}, headers=observer).json()
    assert [row["id"] for row in page["items"]] == [normal["id"]]
    assert (
        client.get(base + "/work-page", params={"priority": "urgent"}, headers=observer).status_code
        == 422
    )

    path = base + "/work/" + private["id"]
    assert client.get(path + "/share-preview", headers=writer).json()["item"]["priority"] == "high"
    details = {"title": "Updated budget", "description": None, "due_date": None}

    def edit(version, **overrides):
        return client.patch(
            path + "/task-details",
            headers=writer,
            json={"expected_version": version, "details": {**details, **overrides}},
        )

    assert edit(1).json()["priority"] == "high"
    assert edit(2, priority=None).status_code == 422
    updated = edit(2, priority="low").json()
    assert updated["priority"] == "low" and updated["version"] == 3
    assert edit(3, priority="low").json()["version"] == 3
    assert (
        client.post(path + "/share", json={"expected_version": 2}, headers=writer).status_code
        == 409
    )
    assert edit(3, priority="normal").json()["priority"] == "normal"


def test_priority_migration_preserves_old_rows_and_refuses_lossy_downgrade(setup, pg):
    service, workspace, _, _ = setup
    engine, config = pg
    user = Principal("test", "owner")
    task = service.create_work(user, workspace, Task(title="Existing"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0010_workspace_projects")
    assert service.get_work(user, workspace, task.id).priority == "normal"
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    service.create_work(user, workspace, Task(title="Important"), priority="high")
    with pytest.raises(
        IntegrityError, match="Cannot downgrade while task priority overrides exist"
    ):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0010_workspace_projects")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT task_priority FROM work_items WHERE title='Important'")
            ).scalar_one()
            == "high"
        )
