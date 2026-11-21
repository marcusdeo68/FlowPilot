import pytest

pytestmark = pytest.mark.postgres


def test_preview_projects_workspace_evidence_and_binds_sharing_to_version(workspace_client):
    client, workspace, _, _, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}"
    author = {"Authorization": "Bearer " + sign("member")}
    peer = {"Authorization": "Bearer " + sign("owner")}
    observer = {"Authorization": "Bearer " + sign("observer")}
    read_only = {"Authorization": "Bearer " + sign("member", overrides={"scope": "flowpilot:read"})}
    created = client.post(
        base + "/work",
        headers=author,
        json={
            "item": {
                "kind": "task",
                "title": "Plan workshop",
                "description": "Full synthetic description",
            }
        },
    )
    assert created.status_code == 201
    item = created.json()
    work = base + "/work/" + item["id"]
    preview = work + "/share-preview"
    assert client.get(preview, headers=read_only).status_code == 403
    assert client.get(preview, headers=peer).status_code == 404

    def link(summary, excerpt, visibility):
        nonlocal item
        created_source = client.post(
            base + "/sources",
            headers=author,
            json={
                "reference": f"Synthetic reference {summary}",
                "summary": summary,
                "excerpt": excerpt,
            },
        )
        assert created_source.status_code == 201
        source = created_source.json()["id"]
        linked = client.post(
            work + "/evidence",
            headers=author,
            json={
                "source_id": source,
                "visibility": visibility,
                "expected_version": item["version"],
            },
        )
        assert linked.status_code == 200
        item = linked.json()
        return source

    private = link("Private summary", "Private excerpt", "private")
    summarized = link("Offered summary", "Withheld excerpt", "summary_shared")
    link("Offered details", "Offered excerpt", "excerpt_shared")
    response = client.get(preview, headers=author)
    assert response.status_code == 200
    captured = response.json()
    assert captured["item"] == item
    expected = [
        {"summary": "Offered details", "excerpt": "Offered excerpt"},
        {"summary": "Offered summary"},
    ]
    assert sorted(captured["evidence"], key=lambda row: row["summary"]) == expected
    assert client.get(work + "/evidence", headers=observer).status_code == 404

    link("New summary", "Withheld", "summary_shared")
    assert (
        client.post(
            work + "/share",
            headers=author,
            json={
                "expected_version": captured["item"]["version"],
            },
        ).status_code
        == 409
    )
    assert client.get(work, headers=observer).status_code == 404
    latest = client.get(preview, headers=author).json()
    share = {"expected_version": latest["item"]["version"]}
    result = client.post(work + "/share", headers=author, json=share)
    assert result.status_code == 200
    assert result.json()["visibility"] == "workspace"
    assert client.get(work + "/evidence", headers=observer).json() == latest["evidence"]
    assert client.get(base + "/sources/" + private, headers=observer).status_code == 404
    assert client.get(base + "/sources/" + summarized, headers=observer).status_code == 404
    assert client.get(preview, headers=peer).status_code == 403
    assert client.get(preview, headers=author).status_code == 409
    assert client.post(work + "/share", headers=author, json=share).status_code == 409
    assert (
        sum(
            event["operation"] == "shared"
            for event in client.get(work + "/history", headers=observer).json()
        )
        == 1
    )
    event = client.post(
        base + "/work",
        headers=author,
        json={
            "item": {
                "kind": "event",
                "title": "Synthetic rehearsal",
                "time_zone": "UTC",
                "starts_at": "2030-06-15T14:00:00Z",
                "ends_at": "2030-06-15T15:00:00Z",
            }
        },
    )
    assert event.status_code == 201
    event_path = base + "/work/" + event.json()["id"]
    assert client.get(event_path + "/share-preview", headers=author).status_code == 200
    assert (
        client.post(
            event_path + "/transitions",
            headers=author,
            json={
                "target": "canceled",
                "expected_version": 1,
            },
        ).status_code
        == 200
    )
    assert client.get(event_path + "/share-preview", headers=author).status_code == 409


def test_visibility_filters_precede_pagination_and_validate_cursors(workspace_client):
    client, workspace, _, _, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}"
    author = {"Authorization": "Bearer " + sign("member")}
    peer = {"Authorization": "Bearer " + sign("observer")}

    def make(title, visibility):
        response = client.post(
            base + "/work",
            headers=author,
            json={
                "item": {"kind": "task", "title": title},
                "visibility": visibility,
            },
        )
        assert response.status_code == 201
        return response.json()

    oldest = make("Oldest shared", "workspace")
    newest = make("Newest shared", "workspace")
    hidden = [make(f"Private {index}", "private") for index in range(4)]
    shared = base + "/work-page?visibility=workspace&limit=1"
    assert client.get(shared, headers=author).json() == {
        "items": [newest],
        "next_after": newest["id"],
    }
    assert client.get(shared + "&after=" + newest["id"], headers=peer).json() == {
        "items": [oldest],
        "next_after": None,
    }
    assert client.get(shared + "&after=" + hidden[-1]["id"], headers=author).status_code == 404
    assert client.get(shared + "&after=" + hidden[-1]["id"], headers=peer).status_code == 404
    assert client.get(shared + "&kind=event", headers=peer).json()["items"] == []
    private = base + "/work-page?visibility=private"
    assert client.get(private, headers=peer).json()["items"] == []
    assert client.get(private, headers=author).json()["items"] == hidden[::-1]
    assert client.get(private + "&after=" + newest["id"], headers=author).status_code == 404
    assert client.get(base + "/work-page?visibility=public", headers=author).status_code == 422
