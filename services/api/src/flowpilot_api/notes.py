"""Private note storage behind verified identity and active workspace membership."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, Engine, text

from flowpilot_api.member_context import resolve_member
from flowpilot_api.repository import InvalidTransition, VersionConflict
from flowpilot_api.work_service import Principal

_NOTE_FIELDS = "id, body, archived, version, created_at, updated_at"
_OWNER_SCOPE = "workspace_id = :workspace AND owner_id = :owner"


class NoteNotFound(Exception):
    pass


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def has_text(cls, body: str) -> str:
        if not body.strip() or "\x00" in body:
            raise ValueError("Enter note text without NUL characters")
        try:
            body.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Enter valid Unicode text") from exc
        return body


class NoteEdit(NoteBody):
    expected_version: int = Field(ge=1, strict=True)


class NoteState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_version: int = Field(ge=1, strict=True)
    archived: bool = Field(strict=True)


@dataclass(frozen=True)
class Note:
    id: UUID
    body: str
    archived: bool
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NotePage:
    items: list[Note]
    next_after: UUID | None


class NotesService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _scope(
        self, connection: Connection, principal: Principal, workspace: UUID, *, write: bool = False
    ) -> dict[str, UUID]:
        member = resolve_member(
            connection,
            issuer=principal.issuer,
            subject=principal.subject,
            workspace_id=workspace,
            write=write,
        )
        return {"workspace": member.workspace_id, "owner": member.user_id}

    def _audit(
        self, connection: Connection, scope: dict[str, UUID], note: Note, operation: str
    ) -> None:
        connection.execute(
            text("""INSERT INTO note_events (workspace_id, note_id, actor_id, version, operation)
                    VALUES (:workspace, :id, :owner, :version, :operation)"""),
            {**scope, "id": note.id, "version": note.version, "operation": operation},
        )

    def page(
        self,
        principal: Principal,
        workspace: UUID,
        *,
        archived: bool = False,
        limit: int = 25,
        after: UUID | None = None,
    ) -> NotePage:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            scope = self._scope(connection, principal, workspace)
            params: dict[str, UUID | bool | int | datetime] = {
                **scope,
                "archived": archived,
                "limit": limit + 1,
            }
            boundary = ""
            if after is not None:
                pivot = connection.execute(
                    text(f"SELECT created_at FROM notes WHERE {_OWNER_SCOPE} AND id = :id"),
                    {**scope, "id": after},
                ).scalar_one_or_none()
                if pivot is None:
                    raise NoteNotFound
                boundary = " AND (created_at, id) < (:pivot, :after)"
                params.update(pivot=pivot, after=after)
            rows = (
                connection.execute(
                    text(f"""SELECT {_NOTE_FIELDS} FROM notes WHERE {_OWNER_SCOPE}
                    AND archived = :archived {boundary}
                    ORDER BY created_at DESC, id DESC LIMIT :limit"""),
                    params,
                )
                .mappings()
                .all()
            )
            notes = [Note(**row) for row in rows[:limit]]
            return NotePage(notes, notes[-1].id if len(rows) > limit else None)

    def create(self, principal: Principal, workspace: UUID, details: NoteBody) -> Note:
        with self.engine.begin() as connection:
            scope = self._scope(connection, principal, workspace, write=True)
            row = (
                connection.execute(
                    text(f"""INSERT INTO notes (id, workspace_id, owner_id, body)
                        VALUES (:id, :workspace, :owner, :body) RETURNING {_NOTE_FIELDS}"""),
                    {**scope, "id": uuid4(), "body": details.body},
                )
                .mappings()
                .one()
            )
            note = Note(**row)
            self._audit(connection, scope, note, "created")
            return note

    def update(
        self, principal: Principal, workspace: UUID, note_id: UUID, command: NoteEdit | NoteState
    ) -> Note:
        with self.engine.begin() as connection:
            scope = self._scope(connection, principal, workspace, write=True)
            args = {**scope, "id": note_id}
            selected = (
                connection.execute(
                    text(f"""SELECT {_NOTE_FIELDS} FROM notes WHERE {_OWNER_SCOPE}
                        AND id = :id FOR UPDATE"""),
                    args,
                )
                .mappings()
                .first()
            )
            if selected is None:
                raise NoteNotFound
            current = Note(**selected)
            if current.version != command.expected_version:
                raise VersionConflict
            body, archived = current.body, current.archived
            if isinstance(command, NoteEdit):
                if archived:
                    raise InvalidTransition
                body, operation = command.body, "edited"
            else:
                archived = command.archived
                operation = "archived" if archived else "restored"
            if (body, archived) == (current.body, current.archived):
                return current
            row = (
                connection.execute(
                    text(f"""UPDATE notes SET body = :body, archived = :archived,
                        version = version + 1, updated_at = now() WHERE {_OWNER_SCOPE}
                        AND id = :id RETURNING {_NOTE_FIELDS}"""),
                    {**args, "body": body, "archived": archived},
                )
                .mappings()
                .one()
            )
            updated = Note(**row)
            self._audit(connection, scope, updated, operation)
            return updated
