"""Private manual-source review. No connector, inference or action execution."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, Engine, text

from flowpilot_api.access import Membership, Visibility
from flowpilot_api.member_context import resolve_member
from flowpilot_api.work import Task
from flowpilot_api.work_service import Principal, SourceNotFound, WorkService

Decision = Literal["accept", "dismiss"]
State = Literal["pending_review", "accepted", "dismissed"]


class ProposalNotFound(Exception):
    pass


class ReviewConflict(Exception):
    """Reload the proposal before deciding again."""


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_version: int = Field(ge=1, strict=True)


class Correction(Revision):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None

    @field_validator("title")
    @classmethod
    def canonical_title(cls, value: str) -> str:
        return Task(title=value).title


class Review(Revision):
    decision: Decision


@dataclass(frozen=True)
class Proposal:
    id: UUID
    source_id: UUID
    title: str
    due_date: date | None
    state: State
    version: int
    work_id: UUID | None
    updated_at: datetime


def member_for(c: Connection, p: Principal, ws: UUID, *, write: bool) -> Membership:
    return resolve_member(c, issuer=p.issuer, subject=p.subject, workspace_id=ws, write=write)


def scope(member: Membership) -> dict:
    return {"ws": member.workspace_id, "owner": member.user_id}


def view(row) -> Proposal:
    return Proposal(**{field: row[field] for field in Proposal.__dataclass_fields__})


def record(c: Connection, member: Membership, proposal: Proposal, operation: str) -> None:
    c.execute(
        text("""INSERT INTO proposal_events(workspace_id, proposal_id, actor_id, version, operation)
            VALUES (:ws, :id, :owner, :version, :operation)"""),
        {**scope(member), "id": proposal.id, "version": proposal.version, "operation": operation},
    )


def lookup(c: Connection, member: Membership, pid: UUID, *, lock: bool = False) -> Proposal:
    query = "SELECT * FROM task_proposals WHERE workspace_id=:ws AND owner_id=:owner AND id=:id"
    row = (
        c.execute(text(query + (" FOR UPDATE" if lock else "")), {**scope(member), "id": pid})
        .mappings()
        .first()
    )
    if row is None:
        raise ProposalNotFound
    return view(row)


def require_pending(proposal: Proposal, version: int) -> None:
    if proposal.version != version or proposal.state != "pending_review":
        raise ReviewConflict


class ProposalService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.work = WorkService(engine)

    def suggest(self, p: Principal, ws: UUID, source: UUID) -> Proposal:
        with self.engine.begin() as c:
            member = member_for(c, p, ws, write=True)
            args = {**scope(member), "source": source, "id": uuid4()}
            summary = c.execute(
                text(
                    "SELECT summary FROM source_items WHERE workspace_id=:ws AND owner_id=:owner AND id=:source"
                ),
                args,
            ).scalar_one_or_none()
            if summary is None:
                raise SourceNotFound
            # A bounded literal title, never an instruction or an inferred deadline.
            row = (
                c.execute(
                    text("""INSERT INTO task_proposals(id, workspace_id, source_id, owner_id, title)
                VALUES (:id, :ws, :source, :owner, :title)
                ON CONFLICT (workspace_id, source_id) DO NOTHING RETURNING *"""),
                    {**args, "title": Task(title=summary[:200]).title},
                )
                .mappings()
                .first()
            )
            if row is None:
                existing = (
                    c.execute(
                        text("""SELECT * FROM task_proposals WHERE workspace_id=:ws
                    AND owner_id=:owner AND source_id=:source"""),
                        args,
                    )
                    .mappings()
                    .one()
                )
                return view(existing)
            proposal = view(row)
            record(c, member, proposal, "suggested")
            return proposal

    def get(self, p: Principal, ws: UUID, pid: UUID) -> Proposal:
        with self.engine.begin() as c:
            return lookup(c, member_for(c, p, ws, write=False), pid)

    def queue(self, p: Principal, ws: UUID, limit: int) -> list[Proposal]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as c:
            member = member_for(c, p, ws, write=False)
            rows = c.execute(
                text("""SELECT * FROM task_proposals WHERE workspace_id=:ws
                AND owner_id=:owner AND state='pending_review' ORDER BY updated_at DESC,id LIMIT :limit"""),
                {**scope(member), "limit": limit},
            ).mappings()
            return [view(row) for row in rows]

    def correct(self, p: Principal, ws: UUID, pid: UUID, edit: Correction) -> Proposal:
        with self.engine.begin() as c:
            member = member_for(c, p, ws, write=True)
            current = lookup(c, member, pid, lock=True)
            require_pending(current, edit.expected_version)
            if (current.title, current.due_date) == (edit.title, edit.due_date):
                raise ReviewConflict
            row = (
                c.execute(
                    text("""UPDATE task_proposals SET title=:title, due_date=:due,
                version=version+1, updated_at=now() WHERE workspace_id=:ws AND owner_id=:owner
                AND id=:id RETURNING *"""),
                    {**scope(member), "id": pid, "title": edit.title, "due": edit.due_date},
                )
                .mappings()
                .one()
            )
            updated = view(row)
            record(c, member, updated, "corrected")
            return updated

    def review(self, p: Principal, ws: UUID, pid: UUID, review: Review) -> Proposal:
        with self.engine.begin() as c:
            member = member_for(c, p, ws, write=True)
            current = lookup(c, member, pid, lock=True)
            require_pending(current, review.expected_version)
            work_id = None
            state = "dismissed"
            if review.decision == "accept":
                item = self.work.insert_authorized_work(
                    c,
                    member,
                    Task(title=current.title, due_date=current.due_date),
                    visibility=Visibility.PRIVATE,
                )
                c.execute(
                    text("""INSERT INTO evidence_links
                    (workspace_id, work_id, source_id, source_owner_id, visibility)
                    VALUES (:ws, :work, :source, :owner, 'private')"""),
                    {**scope(member), "work": item.id, "source": current.source_id},
                )
                work_id, state = item.id, "accepted"
            row = (
                c.execute(
                    text("""UPDATE task_proposals SET state=:state, work_id=:work,
                version=version+1, updated_at=now() WHERE workspace_id=:ws AND owner_id=:owner
                AND id=:id RETURNING *"""),
                    {**scope(member), "id": pid, "state": state, "work": work_id},
                )
                .mappings()
                .one()
            )
            updated = view(row)
            record(c, member, updated, state)
            return updated
