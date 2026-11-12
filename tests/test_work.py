import pytest
from flowpilot_api.work import Commitment, Task, WorkItem, can_change_work_status
from pydantic import TypeAdapter, ValidationError


def test_types_have_distinct_lifecycles():
    assert can_change_work_status(Commitment(title="Promise"), "confirmed")
    assert not can_change_work_status(Task(title="Task"), "confirmed")
    assert not can_change_work_status(Task(title="Task"), "completed")
    assert can_change_work_status(Task(title="Task", status="active"), "completed")
    assert not can_change_work_status(Task(title="Task", status="completed"), "active")


@pytest.mark.parametrize(
    "overrides",
    [
        {"ends_at": "2026-11-12T09:00:00Z"},
        {"starts_at": "2026-11-12T10:00:00"},
        {"time_zone": "MadeUp/Zone"},
        {"status": "completed"},
        {"workspace_id": "client-forged"},
    ],
)
def test_invalid_events(overrides):
    payload = dict(
        kind="event",
        title="Synthetic meeting",
        starts_at="2026-11-12T10:00:00Z",
        ends_at="2026-11-12T11:00:00Z",
        time_zone="America/Los_Angeles",
    )
    payload.update(overrides)
    with pytest.raises(ValidationError):
        TypeAdapter(WorkItem).validate_python(payload)


def test_event_contract():
    item = TypeAdapter(WorkItem).validate_python(
        dict(
            kind="event",
            title=" Synthetic meeting ",
            starts_at="2026-11-12T10:00:00Z",
            ends_at="2026-11-12T11:00:00Z",
            time_zone="America/Los_Angeles",
        )
    )
    assert item.title == "Synthetic meeting"
    assert can_change_work_status(item, "canceled")


def test_postgres_incompatible_nul_rejected_before_storage():
    from flowpilot_api.work_service import ManualSource

    for factory in (
        lambda: Task(title="bad\x00title"),
        lambda: Task(title="Task", description="bad\x00description"),
        lambda: ManualSource(reference="ref", summary="Summary", excerpt="bad\x00excerpt"),
    ):
        with pytest.raises(ValidationError, match="NUL"):
            factory()
