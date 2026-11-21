"""Authorized PostgreSQL commands for synthetic work.

Only a verified authentication adapter may construct Principal for an API.
No request is permitted to assert its own issuer/subject or role.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator
from sqlalchemy import Connection, Engine, bindparam, text

from flowpilot_api.access import (
    AccessDenied,
    EvidenceVisibility,
    Membership,
    Visibility,
    require_work_access,
    shared_evidence,
    visible_evidence,
)
from flowpilot_api.member_context import resolve_member
from flowpilot_api.repository import InvalidTransition, VersionConflict
from flowpilot_api.work import (
    TASK_TRANSITIONS,
    Commitment,
    Event,
    EventScheduleChange,
    InvalidEventSchedule,
    Task,
    TaskDetails,
    WorkDetails,
    WorkItem,
    can_change_work_status,
)


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str


class WorkNotFound(Exception):
    """Absent and inaccessible objects deliberately have the same result."""


class SourceNotFound(Exception):
    pass


class ManualSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reference: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(min_length=1, max_length=2000)

    @field_validator("reference", "summary", "excerpt")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Text cannot contain NUL characters")
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value.strip()


@dataclass(frozen=True)
class StoredWork:
    id: UUID
    workspace_id: UUID
    creator_id: UUID
    owner_id: UUID
    visibility: Visibility
    version: int
    data: Commitment | Task | Event
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkPage:
    items: list[StoredWork]
    next_after: UUID | None


@dataclass(frozen=True)
class DueTasks:
    items: list[StoredWork]
    has_more: bool


@dataclass(frozen=True)
class UpcomingEvents:
    items: list[StoredWork]
    has_more: bool


@dataclass(frozen=True)
class SharePreview:
    item: StoredWork
    evidence: list[dict[str, str]]


@dataclass(frozen=True)
class TaskReminder:
    id: UUID
    title: str
    due_date: date


@dataclass(frozen=True)
class EventReminder:
    id: UUID
    title: str
    starts_at: datetime


@dataclass(frozen=True)
class ReminderCandidates:
    tasks: list[TaskReminder]
    events: list[EventReminder]
    has_more: bool


ReminderCategory = Literal["tasks", "events", "both"]


class _StoredWorkPayload(RootModel[WorkItem]):
    """Validate a database projection against the same tagged union used by the API."""


def _stored(row) -> StoredWork:
    fields = {
        "kind": row["kind"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
    }
    if row["kind"] == "event":
        fields.update({key: row[key] for key in ("starts_at", "ends_at", "time_zone")})
    else:
        fields["due_date"] = row["due_date"]
    return StoredWork(
        id=row["id"],
        workspace_id=row["workspace_id"],
        creator_id=row["creator_id"],
        owner_id=row["owner_id"],
        visibility=Visibility(row["visibility"]),
        version=row["version"],
        data=_StoredWorkPayload.model_validate(fields).root,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class WorkService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _member(
        self,
        connection: Connection,
        principal: Principal,
        workspace_id: UUID,
        *,
        write: bool = False,
    ) -> Membership:
        return resolve_member(
            connection,
            issuer=principal.issuer,
            subject=principal.subject,
            workspace_id=workspace_id,
            write=write,
        )

    def _work(
        self, connection: Connection, member: Membership, work_id: UUID, *, write: bool = False
    ) -> StoredWork:
        query = """SELECT * FROM work_items WHERE workspace_id = :workspace AND id = :id
                   AND (visibility = 'workspace' OR creator_id = :user)"""
        if write:
            query += " FOR UPDATE"
        row = (
            connection.execute(
                text(query),
                {"workspace": member.workspace_id, "id": work_id, "user": member.user_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkNotFound
        item = _stored(row)
        require_work_access(
            member, item.workspace_id, item.creator_id, item.visibility, write=write
        )
        return item

    def _audit(self, connection, member, item, operation, from_status=None):
        connection.execute(
            text("""
            INSERT INTO audit_events
                (id, workspace_id, work_id, actor_id, operation, from_status, to_status, version)
            VALUES (:id, :workspace, :work, :actor, :operation, :before, :after, :version)
        """),
            {
                "id": uuid4(),
                "workspace": member.workspace_id,
                "work": item.id,
                "actor": member.user_id,
                "operation": operation,
                "before": from_status,
                "after": item.data.status,
                "version": item.version,
            },
        )

    def create_work(
        self,
        principal: Principal,
        workspace_id: UUID,
        data: Commitment | Task | Event,
        *,
        visibility: Visibility = Visibility.PRIVATE,
    ) -> StoredWork:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            return self.insert_authorized_work(connection, member, data, visibility=visibility)

    def insert_authorized_work(
        self,
        connection: Connection,
        member: Membership,
        data: Commitment | Task | Event,
        *,
        visibility: Visibility,
    ) -> StoredWork:
        """Insert and audit using the caller's already-authorized transaction."""
        if visibility not in (Visibility.PRIVATE, Visibility.WORKSPACE):
            raise ValueError("Invalid visibility")
        initial = {"task": "open", "commitment": "detected", "event": "scheduled"}
        if data.status != initial[data.kind]:
            raise InvalidTransition("Creation requires the initial state")
        workspace_id = member.workspace_id
        values = {
            "id": uuid4(),
            "workspace": workspace_id,
            "user": member.user_id,
            "kind": data.kind,
            "title": data.title,
            "description": data.description,
            "status": data.status,
            "visibility": visibility,
            "due_date": getattr(data, "due_date", None),
            "starts_at": getattr(data, "starts_at", None),
            "ends_at": getattr(data, "ends_at", None),
            "time_zone": getattr(data, "time_zone", None),
        }
        row = (
            connection.execute(
                text("""
            INSERT INTO work_items (id, workspace_id, creator_id, owner_id, kind, title,
                description, status, visibility, due_date, starts_at, ends_at, time_zone)
            VALUES (:id, :workspace, :user, :user, :kind, :title, :description, :status,
                :visibility, :due_date, :starts_at, :ends_at, :time_zone) RETURNING *
        """),
                values,
            )
            .mappings()
            .one()
        )
        item = _stored(row)
        self._audit(connection, member, item, "created")
        return item

    def get_work(self, principal: Principal, workspace_id: UUID, work_id: UUID) -> StoredWork:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            return self._work(connection, member, work_id)

    def list_work(
        self, principal: Principal, workspace_id: UUID, *, limit: int = 50
    ) -> list[StoredWork]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            rows = connection.execute(
                text("""SELECT * FROM work_items
                WHERE workspace_id = :workspace AND (visibility = 'workspace' OR creator_id = :user)
                ORDER BY updated_at DESC, id LIMIT :limit"""),
                {"workspace": workspace_id, "user": member.user_id, "limit": limit},
            ).mappings()
            return [_stored(row) for row in rows]

    def list_work_page(
        self,
        principal: Principal,
        workspace_id: UUID,
        *,
        limit: int = 50,
        after: UUID | None = None,
        kind: Literal["event"] | None = None,
        visibility: Visibility | None = None,
    ) -> WorkPage:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            params = {"workspace": workspace_id, "user": member.user_id, "limit": limit + 1}
            boundary = " AND kind = 'event'" if kind == "event" else ""
            if visibility is not None:
                boundary += " AND visibility = :visibility"
                params["visibility"] = visibility
            if after is not None:
                pivot = self._work(connection, member, after)
                if (kind is not None and pivot.data.kind != kind) or (
                    visibility is not None and pivot.visibility != visibility
                ):
                    raise WorkNotFound
                boundary += " AND (created_at, id) < (:created, :after)"
                params.update(created=pivot.created_at, after=pivot.id)
            rows = (
                connection.execute(
                    text(
                        """SELECT * FROM work_items WHERE workspace_id=:workspace
                    AND (visibility='workspace' OR creator_id=:user)"""
                        + boundary
                        + " ORDER BY created_at DESC, id DESC LIMIT :limit"
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            items = [_stored(row) for row in rows[:limit]]
            return WorkPage(items, items[-1].id if len(rows) > limit else None)

    def list_due_tasks(
        self, principal: Principal, workspace_id: UUID, *, limit: int = 20
    ) -> DueTasks:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            rows = (
                connection.execute(
                    text("""SELECT * FROM work_items WHERE workspace_id = :workspace
                        AND (visibility = 'workspace' OR creator_id = :user)
                        AND kind = 'task' AND due_date IS NOT NULL AND status IN :unfinished
                        ORDER BY due_date ASC, created_at DESC, id DESC LIMIT :limit""").bindparams(
                        bindparam("unfinished", expanding=True)
                    ),
                    {
                        "workspace": workspace_id,
                        "user": member.user_id,
                        "unfinished": tuple(TASK_TRANSITIONS),
                        "limit": limit + 1,
                    },
                )
                .mappings()
                .all()
            )
            return DueTasks([_stored(row) for row in rows[:limit]], len(rows) > limit)

    def list_upcoming_events(
        self, principal: Principal, workspace_id: UUID, *, limit: int = 5
    ) -> UpcomingEvents:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            rows = (
                connection.execute(
                    text("""SELECT * FROM work_items WHERE workspace_id = :workspace
                        AND (visibility = 'workspace' OR creator_id = :user)
                        AND kind = 'event' AND status = 'scheduled'
                        AND ends_at > CURRENT_TIMESTAMP
                        AND starts_at < CURRENT_TIMESTAMP + INTERVAL '168 hours'
                        ORDER BY starts_at ASC, id ASC LIMIT :limit"""),
                    {"workspace": workspace_id, "user": member.user_id, "limit": limit + 1},
                )
                .mappings()
                .all()
            )
            return UpcomingEvents([_stored(row) for row in rows[:limit]], len(rows) > limit)

    def reminder_candidates(
        self,
        principal: Principal,
        workspace_id: UUID,
        *,
        local_date: date,
        category: ReminderCategory = "both",
        event_lead_minutes: int = 15,
    ) -> ReminderCandidates:
        if not 5 <= event_lead_minutes <= 60:
            raise ValueError("Event lead time must be between 5 and 60 minutes")
        limit = 5
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            params = {"workspace": workspace_id, "user": member.user_id, "limit": limit + 1}
            tasks = (
                []
                if category == "events"
                else connection.execute(
                    text("""SELECT id, title, due_date FROM work_items
                    WHERE workspace_id = :workspace AND (visibility = 'workspace' OR creator_id = :user)
                    AND kind = 'task' AND status IN :unfinished AND due_date = :local_date
                    ORDER BY created_at, id LIMIT :limit""").bindparams(
                        bindparam("unfinished", expanding=True)
                    ),
                    {**params, "local_date": local_date, "unfinished": tuple(TASK_TRANSITIONS)},
                ).all()
            )
            events = (
                []
                if category == "tasks"
                else connection.execute(
                    text("""SELECT id, title, starts_at FROM work_items
                    WHERE workspace_id = :workspace AND (visibility = 'workspace' OR creator_id = :user)
                    AND kind = 'event' AND status = 'scheduled'
                    AND starts_at > statement_timestamp()
                    AND starts_at <= statement_timestamp() + make_interval(mins => :event_lead_minutes)
                    ORDER BY starts_at, id LIMIT :limit"""),
                    {**params, "event_lead_minutes": event_lead_minutes},
                ).all()
            )
            return ReminderCandidates(
                [TaskReminder(row.id, row.title, row.due_date) for row in tasks[:limit]],
                [
                    EventReminder(row.id, row.title, row.starts_at.astimezone(UTC))
                    for row in events[:limit]
                ],
                len(tasks) > limit or len(events) > limit,
            )

    def edit_task(
        self,
        principal: Principal,
        workspace_id: UUID,
        work_id: UUID,
        *,
        details: TaskDetails,
        expected_version: int,
    ) -> StoredWork:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            current = self._work(connection, member, work_id, write=True)
            if not isinstance(current.data, Task):
                raise WorkNotFound
            if current.creator_id != member.user_id:
                raise AccessDenied
            if current.version != expected_version:
                raise VersionConflict
            if (
                current.data.title == details.title
                and current.data.description == details.description
                and current.data.due_date == details.due_date
            ):
                return current
            row = (
                connection.execute(
                    text("""UPDATE work_items SET title = :title, description = :description,
                    due_date = :due_date, version = version + 1, updated_at = now()
                    WHERE workspace_id = :workspace AND id = :id AND version = :version
                    RETURNING *"""),
                    {
                        "title": details.title,
                        "description": details.description,
                        "due_date": details.due_date,
                        "workspace": workspace_id,
                        "id": work_id,
                        "version": expected_version,
                    },
                )
                .mappings()
                .one()
            )
            updated = _stored(row)
            self._audit(connection, member, updated, "details_changed")
            return updated

    def edit_event(
        self,
        principal: Principal,
        workspace_id: UUID,
        work_id: UUID,
        *,
        details: WorkDetails,
        schedule: EventScheduleChange | None,
        expected_version: int,
    ) -> StoredWork:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            current = self._work(connection, member, work_id, write=True)
            if not isinstance(current.data, Event):
                raise WorkNotFound
            if current.creator_id != member.user_id:
                raise AccessDenied
            if current.version != expected_version:
                raise VersionConflict
            if current.data.status != "scheduled":
                raise InvalidTransition
            starts_at = current.data.starts_at.astimezone(UTC)
            ends_at = current.data.ends_at.astimezone(UTC)
            time_zone = current.data.time_zone
            previous = {
                "title": current.data.title,
                "description": current.data.description,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "time_zone": time_zone,
            }
            if schedule is not None:
                if schedule.time_zone != time_zone and (
                    schedule.starts_at is None or schedule.ends_at is None
                ):
                    raise InvalidEventSchedule("Provide both times when changing time zone")
                starts_at = schedule.starts_at or starts_at
                ends_at = schedule.ends_at or ends_at
                time_zone = schedule.time_zone
                if ends_at <= starts_at:
                    raise InvalidEventSchedule("Event end must follow start")
            changes = {
                "title": details.title,
                "description": details.description,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "time_zone": time_zone,
            }
            if changes == previous:
                return current
            row = (
                connection.execute(
                    text("""UPDATE work_items SET title = :title, description = :description,
                    starts_at = :starts_at, ends_at = :ends_at, time_zone = :time_zone,
                    version = version + 1, updated_at = now()
                    WHERE workspace_id = :workspace AND id = :id AND version = :version
                    RETURNING *"""),
                    {
                        **changes,
                        "workspace": workspace_id,
                        "id": work_id,
                        "version": expected_version,
                    },
                )
                .mappings()
                .one()
            )
            updated = _stored(row)
            self._audit(connection, member, updated, "details_changed")
            return updated

    def transition(
        self,
        principal: Principal,
        workspace_id: UUID,
        work_id: UUID,
        *,
        target: str,
        expected_version: int,
    ) -> StoredWork:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            current = self._work(connection, member, work_id, write=True)
            if current.version != expected_version:
                raise VersionConflict
            if not can_change_work_status(current.data, target):
                raise InvalidTransition
            row = (
                connection.execute(
                    text("""UPDATE work_items SET status = :status,
                version = version + 1, updated_at = now()
                WHERE workspace_id = :workspace AND id = :id AND version = :version RETURNING *"""),
                    {
                        "status": target,
                        "workspace": workspace_id,
                        "id": work_id,
                        "version": expected_version,
                    },
                )
                .mappings()
                .one()
            )
            updated = _stored(row)
            self._audit(connection, member, updated, "status_changed", current.data.status)
            return updated

    def _shareable_work(
        self,
        connection: Connection,
        member: Membership,
        work_id: UUID,
        *,
        expected_version: int | None = None,
    ) -> StoredWork:
        item = self._work(connection, member, work_id, write=True)
        if item.creator_id != member.user_id:
            raise AccessDenied
        if expected_version is not None and item.version != expected_version:
            raise VersionConflict
        if item.visibility != Visibility.PRIVATE:
            raise InvalidTransition("Work is already shared")
        return item

    def share_preview(
        self, principal: Principal, workspace_id: UUID, work_id: UUID
    ) -> SharePreview:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            # Evidence linking locks this same row before changing links and its version.
            item = self._shareable_work(connection, member, work_id)
            evidence = []
            for row in self._evidence_rows(connection, workspace_id, work_id):
                fields = shared_evidence(
                    EvidenceVisibility(row["visibility"]),
                    summary=row["summary"],
                    excerpt=row["excerpt"],
                )
                if fields:
                    evidence.append(fields)
            return SharePreview(item, evidence)

    def share_work(
        self, principal: Principal, workspace_id: UUID, work_id: UUID, *, expected_version: int
    ) -> StoredWork:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            self._shareable_work(connection, member, work_id, expected_version=expected_version)
            row = (
                connection.execute(
                    text("""UPDATE work_items SET visibility = 'workspace',
                version = version + 1, updated_at = now()
                WHERE workspace_id = :workspace AND id = :id RETURNING *"""),
                    {"workspace": workspace_id, "id": work_id},
                )
                .mappings()
                .one()
            )
            updated = _stored(row)
            self._audit(connection, member, updated, "shared")
            return updated

    def create_source(self, principal: Principal, workspace_id: UUID, data: ManualSource) -> UUID:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            source_id = uuid4()
            connection.execute(
                text("""INSERT INTO source_items
                (id, workspace_id, owner_id, reference, summary, excerpt)
                VALUES (:id, :workspace, :owner, :reference, :summary, :excerpt)"""),
                {
                    "id": source_id,
                    "workspace": workspace_id,
                    "owner": member.user_id,
                    **data.model_dump(),
                },
            )
            connection.execute(
                text("""INSERT INTO audit_events
                (id, workspace_id, source_id, actor_id, operation, version)
                VALUES (:id, :workspace, :source, :actor, 'source_created', 1)"""),
                {
                    "id": uuid4(),
                    "workspace": workspace_id,
                    "source": source_id,
                    "actor": member.user_id,
                },
            )
            return source_id

    def get_source(self, principal: Principal, workspace_id: UUID, source_id: UUID) -> ManualSource:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            row = (
                connection.execute(
                    text("""SELECT reference, summary, excerpt FROM source_items
                WHERE workspace_id = :workspace AND id = :id AND owner_id = :user"""),
                    {"workspace": workspace_id, "id": source_id, "user": member.user_id},
                )
                .mappings()
                .first()
            )
            if row is None:
                raise SourceNotFound
            return ManualSource.model_validate(dict(row))

    def link_evidence(
        self,
        principal: Principal,
        workspace_id: UUID,
        work_id: UUID,
        source_id: UUID,
        *,
        visibility: EvidenceVisibility,
        expected_version: int,
    ) -> StoredWork:
        if visibility not in tuple(EvidenceVisibility):
            raise ValueError("Invalid evidence visibility")
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            current = self._work(connection, member, work_id, write=True)
            if current.version != expected_version:
                raise VersionConflict
            source = connection.execute(
                text("""SELECT id FROM source_items
                WHERE workspace_id = :workspace AND id = :id AND owner_id = :user"""),
                {"workspace": workspace_id, "id": source_id, "user": member.user_id},
            ).first()
            if source is None:
                raise SourceNotFound
            shared = visibility != EvidenceVisibility.PRIVATE
            connection.execute(
                text("""INSERT INTO evidence_links
                (workspace_id, work_id, source_id, source_owner_id, visibility, shared_by, shared_at)
                VALUES (:workspace, :work, :source, :owner, :visibility, :actor,
                        CASE WHEN :shared THEN now() ELSE NULL END)"""),
                {
                    "workspace": workspace_id,
                    "work": work_id,
                    "source": source_id,
                    "owner": member.user_id,
                    "visibility": visibility,
                    "shared": shared,
                    "actor": member.user_id if shared else None,
                },
            )
            row = (
                connection.execute(
                    text("""UPDATE work_items SET version = version + 1,
                updated_at = now() WHERE workspace_id = :workspace AND id = :id RETURNING *"""),
                    {"workspace": workspace_id, "id": work_id},
                )
                .mappings()
                .one()
            )
            updated = _stored(row)
            self._audit(connection, member, updated, "evidence_linked")
            return updated

    def _evidence_rows(self, connection: Connection, workspace_id: UUID, work_id: UUID):
        return connection.execute(
            text("""SELECT e.visibility, s.owner_id, s.summary, s.excerpt
                FROM evidence_links e JOIN source_items s ON s.workspace_id = e.workspace_id
                    AND s.id = e.source_id AND s.owner_id = e.source_owner_id
                WHERE e.workspace_id = :workspace AND e.work_id = :work
                ORDER BY e.source_id"""),
            {"workspace": workspace_id, "work": work_id},
        ).mappings()

    def evidence(self, principal: Principal, workspace_id: UUID, work_id: UUID) -> list[dict]:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            self._work(connection, member, work_id)
            result = []
            for row in self._evidence_rows(connection, workspace_id, work_id):
                projected = visible_evidence(
                    member,
                    workspace_id,
                    row["owner_id"],
                    EvidenceVisibility(row["visibility"]),
                    summary=row["summary"],
                    excerpt=row["excerpt"],
                )
                if projected:
                    result.append(projected)
            return result

    def history(self, principal: Principal, workspace_id: UUID, work_id: UUID) -> list[dict]:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            self._work(connection, member, work_id)
            rows = connection.execute(
                text("""SELECT operation, actor_id, from_status,
                to_status, version, created_at FROM audit_events
                WHERE workspace_id = :workspace AND work_id = :work ORDER BY version, created_at, id"""),
                {"workspace": workspace_id, "work": work_id},
            ).mappings()
            return [dict(row) for row in rows]
