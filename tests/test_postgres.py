"""Real PostgreSQL integration checks. Each test owns a random disposable schema."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from flowpilot_api.access import AccessDenied, EvidenceVisibility, Visibility
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
