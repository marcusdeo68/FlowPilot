"""Typed canonical-work contracts. Not yet exposed by the local commitment API."""

from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flowpilot_api.domain import CommitmentStatus


class WorkDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(max_length=4000)

    @field_validator("title", "description")
    @classmethod
    def meaningful_text(cls, value: str | None) -> str | None:
        if value is not None:
            if "\x00" in value:
                raise ValueError("Text cannot contain NUL characters")
            value = value.strip()
            if not value:
                raise ValueError("Text must not be blank")
        return value


class WorkBase(WorkDetails):
    description: str | None = Field(default=None, max_length=4000)


class Commitment(WorkBase):
    kind: Literal["commitment"] = "commitment"
    status: CommitmentStatus = CommitmentStatus.DETECTED
    due_date: date | None = None


class Task(WorkBase):
    kind: Literal["task"] = "task"
    status: Literal["open", "active", "blocked", "completed", "canceled"] = "open"
    due_date: date | None = None


class TaskDetails(WorkDetails):
    """Complete editable fields. Send null explicitly to clear a field."""

    due_date: date | None

    @field_validator("due_date", mode="before")
    @classmethod
    def calendar_date(cls, value: object) -> date | None:
        if value is None or type(value) is date:
            return value
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                pass
            else:
                if parsed.isoformat() == value:
                    return parsed
        raise ValueError("Due date must be a YYYY-MM-DD calendar date or null")


class Event(WorkBase):
    kind: Literal["event"] = "event"
    status: Literal["scheduled", "canceled"] = "scheduled"
    starts_at: datetime
    ends_at: datetime
    time_zone: str = Field(min_length=1, max_length=100)

    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA time zone") from exc
        return value

    @model_validator(mode="after")
    def valid_interval(self) -> "Event":
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError("Event timestamps must include an offset")
        if self.ends_at <= self.starts_at:
            raise ValueError("Event end must follow start")
        return self


WorkItem = Annotated[Commitment | Task | Event, Field(discriminator="kind")]

TASK_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "open": ("active", "canceled"),
    "active": ("completed", "blocked", "canceled"),
    "blocked": ("active", "canceled"),
}


def can_change_work_status(item: Commitment | Task | Event, target: str) -> bool:
    if isinstance(item, Commitment):
        from flowpilot_api.domain import can_transition

        try:
            return can_transition(item.status, CommitmentStatus(target))
        except ValueError:
            return False
    if isinstance(item, Task):
        return target in TASK_TRANSITIONS.get(item.status, ())
    return item.status == "scheduled" and target == "canceled"
