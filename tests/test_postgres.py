"""Real PostgreSQL integration checks. Each test owns a random disposable schema."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from flowpilot_api.access import AccessDenied, EvidenceVisibility, Role, Visibility
from flowpilot_api.membership_service import (
    LastOwnerConflict,
    MemberNotFound,
    MembershipConflict,
    MembershipService,
    ProfileNotFound,
    WorkspaceCreate,
)
from flowpilot_api.repository import InvalidTransition, VersionConflict
from flowpilot_api.work import Commitment, Event, Task
from flowpilot_api.work_service import (
    ManualSource,
    Principal,
    SourceNotFound,
    WorkNotFound,
    WorkService,
)
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.schema import CreateSchema, DropSchema

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg():
    url = os.environ.get("FLOWPILOT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set FLOWPILOT_TEST_DATABASE_URL for real PostgreSQL checks")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Integration tests require a PostgreSQL database ending in _test")
    schema = "fp_test_" + uuid4().hex
    root = create_engine(parsed, hide_parameters=True)
    with root.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(
        parsed, connect_args={"options": f"-csearch_path={schema}"}, hide_parameters=True
    )
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine, config
    finally:
        engine.dispose()
        # The target is the exact random schema created above, never public/user schemas.
        with root.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        root.dispose()


@pytest.fixture
def setup(pg):
    engine, _ = pg
    workspace, other = uuid4(), uuid4()
    users = {name: uuid4() for name in ("owner", "member", "observer", "outsider")}
    with engine.begin() as connection:
        for label, value in (("Synthetic A", workspace), ("Synthetic B", other)):
            connection.execute(
                text("INSERT INTO workspaces (id, name) VALUES (:id, :name)"),
                {"id": value, "name": label},
            )
        for name, user_id in users.items():
            connection.execute(
                text("INSERT INTO users (id, issuer, subject) VALUES (:id, 'test', :name)"),
                {"id": user_id, "name": name},
            )
            connection.execute(
                text("""INSERT INTO memberships (workspace_id, user_id, role)
                VALUES (:workspace, :user, :role)"""),
                {
                    "workspace": other if name == "outsider" else workspace,
                    "user": user_id,
                    "role": "owner" if name == "outsider" else name,
                },
            )
    return WorkService(engine), workspace, other, users


def principal(name="owner"):
    return Principal("test", name)


def test_migration_round_trip(pg):
    engine, config = pg
    tables = {
        "users",
        "workspaces",
        "memberships",
        "source_items",
        "work_items",
        "evidence_links",
        "audit_events",
        "workspace_events",
    }
    assert tables <= set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    assert not tables.intersection(inspect(engine).get_table_names())
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    assert tables <= set(inspect(engine).get_table_names())


def test_workflow_and_state_constraints(setup):
    service, workspace, _, _ = setup
    item = service.create_work(principal(), workspace, Task(title="Synthetic work"))
    assert item.data.status == "open"
    with pytest.raises(InvalidTransition):
        service.transition(principal(), workspace, item.id, target="completed", expected_version=1)
    active = service.transition(
        principal(), workspace, item.id, target="active", expected_version=1
    )
    assert active.version == 2
    with pytest.raises(VersionConflict):
        service.transition(principal(), workspace, item.id, target="completed", expected_version=1)
    completed = service.transition(
        principal(), workspace, item.id, target="completed", expected_version=2
    )
    assert completed.version == 3
    assert [event["operation"] for event in service.history(principal(), workspace, item.id)] == [
        "created",
        "status_changed",
        "status_changed",
    ]
    with pytest.raises(InvalidTransition):
        service.create_work(principal(), workspace, Task(title="Skip review", status="completed"))


def test_private_and_cross_workspace_access(setup):
    service, workspace, other, _ = setup
    item = service.create_work(principal("member"), workspace, Commitment(title="Private"))
    assert service.list_work(principal(), workspace) == []
    for actor in ("owner", "observer"):
        with pytest.raises(WorkNotFound):
            service.get_work(principal(actor), workspace, item.id)
        with pytest.raises(WorkNotFound):
            service.history(principal(actor), workspace, item.id)
    with pytest.raises(AccessDenied):
        service.get_work(principal("outsider"), workspace, item.id)
    with pytest.raises(AccessDenied):
        service.create_work(principal(), other, Task(title="Wrong workspace"))
    with pytest.raises(WorkNotFound):
        service.get_work(principal("outsider"), other, item.id)
    with pytest.raises(WorkNotFound):
        service.transition(principal(), workspace, item.id, target="confirmed", expected_version=1)


def test_shared_work_and_observer_read_only(setup):
    service, workspace, _, _ = setup
    item = service.create_work(principal("member"), workspace, Task(title="Share me"))
    shared = service.share_work(principal("member"), workspace, item.id, expected_version=1)
    assert shared.visibility == Visibility.WORKSPACE
    assert service.get_work(principal("observer"), workspace, item.id).version == 2
    assert len(service.list_work(principal(), workspace)) == 1
    for action in (
        lambda: service.create_work(principal("observer"), workspace, Task(title="No write")),
        lambda: service.transition(
            principal("observer"), workspace, item.id, target="active", expected_version=2
        ),
    ):
        with pytest.raises(AccessDenied):
            action()
    assert (
        service.transition(
            principal(), workspace, item.id, target="active", expected_version=2
        ).version
        == 3
    )


@pytest.mark.parametrize(
    "visibility,expected",
    [
        (EvidenceVisibility.PRIVATE, []),
        (EvidenceVisibility.SUMMARY_SHARED, [{"summary": "Synthetic summary"}]),
        (
            EvidenceVisibility.EXCERPT_SHARED,
            [{"summary": "Synthetic summary", "excerpt": "Private excerpt"}],
        ),
    ],
)
def test_evidence_owner_explicit_sharing(setup, visibility, expected):
    service, workspace, other, _ = setup
    item = service.create_work(
        principal("member"),
        workspace,
        Task(title="Shared derived task"),
        visibility=Visibility.WORKSPACE,
    )
    source = service.create_source(
        principal("member"),
        workspace,
        ManualSource(
            reference="synthetic-1", summary="Synthetic summary", excerpt="Private excerpt"
        ),
    )
    # Even a workspace owner cannot share another member's source.
    with pytest.raises(SourceNotFound):
        service.link_evidence(
            principal(), workspace, item.id, source, visibility=visibility, expected_version=1
        )
    service.link_evidence(
        principal("member"), workspace, item.id, source, visibility=visibility, expected_version=1
    )
    assert service.evidence(principal(), workspace, item.id) == expected
    assert service.evidence(principal("member"), workspace, item.id) == [
        {"summary": "Synthetic summary", "excerpt": "Private excerpt"}
    ]
    with pytest.raises(WorkNotFound):
        service.evidence(principal("outsider"), other, item.id)


def test_removed_membership_rechecked_each_operation(setup):
    service, workspace, _, users = setup
    item = service.create_work(principal(), workspace, Task(title="Before removal"))
    with service.engine.begin() as connection:
        connection.execute(
            text("UPDATE memberships SET active=false WHERE user_id=:user"),
            {"user": users["owner"]},
        )
    with pytest.raises(AccessDenied):
        service.get_work(principal(), workspace, item.id)
    with pytest.raises(AccessDenied):
        service.transition(principal(), workspace, item.id, target="active", expected_version=1)


def test_database_rejects_cross_workspace_relationships(setup):
    service, workspace, _, users = setup
    with pytest.raises(IntegrityError):
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO work_items
                (id, workspace_id, creator_id, owner_id, kind, title, status)
                VALUES (:id, :workspace, :user, :user, 'task', 'Wrong tenant', 'open')"""),
                {"id": uuid4(), "workspace": workspace, "user": users["outsider"]},
            )
    assert service.list_work(principal(), workspace) == []


