"""Authorized PostgreSQL commands for synthetic work.

Only a verified authentication adapter may construct Principal for an API.
No request is permitted to assert its own issuer/subject or role.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator
from sqlalchemy import Connection, Engine, text

from flowpilot_api.access import (
    AccessDenied,
    EvidenceVisibility,
    Membership,
    Visibility,
    require_work_access,
    visible_evidence,
)
from flowpilot_api.member_context import resolve_member
from flowpilot_api.repository import InvalidTransition, VersionConflict
from flowpilot_api.work import Commitment, Event, Task, WorkItem, can_change_work_status


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

    def share_work(
        self, principal: Principal, workspace_id: UUID, work_id: UUID, *, expected_version: int
    ) -> StoredWork:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id, write=True)
            current = self._work(connection, member, work_id, write=True)
            if current.creator_id != member.user_id:
                raise AccessDenied
            if current.version != expected_version:
                raise VersionConflict
            if current.visibility != Visibility.PRIVATE:
                raise InvalidTransition("Work is already shared")
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

    def evidence(self, principal: Principal, workspace_id: UUID, work_id: UUID) -> list[dict]:
        with self.engine.begin() as connection:
            member = self._member(connection, principal, workspace_id)
            self._work(connection, member, work_id)
            rows = connection.execute(
                text("""SELECT e.visibility, s.owner_id, s.summary, s.excerpt
                FROM evidence_links e JOIN source_items s ON s.workspace_id = e.workspace_id
                    AND s.id = e.source_id AND s.owner_id = e.source_owner_id
                WHERE e.workspace_id = :workspace AND e.work_id = :work
                ORDER BY e.source_id"""),
                {"workspace": workspace_id, "work": work_id},
            ).mappings()
            result = []
            for row in rows:
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
