"""Validated request and response shapes for the HTTP API."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from flowpilot_api.domain import CommitmentStatus


class CommitmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=4000)
    owner_name: str | None = Field(default=None, max_length=160)
    due_date: date | None = None
    evidence_excerpt: str | None = Field(default=None, max_length=2000)

    @field_validator("title", "owner_name", "details", "evidence_excerpt")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Text fields cannot contain only whitespace")
        return cleaned


class CommitmentTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: CommitmentStatus
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Reason cannot contain only whitespace")
        return cleaned


class CommitmentOut(BaseModel):
    id: UUID
    title: str
    details: str | None
    owner_name: str | None
    due_date: date | None
    evidence_excerpt: str | None
    status: CommitmentStatus
    version: int
    created_at: datetime
    updated_at: datetime


class CommitmentEventOut(BaseModel):
    id: int
    commitment_id: UUID
    event_type: str
    actor: str
    from_status: CommitmentStatus | None
    to_status: CommitmentStatus | None
    reason: str | None
    created_at: datetime


class CommitmentListOut(BaseModel):
    items: list[CommitmentOut]
    count: int


class FocusItem(BaseModel):
    id: UUID
    title: str
    owner_name: str | None
    due_date: date | None
    status: CommitmentStatus
    version: int


class FocusOut(BaseModel):
    items: list[FocusItem]
    due_count: int
