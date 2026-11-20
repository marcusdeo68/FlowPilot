"""Typed canonical-work contracts. Not yet exposed by the local commitment API."""

import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

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


class EventSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    time_zone: str = Field(min_length=1, max_length=100)
    starts_at: datetime
    ends_at: datetime

    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA time zone") from exc
        return value

    @model_validator(mode="after")
    def valid_interval(self) -> "EventSchedule":
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError("Event timestamps must include an offset")
        try:
            starts_at = self.starts_at.astimezone(UTC)
            ends_at = self.ends_at.astimezone(UTC)
        except OverflowError as exc:
            raise ValueError("Time is outside the supported date range") from exc
        if ends_at <= starts_at:
            raise ValueError("Event end must follow start")
        return self


class Event(WorkBase, EventSchedule):
    kind: Literal["event"] = "event"
    status: Literal["scheduled", "canceled"] = "scheduled"


class LocalEventSchedule(EventSchedule):
    """Resolve wall times without guessing during daylight-saving transitions."""

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def resolve_local_time(cls, value: object, info: ValidationInfo) -> datetime:
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?",
            value,
        ):
            raise ValueError("Use a local date and time without an offset")
        local = datetime.fromisoformat(value)
        if "time_zone" not in info.data:
            raise ValueError("Choose a valid IANA time zone")
        zone = ZoneInfo(info.data["time_zone"])
        candidates = set()
        try:
            for fold in (0, 1):
                instant = local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
                if instant.astimezone(zone).replace(tzinfo=None) == local:
                    candidates.add(instant)
        except OverflowError as exc:
            raise ValueError("Time is outside the supported date range") from exc
        if not candidates:
            raise ValueError("This local time does not exist in the selected zone")
        if len(candidates) > 1:
            raise ValueError("This local time occurs twice. Choose another time or enter it in UTC")
        return candidates.pop()


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