def test_audit_is_atomic_and_append_only(setup):
    service, workspace, _, _ = setup
    item = service.create_work(principal(), workspace, Task(title="Transaction"))
    for statement in (
        "DELETE FROM audit_events",
        "UPDATE audit_events SET version=2",
        "TRUNCATE audit_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            with service.engine.begin() as connection:
                connection.execute(text(statement))
    with service.engine.begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION fail_audit_insert() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected audit failure'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events
            FOR EACH ROW EXECUTE FUNCTION fail_audit_insert()""")
        )
    with pytest.raises(DBAPIError, match="injected audit failure"):
        service.transition(principal(), workspace, item.id, target="active", expected_version=1)
    saved = service.get_work(principal(), workspace, item.id)
    assert (saved.data.status, saved.version) == ("open", 1)
    assert len(service.history(principal(), workspace, item.id)) == 1


def test_real_concurrent_writes(setup):
    service, workspace, _, _ = setup
    item = service.create_work(principal(), workspace, Task(title="Concurrent"))

    def write(_):
        try:
            service.transition(principal(), workspace, item.id, target="active", expected_version=1)
            return "ok"
        except VersionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, range(2))) == ["conflict", "ok"]
    assert len(service.history(principal(), workspace, item.id)) == 2


def test_event_persists_aware_instants(setup):
    service, workspace, _, _ = setup
    event = Event(
        title="Synthetic event",
        starts_at="2026-11-12T10:00:00-08:00",
        ends_at="2026-11-12T11:00:00-08:00",
        time_zone="America/Los_Angeles",
    )
    item = service.create_work(principal(), workspace, event)
    saved = service.get_work(principal(), workspace, item.id)
    assert saved.data.starts_at == event.starts_at
    assert saved.data.time_zone == event.time_zone


def test_source_privacy_and_cross_workspace_links(setup):
    service, workspace, other, users = setup
    data = ManualSource(reference="synthetic-source", summary="Summary", excerpt="Private excerpt")
    source = service.create_source(principal("outsider"), other, data)
    assert service.get_source(principal("outsider"), other, source) == data
    with pytest.raises(SourceNotFound):
        service.get_source(principal(), workspace, source)
    own_source = service.create_source(principal("member"), workspace, data)
    with pytest.raises(SourceNotFound):
        service.get_source(principal(), workspace, own_source)
    item = service.create_work(principal(), workspace, Task(title="Unrelated"))
    with pytest.raises(SourceNotFound):
        service.link_evidence(
            principal(),
            workspace,
            item.id,
            source,
            visibility=EvidenceVisibility.EXCERPT_SHARED,
            expected_version=1,
        )
    with pytest.raises(IntegrityError):
        with service.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO evidence_links
                (workspace_id, work_id, source_id, source_owner_id, visibility)
                VALUES (:workspace, :work, :source, :owner, 'private')"""),
                {
                    "workspace": workspace,
                    "work": item.id,
                    "source": source,
                    "owner": users["outsider"],
                },
            )
    assert service.evidence(principal(), workspace, item.id) == []


