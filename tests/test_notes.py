from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from flowpilot_api.notes import NoteBody, NoteEdit, NotesService
from flowpilot_api.repository import VersionConflict
from flowpilot_api.storage import SCHEMA_REVISION
from flowpilot_api.work_service import Principal
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.postgres


def test_notes_http_lifecycle_and_boundaries(workspace_client):
    client, workspace, other, _, sign = workspace_client
    path = f"/api/v2/workspaces/{workspace}/notes"
    other_path = f"/api/v2/workspaces/{other}/notes"

    def auth(subject, scope=None):
        overrides = {"scope": scope} if scope else None
        return {"Authorization": "Bearer " + sign(subject, overrides=overrides)}

    member = auth("member")
    read_only = auth("member", "flowpilot:read")
    owner = auth("owner")
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth("outsider")).status_code == 403
    assert client.post(path, headers=read_only, json={"body": "Read only"}).status_code == 403
    assert client.post(path, headers=auth("observer"), json={"body": "Observer"}).status_code == 403
    for invalid in (
        {"body": " \n "},
        {"body": "x" * 2001},
        {"body": "\0"},
        {"body": "x", "owner_id": "x"},
    ):
        result = client.post(path, headers=member, json=invalid)
        assert result.status_code == 422
        assert result.json() == {"detail": "Invalid note request"}
    bad_unicode = client.post(
        path,
        headers={**member, "Content-Type": "application/json"},
        content=b'{"body":"\\ud800"}',
    )
    assert bad_unicode.status_code == 422
    assert bad_unicode.json() == {"detail": "Invalid note request"}

    value = "  First line\r\n  More text 🙂  "
    created = client.post(path, headers=member, json={"body": value})
    assert created.status_code == 201
    note = created.json()
    url = path + "/" + note["id"]
    assert note["version"] == 1 and note["archived"] is False and note["body"] == value
    assert client.get(path, headers=read_only).json() == {"items": [note], "next_after": None}
    assert client.get(path, headers=owner).json() == {"items": [], "next_after": None}
    update = {"body": "Updated", "expected_version": 1}
    assert client.patch(url, headers=owner, json=update).status_code == 404
    assert (
        client.patch(
            other_path + "/" + note["id"], headers=auth("outsider"), json=update
        ).status_code
        == 404
    )
    for reader in (owner, member):
        missing = client.get(path, headers=reader, params={"after": str(uuid4())})
        assert missing.status_code == 404
    assert client.get(path, headers=owner, params={"after": note["id"]}).status_code == 404
    for version in (True, "1", 0):
        assert (
            client.patch(
                url, headers=member, json={**update, "expected_version": version}
            ).status_code
            == 422
        )
    for invalid_limit in (0, 101):
        assert client.get(path, headers=member, params={"limit": invalid_limit}).status_code == 422

    stored = client.patch(url, headers=member, json=update)
    assert stored.status_code == 200 and stored.json()["version"] == 2
    assert client.patch(url, headers=member, json=update).status_code == 409
    same = client.patch(url, headers=member, json={**update, "expected_version": 2})
    assert same.json() == stored.json()
    assert (
        client.post(
            url + "/state", headers=member, json={"expected_version": 2, "archived": "true"}
        ).status_code
        == 422
    )
    archived = client.post(
        url + "/state", headers=member, json={"expected_version": 2, "archived": True}
    )
    assert archived.status_code == 200 and archived.json()["version"] == 3
    assert client.get(path, headers=owner, params={"archived": True}).json()["items"] == []
    assert client.get(path, headers=member).json()["items"] == []
    assert client.get(path, headers=member, params={"archived": True}).json()["items"] == [
        archived.json()
    ]
    assert (
        client.patch(url, headers=member, json={**update, "expected_version": 3}).status_code == 409
    )
    restored = client.post(
        url + "/state", headers=member, json={"expected_version": 3, "archived": False}
    )
    assert restored.status_code == 200 and restored.json()["version"] == 4
    assert client.get(path, headers=member).json()["items"] == [restored.json()]


def test_notes_lock_versions_and_commit_metadata_atomically(setup):
    work, workspace, _, users = setup
    engine = work.engine
    service = NotesService(engine)
    author = Principal("test", "member")
    note = service.create(author, workspace, NoteBody(body="Synthetic note"))

    def edit(body):
        try:
            return service.update(
                author, workspace, note.id, NoteEdit(body=body, expected_version=1)
            )
        except VersionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [result for result in pool.map(edit, ("First save", "Second save")) if result]
    assert len(winners) == 1 and winners[0].version == 2

    with engine.begin() as connection:
        assert connection.execute(
            text(
                "SELECT operation, version, actor_id FROM note_events WHERE note_id=:id ORDER BY version"
            ),
            {"id": note.id},
        ).all() == [("created", 1, users["member"]), ("edited", 2, users["member"])]
        connection.execute(text("ALTER TABLE note_events ADD CHECK (version < 3)"))
    with pytest.raises(IntegrityError):
        service.update(
            author, workspace, note.id, NoteEdit(body="Must roll back", expected_version=2)
        )
    assert service.page(author, workspace).items == winners

    for statement in (
        "UPDATE note_events SET operation='archived'",
        "DELETE FROM note_events",
        "TRUNCATE note_events",
    ):
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(statement))


def test_notes_cursor_survives_archiving_and_stored_deactivation(workspace_client, setup):
    client, workspace, _, users, sign = workspace_client
    work, _, _, _ = setup
    path = f"/api/v2/workspaces/{workspace}/notes"
    auth = {"Authorization": "Bearer " + sign("member")}
    ids = []
    for body in ("Older", "Newer"):
        created = client.post(path, headers=auth, json={"body": body})
        assert created.status_code == 201
        ids.append(created.json()["id"])
    first = client.get(path, headers=auth, params={"limit": 1}).json()
    assert first["next_after"] == ids[-1]
    moved = client.post(
        path + f"/{ids[-1]}/state", headers=auth, json={"expected_version": 1, "archived": True}
    )
    assert moved.status_code == 200
    next_page = client.get(path, headers=auth, params={"limit": 1, "after": first["next_after"]})
    assert next_page.status_code == 200
    assert [note["id"] for note in next_page.json()["items"]] == ids[:1]
    assert next_page.json()["next_after"] is None
    with work.engine.begin() as connection:
        connection.execute(
            text("UPDATE memberships SET active=false WHERE workspace_id=:ws AND user_id=:member"),
            {"ws": workspace, "member": users["member"]},
        )
    assert client.get(path, headers=auth).status_code == 403
    assert (
        client.patch(
            path + f"/{ids[0]}", headers=auth, json={"body": "Denied", "expected_version": 1}
        ).status_code
        == 403
    )


def test_notes_migration_preserves_existing_private_content(setup, pg):
    work, workspace, _, _ = setup
    engine, config = pg
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007_task_details_audit")
        assert connection.execute(text("SELECT to_regclass('notes')")).scalar_one() is None
        command.upgrade(config, "head")
    service = NotesService(work.engine)
    author = Principal("test", "member")
    note = service.create(author, workspace, NoteBody(body="Keep the saved note"))
    with (
        pytest.raises(IntegrityError, match="Cannot downgrade while private notes exist"),
        engine.begin() as connection,
    ):
        config.attributes["connection"] = connection
        command.downgrade(config, "0007_task_details_audit")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == SCHEMA_REVISION
        )
        assert connection.execute(text("SELECT note_id FROM note_events")).scalar_one() == note.id
    assert service.page(author, workspace).items == [note]
