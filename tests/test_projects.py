import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.postgres


def test_projects_isolate_assignments_and_bind_sharing_review(workspace_client):
    client, ws, other, _, sign = workspace_client
    base = f"/api/v2/workspaces/{ws}"
    writer = {"Authorization": "Bearer " + sign("member")}
    viewer = {"Authorization": "Bearer " + sign("observer")}
    outside = {"Authorization": "Bearer " + sign("outsider")}

    def project(workspace, headers, name):
        return client.post(
            f"/api/v2/workspaces/{workspace}/projects", headers=headers, json={"name": name}
        )

    assert client.get(base + "/projects", headers=outside).status_code == 403
    assert project(ws, viewer, "Denied").status_code == 403
    assert project(ws, writer, "  ").status_code == 422
    created = project(ws, writer, " Budget ")
    assert created.status_code == 201
    item = created.json()
    assert item["name"] == "Budget"
    assert client.get(base + "/projects", headers=viewer).json() == [item]
    assert project(ws, writer, "budget").status_code == 409
    foreign = project(other, outside, "Foreign").json()["id"]

    def task(title, *, project_id=None, visibility="private"):
        return client.post(
            base + "/work",
            headers=writer,
            json={
                "item": {"kind": "task", "title": title},
                "project_id": project_id,
                "visibility": visibility,
            },
        )

    assert task("Invalid", project_id=foreign).status_code == 404
    shared = task("Shared budget", project_id=item["id"], visibility="workspace").json()
    private = task("Own budget").json()
    path = f"{base}/work/{private['id']}"
    preview = client.get(path + "/share-preview", headers=writer).json()
    assert preview["project_name"] is None
    details = {"title": "Own budget", "description": None, "due_date": None, "project_id": foreign}
    payload = {"details": details, "expected_version": 1}
    assert client.patch(path + "/task-details", headers=writer, json=payload).status_code == 404
    details["project_id"] = item["id"]
    saved = client.patch(path + "/task-details", headers=writer, json=payload).json()
    assert saved["project_id"] == item["id"] and saved["version"] == 2
    assert client.get(path + "/share-preview", headers=writer).json()["project_name"] == "Budget"
    stale = client.post(path + "/share", headers=writer, json={"expected_version": 1})
    assert stale.status_code == 409
    observer_rows = client.post(
        base + "/work-page/search",
        headers=viewer,
        json={"q": "Budget", "project_id": item["id"], "task_status": "open", "limit": 1},
    ).json()
    assert [row["id"] for row in observer_rows["items"]] == [shared["id"]]
    assert observer_rows["next_after"] is None
    member_rows = client.get(
        base + "/work-page", headers=writer, params={"project_id": item["id"]}
    ).json()["items"]
    assert {row["id"] for row in member_rows} == {shared["id"], private["id"]}
    assert (
        client.get(base + "/work-page", headers=viewer, params={"project_id": foreign}).json()[
            "items"
        ]
        == []
    )
    details.pop("project_id")
    details["title"] = "Updated budget"
    payload["expected_version"] = 2
    saved = client.patch(path + "/task-details", headers=writer, json=payload).json()
    assert saved["project_id"] == item["id"] and saved["version"] == 3
    details["project_id"] = None
    payload["expected_version"] = 3
    saved = client.patch(path + "/task-details", headers=writer, json=payload).json()
    assert saved["project_id"] is None and saved["version"] == 4


def test_workspace_project_history_blocks_lossy_downgrade(setup, pg):
    from flowpilot_api.work_service import Principal

    service, ws, _, _ = setup
    engine, config = pg
    service.create_project(Principal("test", "owner"), ws, "Keep")
    with pytest.raises(IntegrityError, match="Cannot downgrade while workspace projects exist"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0009_workspace_invitations")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT name FROM workspace_projects")).scalar_one() == "Keep"
        )