def test_identity_issuer_and_stored_role_are_authoritative(setup):
    service, workspace, _, users = setup
    with pytest.raises(AccessDenied):
        service.list_work(Principal("unverified-other-issuer", "owner"), workspace)
    with service.engine.begin() as connection:
        connection.execute(
            text("UPDATE memberships SET role='observer' WHERE user_id=:user"),
            {"user": users["owner"]},
        )
    assert service.list_work(principal(), workspace) == []
    with pytest.raises(AccessDenied):
        service.create_work(principal(), workspace, Task(title="Old owner role must not survive"))


def test_database_type_constraint_cannot_be_bypassed(setup):
    service, workspace, _, _ = setup
    item = service.create_work(principal(), workspace, Task(title="Typed task"))
    with pytest.raises(IntegrityError):
        with service.engine.begin() as connection:
            connection.execute(
                text("UPDATE work_items SET status='confirmed' WHERE id=:id"), {"id": item.id}
            )
    assert service.get_work(principal(), workspace, item.id).data.status == "open"


def test_source_audit_commits_with_source_and_rolls_back_on_failure(setup):
    service, workspace, _, users = setup
    source = service.create_source(
        principal(),
        workspace,
        ManualSource(reference="first", summary="Summary", excerpt="Private"),
    )
    with service.engine.begin() as connection:
        event = (
            connection.execute(
                text("SELECT * FROM audit_events WHERE source_id=:source"), {"source": source}
            )
            .mappings()
            .one()
        )
        assert event["operation"] == "source_created"
        assert event["actor_id"] == users["owner"]
        assert event["work_id"] is None
        connection.execute(
            text("""CREATE FUNCTION fail_source_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'source audit failure'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER fail_source_audit BEFORE INSERT ON audit_events
            FOR EACH ROW EXECUTE FUNCTION fail_source_audit()""")
        )
    with pytest.raises(DBAPIError, match="source audit failure"):
        service.create_source(
            principal(),
            workspace,
            ManualSource(reference="rolled-back", summary="Summary", excerpt="Private"),
        )
    with service.engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM source_items")).scalar_one() == 1


@pytest.fixture
def workspace_client(setup, token_tools):
    from fastapi.testclient import TestClient
    from flowpilot_api.workspace_api import create_workspace_app

    service, workspace, other, users = setup
    config, verifier, sign = token_tools
    with service.engine.begin() as connection:
        connection.execute(text("UPDATE users SET issuer=:issuer"), {"issuer": config.issuer})
    app = create_workspace_app(engine=service.engine, verifier=verifier)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, workspace, other, users, sign


def test_workspace_http_authentication_boundary(workspace_client):
    client, workspace, _, _, sign = workspace_client
    path = f"/api/v2/workspaces/{workspace}/work"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer fake"}).status_code == 401
    assert client.get(path, headers={"X-User-ID": "owner", "X-Role": "owner"}).status_code == 401
    assert client.get("/api/v1/commitments").status_code == 404
    assert client.get("/readyz").status_code == 200
    assert (
        client.get(path, headers={"Authorization": "Bearer " + sign("outsider")}).status_code == 403
    )
    response = client.get(path, headers={"Authorization": "Bearer " + sign()})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == []


def test_workspace_http_create_transition_and_tenant_checks(workspace_client):
    client, workspace, other, _, sign = workspace_client
    headers = {"Authorization": "Bearer " + sign()}
    path = f"/api/v2/workspaces/{workspace}/work"
    response = client.post(
        path, headers=headers, json={"item": {"kind": "task", "title": "API task"}}
    )
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["data"]["status"] == "open"
    assert (
        client.get(
            path + "/" + item["id"], headers={"Authorization": "Bearer " + sign("member")}
        ).status_code
        == 404
    )
    transition = path + f"/{item['id']}/transitions"
    assert (
        client.post(
            transition, headers=headers, json={"target": "active", "expected_version": 1}
        ).status_code
        == 200
    )
    assert (
        client.post(
            transition, headers=headers, json={"target": "completed", "expected_version": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v2/workspaces/{other}/work",
            headers=headers,
            json={"item": {"kind": "task", "title": "Wrong tenant"}},
        ).status_code
        == 403
    )
    assert (
        client.post(
            path,
            headers=headers,
            json={"item": {"kind": "task", "title": "Forged"}, "role": "owner"},
        ).status_code
        == 422
    )


def test_workspace_http_scopes_and_stored_role(workspace_client):
    client, workspace, _, _, sign = workspace_client
    path = f"/api/v2/workspaces/{workspace}/work"
    assert (
        client.get(
            path, headers={"Authorization": "Bearer " + sign(overrides={"scope": ""})}
        ).status_code
        == 403
    )
    read_only = {"Authorization": "Bearer " + sign(overrides={"scope": "flowpilot:read"})}
    assert client.get(path, headers=read_only).status_code == 200
    assert (
        client.post(
            path, headers=read_only, json={"item": {"kind": "task", "title": "No scope"}}
        ).status_code
        == 403
    )
    forged_role = {"Authorization": "Bearer " + sign("observer", overrides={"role": "owner"})}
    assert (
        client.post(
            path, headers=forged_role, json={"item": {"kind": "task", "title": "No role"}}
        ).status_code
        == 403
    )


def test_workspace_http_evidence_requires_source_owner(workspace_client):
    client, workspace, _, _, sign = workspace_client
    base = f"/api/v2/workspaces/{workspace}"
    member = {"Authorization": "Bearer " + sign("member")}
    owner = {"Authorization": "Bearer " + sign()}
    source = client.post(
        base + "/sources",
        headers=member,
        json={
            "reference": "synthetic-message",
            "summary": "Shared summary",
            "excerpt": "Private excerpt",
        },
    )
    assert source.status_code == 201
    source_id = source.json()["id"]
    assert client.get(base + f"/sources/{source_id}", headers=owner).status_code == 404
    work = client.post(
        base + "/work",
        headers=member,
        json={"item": {"kind": "task", "title": "Shared task"}, "visibility": "workspace"},
    ).json()
    path = base + f"/work/{work['id']}/evidence"
    payload = {"source_id": source_id, "visibility": "summary_shared", "expected_version": 1}
    assert client.post(path, headers=owner, json=payload).status_code == 404
    assert client.post(path, headers=member, json=payload).status_code == 200
    assert client.get(path, headers=owner).json() == [{"summary": "Shared summary"}]
    assert client.get(path, headers=member).json() == [
        {"summary": "Shared summary", "excerpt": "Private excerpt"}
    ]


def test_new_workspace_provisions_only_verified_identity(pg):
    engine, _ = pg
    service = MembershipService(engine)
    person = Principal("synthetic-issuer", "new-user")
    assert service.list_workspaces(person) == []
    with pytest.raises(ProfileNotFound):
        service.profile(person)
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
    workspace = service.create_workspace(person, WorkspaceCreate(name=" First workspace "))
    profile = service.profile(person)
    assert workspace.name == "First workspace"
    assert workspace.role == Role.OWNER
    assert service.list_workspaces(person) == [workspace]
    assert service.list_members(person, workspace.id)[0].user_id == profile.id
    events = service.history(person, workspace.id)
    assert events[0]["actor_id"] == profile.id
    assert events[0]["operation"] == "workspace_created"
    assert service.list_workspaces(Principal("other-issuer", "new-user")) == []


def test_concurrent_onboarding_does_not_duplicate_identity(pg):
    engine, _ = pg
    service = MembershipService(engine)
    person = Principal("synthetic-issuer", "new-user")
    with ThreadPoolExecutor(max_workers=2) as pool:
        spaces = list(
            pool.map(
                lambda _: service.create_workspace(person, WorkspaceCreate(name="Personal")),
                range(2),
            )
        )
    assert len({space.id for space in spaces}) == 2
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM workspace_events")).scalar_one() == 2


def test_workspace_creation_rolls_back_profile_and_membership_on_audit_failure(pg):
    engine, _ = pg
    with engine.begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION fail_workspace_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'workspace audit failure'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER fail_workspace_audit BEFORE INSERT ON workspace_events
            FOR EACH ROW EXECUTE FUNCTION fail_workspace_audit()""")
        )
    service = MembershipService(engine)
    with pytest.raises(DBAPIError, match="workspace audit failure"):
        service.create_workspace(principal(), WorkspaceCreate(name="Must roll back"))
    with engine.begin() as connection:
        for table in ("users", "workspaces", "memberships", "workspace_events"):
            # Fixed test-owned table names, not user input.
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_membership_admin_is_owner_only_and_workspace_scoped(setup):
    work, workspace, other, users = setup
    service = MembershipService(work.engine)
    for actor in ("member", "observer", "outsider"):
        with pytest.raises(AccessDenied):
            service.list_members(principal(actor), workspace)
        with pytest.raises(AccessDenied):
            service.add_member(principal(actor), workspace, users["outsider"])
    with pytest.raises(AccessDenied):
        service.list_members(principal(), other)
    added = service.add_member(principal(), workspace, users["outsider"], role=Role.OBSERVER)
    assert (added.role, added.active, added.version) == (Role.OBSERVER, True, 1)
    with pytest.raises(MembershipConflict):
        service.add_member(principal(), workspace, users["outsider"])
    assert len(service.history(principal(), workspace)) == 1
    assert len(service.list_workspaces(principal("outsider"))) == 2
    with pytest.raises(MemberNotFound):
        service.add_member(principal(), workspace, uuid4())


def test_foreign_issuer_user_is_not_silently_granted_membership(setup):
    work, workspace, _, _ = setup
    service = MembershipService(work.engine)
    foreign = Principal("other-issuer", "foreign")
    service.create_workspace(foreign, WorkspaceCreate(name="Other issuer"))
    with pytest.raises(MemberNotFound):
        service.add_member(principal(), workspace, service.profile(foreign).id)


def test_last_owner_requires_explicit_transfer(setup):
    work, workspace, _, users = setup
    service = MembershipService(work.engine)
    for role, active in ((Role.MEMBER, True), (Role.OWNER, False)):
        with pytest.raises(LastOwnerConflict):
            service.change_member(
                principal(), workspace, users["owner"], role=role, active=active, expected_version=1
            )
    owner = next(
        m for m in service.list_members(principal(), workspace) if m.user_id == users["owner"]
    )
    assert (owner.role, owner.active, owner.version) == (Role.OWNER, True, 1)
    assert service.history(principal(), workspace) == []
    promoted = service.change_member(
        principal(), workspace, users["member"], role=Role.OWNER, active=True, expected_version=1
    )
    assert promoted.version == 2
    service.change_member(
        principal(), workspace, users["owner"], role=Role.MEMBER, active=True, expected_version=1
    )
    with pytest.raises(AccessDenied):
        service.list_members(principal(), workspace)
    assert len(service.history(principal("member"), workspace)) == 2


def test_concurrent_owner_departures_keep_one_active_owner(setup):
    work, workspace, _, users = setup
    service = MembershipService(work.engine)
    service.change_member(
        principal(), workspace, users["member"], role=Role.OWNER, active=True, expected_version=1
    )

    def leave(actor):
        try:
            service.change_member(
                principal(actor),
                workspace,
                users[actor],
                role=Role.OWNER,
                active=False,
                expected_version=1 if actor == "owner" else 2,
            )
            return "left"
        except LastOwnerConflict:
            return "last-owner"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(leave, ("owner", "member"))) == ["last-owner", "left"]
    with work.engine.begin() as connection:
        assert (
            connection.execute(
                text("""SELECT count(*) FROM memberships WHERE
            workspace_id=:workspace AND active=true AND role='owner'"""),
                {"workspace": workspace},
            ).scalar_one()
            == 1
        )


def test_stale_admin_update_rejected(setup):
    work, workspace, _, users = setup
    service = MembershipService(work.engine)
    service.change_member(
        principal(), workspace, users["member"], role=Role.OBSERVER, active=True, expected_version=1
    )
    with pytest.raises(MembershipConflict):
        service.change_member(
            principal(),
            workspace,
            users["member"],
            role=Role.OWNER,
            active=True,
            expected_version=1,
        )
    member = next(
        m for m in service.list_members(principal(), workspace) if m.user_id == users["member"]
    )
    assert (member.role, member.version) == (Role.OBSERVER, 2)
    assert len(service.history(principal(), workspace)) == 1


def test_removal_denies_existing_identity_and_preserves_private_work(setup):
    work, workspace, _, users = setup
    service = MembershipService(work.engine)
    item = work.create_work(principal("member"), workspace, Task(title="Private retained task"))
    service.change_member(
        principal(), workspace, users["member"], role=Role.MEMBER, active=False, expected_version=1
    )
    with pytest.raises(AccessDenied):
        work.get_work(principal("member"), workspace, item.id)
    assert service.list_workspaces(principal("member")) == []
    with pytest.raises(WorkNotFound):
        work.get_work(principal(), workspace, item.id)
    with pytest.raises(MembershipConflict):
        service.add_member(principal(), workspace, users["member"])
    service.change_member(
        principal(), workspace, users["member"], role=Role.MEMBER, active=True, expected_version=2
    )
    assert work.get_work(principal("member"), workspace, item.id).id == item.id


def test_membership_audit_failure_rolls_back_role_and_version(setup):
    work, workspace, _, users = setup
    service = MembershipService(work.engine)
    with work.engine.begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION fail_membership_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'membership audit failure'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER fail_membership_audit BEFORE INSERT ON workspace_events
            FOR EACH ROW EXECUTE FUNCTION fail_membership_audit()""")
        )
    with pytest.raises(DBAPIError, match="membership audit failure"):
        service.change_member(
            principal(),
            workspace,
            users["member"],
            role=Role.OBSERVER,
            active=True,
            expected_version=1,
        )
    member = next(
        m for m in service.list_members(principal(), workspace) if m.user_id == users["member"]
    )
    assert (member.role, member.version) == (Role.MEMBER, 1)


def test_workspace_audit_is_append_only(setup):
    work, workspace, _, users = setup
    service = MembershipService(work.engine)
    service.change_member(
        principal(), workspace, users["member"], role=Role.OBSERVER, active=True, expected_version=1
    )
    for statement in (
        "DELETE FROM workspace_events",
        "UPDATE workspace_events SET to_role='owner'",
        "TRUNCATE workspace_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            with work.engine.begin() as connection:
                connection.execute(text(statement))
    assert len(service.history(principal(), workspace)) == 1


def test_membership_migration_downgrade_preserves_existing_work(setup, pg, token_tools):
    from fastapi.testclient import TestClient
    from flowpilot_api.workspace_api import create_workspace_app

    work, workspace, _, _ = setup
    engine, config = pg
    item = work.create_work(principal(), workspace, Task(title="Existing work"))
    _, verifier, _ = token_tools
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0001_work_storage")
    assert "workspace_events" not in inspect(engine).get_table_names()
    assert "version" not in {
        column["name"] for column in inspect(engine).get_columns("memberships")
    }
    assert work.get_work(principal(), workspace, item.id).data.title == "Existing work"
    with TestClient(
        create_workspace_app(engine=engine, verifier=verifier), base_url="http://127.0.0.1"
    ) as client:
        assert client.get("/readyz").status_code == 503
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    assert work.get_work(principal(), workspace, item.id).id == item.id


def test_http_onboarding_without_manual_user_sql(workspace_client):
    client, _, _, _, sign = workspace_client
    headers = {"Authorization": "Bearer " + sign("newcomer")}
    assert client.get("/api/v2/me", headers=headers).status_code == 404
    assert client.get("/api/v2/workspaces", headers=headers).json() == []
    assert (
        client.post(
            "/api/v2/workspaces", headers=headers, json={"name": "My workspace", "role": "owner"}
        ).status_code
        == 422
    )
    response = client.post("/api/v2/workspaces", headers=headers, json={"name": " My workspace "})
    assert response.status_code == 201
    workspace = response.json()
    assert workspace["name"] == "My workspace" and workspace["role"] == "owner"
    profile = client.get("/api/v2/me", headers=headers).json()
    assert set(profile) == {"id"}
    assert client.get("/api/v2/workspaces", headers=headers).json() == [workspace]
    path = f"/api/v2/workspaces/{workspace['id']}/work"
    assert (
        client.post(
            path, headers=headers, json={"item": {"kind": "task", "title": "First task"}}
        ).status_code
        == 201
    )
    assert client.get(path, headers={"Authorization": "Bearer " + sign()}).status_code == 403


def test_http_membership_transfer_and_revocation(workspace_client):
    client, workspace, _, users, sign = workspace_client
    headers = {"Authorization": "Bearer " + sign()}
    member_headers = {"Authorization": "Bearer " + sign("member")}
    base = f"/api/v2/workspaces/{workspace}"
    assert client.get(base + "/members", headers=member_headers).status_code == 403
    assert client.get(base + "/membership-history", headers=member_headers).status_code == 403
    own_path = base + f"/members/{users['owner']}"
    command_body = {"role": "owner", "active": False, "expected_version": 1}
    assert client.patch(own_path, headers=headers, json=command_body).status_code == 409
    promote = base + f"/members/{users['member']}"
    assert (
        client.patch(
            promote, headers=headers, json={"role": "owner", "active": True, "expected_version": 1}
        ).status_code
        == 200
    )
    assert client.patch(own_path, headers=headers, json=command_body).status_code == 200
    assert client.get(base + "/work", headers=headers).status_code == 403
    assert client.get(base + "/members", headers=member_headers).status_code == 200
    assert len(client.get(base + "/membership-history", headers=member_headers).json()) == 2


def test_migration_rejects_ownerless_legacy_workspace(pg):
    engine, config = pg
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0001_work_storage")
        connection.execute(
            text("INSERT INTO workspaces (id,name) VALUES (:id,'Legacy ownerless')"),
            {"id": uuid4()},
        )
    with pytest.raises(RuntimeError, match="without active owners"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    assert "version" not in {
        column["name"] for column in inspect(engine).get_columns("memberships")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM workspaces")).scalar_one() == 1
