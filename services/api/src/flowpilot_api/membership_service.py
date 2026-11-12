"""Verified-identity onboarding and owner-controlled membership administration."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, Engine, text

from flowpilot_api.access import AccessDenied, Membership, Role
from flowpilot_api.member_context import resolve_member
from flowpilot_api.work_service import Principal


class MemberNotFound(Exception):
    pass


class ProfileNotFound(Exception):
    pass


class MembershipConflict(Exception):
    pass


class LastOwnerConflict(Exception):
    pass


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        if "\x00" in value or not value.strip():
            raise ValueError("Workspace name must be nonblank text without NUL")
        return value.strip()


@dataclass(frozen=True)
class OwnProfile:
    id: UUID


@dataclass(frozen=True)
class WorkspaceInfo:
    id: UUID
    name: str
    role: Role


@dataclass(frozen=True)
class MemberInfo:
    user_id: UUID
    role: Role
    active: bool
    version: int


def _member_info(row) -> MemberInfo:
    return MemberInfo(row["user_id"], Role(row["role"]), row["active"], row["version"])


class MembershipService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _owner(
        self,
        connection: Connection,
        principal: Principal,
        workspace_id: UUID,
        *,
        mutation: bool = False,
    ) -> Membership:
        # Every membership mutation takes this same lock before any member row locks.
        # It serializes owner-count decisions without locking unrelated workspaces.
        if mutation:
            found = connection.execute(
                text("SELECT id FROM workspaces WHERE id=:workspace FOR UPDATE"),
                {"workspace": workspace_id},
            ).first()
            if found is None:
                raise AccessDenied
        member = resolve_member(
            connection,
            issuer=principal.issuer,
            subject=principal.subject,
            workspace_id=workspace_id,
            write=True,
        )
        if member.role != Role.OWNER:
            raise AccessDenied
        return member

    def _audit(self, connection, workspace_id, actor_id, target, operation, before=None):
        connection.execute(
            text("""INSERT INTO workspace_events
            (id, workspace_id, actor_id, target_id, operation, from_role, to_role,
             from_active, to_active, membership_version)
            VALUES (:id, :workspace, :actor, :target, :operation, :before_role, :after_role,
                    :before_active, :after_active, :version)"""),
            {
                "id": uuid4(),
                "workspace": workspace_id,
                "actor": actor_id,
                "target": target.user_id,
                "operation": operation,
                "before_role": before.role if before else None,
                "after_role": target.role,
                "before_active": before.active if before else None,
                "after_active": target.active,
                "version": target.version,
            },
        )

    def profile(self, principal: Principal) -> OwnProfile:
        with self.engine.begin() as connection:
            user_id = connection.execute(
                text("SELECT id FROM users WHERE issuer=:issuer AND subject=:subject"),
                {"issuer": principal.issuer, "subject": principal.subject},
            ).scalar_one_or_none()
            if user_id is None:
                raise ProfileNotFound
            return OwnProfile(user_id)

    def create_workspace(self, principal: Principal, payload: WorkspaceCreate) -> WorkspaceInfo:
        with self.engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO users (id, issuer, subject)
                VALUES (:id, :issuer, :subject) ON CONFLICT (issuer, subject) DO NOTHING"""),
                {"id": uuid4(), "issuer": principal.issuer, "subject": principal.subject},
            )
            user_id = connection.execute(
                text("SELECT id FROM users WHERE issuer=:issuer AND subject=:subject"),
                {"issuer": principal.issuer, "subject": principal.subject},
            ).scalar_one()
            workspace_id = uuid4()
            connection.execute(
                text("INSERT INTO workspaces (id,name) VALUES (:id,:name)"),
                {"id": workspace_id, "name": payload.name},
            )
            connection.execute(
                text("""INSERT INTO memberships (workspace_id,user_id,role)
                VALUES (:workspace,:user,'owner')"""),
                {"workspace": workspace_id, "user": user_id},
            )
            self._audit(
                connection,
                workspace_id,
                user_id,
                MemberInfo(user_id, Role.OWNER, True, 1),
                "workspace_created",
            )
            return WorkspaceInfo(workspace_id, payload.name, Role.OWNER)

    def list_workspaces(self, principal: Principal, *, limit: int = 50) -> list[WorkspaceInfo]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            rows = connection.execute(
                text("""SELECT w.id,w.name,m.role FROM workspaces w
                JOIN memberships m ON m.workspace_id=w.id JOIN users u ON u.id=m.user_id
                WHERE u.issuer=:issuer AND u.subject=:subject AND m.active=true
                ORDER BY w.name,w.id LIMIT :limit"""),
                {"issuer": principal.issuer, "subject": principal.subject, "limit": limit},
            ).mappings()
            return [WorkspaceInfo(row["id"], row["name"], Role(row["role"])) for row in rows]

    def list_members(
        self, principal: Principal, workspace_id: UUID, *, limit: int = 50
    ) -> list[MemberInfo]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            self._owner(connection, principal, workspace_id)
            rows = connection.execute(
                text("""SELECT user_id,role,active,version FROM memberships
                WHERE workspace_id=:workspace ORDER BY user_id LIMIT :limit"""),
                {"workspace": workspace_id, "limit": limit},
            ).mappings()
            return [_member_info(row) for row in rows]

    def add_member(
        self, principal: Principal, workspace_id: UUID, user_id: UUID, *, role: Role = Role.MEMBER
    ) -> MemberInfo:
        if role not in tuple(Role):
            raise ValueError("Unknown role")
        with self.engine.begin() as connection:
            actor = self._owner(connection, principal, workspace_id, mutation=True)
            known = connection.execute(
                text("SELECT id FROM users WHERE id=:id AND issuer=:issuer"),
                {"id": user_id, "issuer": principal.issuer},
            ).first()
            if known is None:
                raise MemberNotFound
            row = (
                connection.execute(
                    text("""INSERT INTO memberships (workspace_id,user_id,role)
                VALUES (:workspace,:user,:role) ON CONFLICT (workspace_id,user_id) DO NOTHING
                RETURNING user_id,role,active,version"""),
                    {"workspace": workspace_id, "user": user_id, "role": role},
                )
                .mappings()
                .first()
            )
            if row is None:
                raise MembershipConflict
            member = _member_info(row)
            self._audit(connection, workspace_id, actor.user_id, member, "member_added")
            return member

    def change_member(
        self,
        principal: Principal,
        workspace_id: UUID,
        user_id: UUID,
        *,
        role: Role,
        active: bool,
        expected_version: int,
    ) -> MemberInfo:
        if (
            role not in tuple(Role)
            or type(active) is not bool
            or type(expected_version) is not int
            or expected_version < 1
        ):
            raise ValueError("Invalid membership command")
        with self.engine.begin() as connection:
            actor = self._owner(connection, principal, workspace_id, mutation=True)
            row = (
                connection.execute(
                    text("""SELECT user_id,role,active,version FROM memberships
                WHERE workspace_id=:workspace AND user_id=:user FOR UPDATE"""),
                    {"workspace": workspace_id, "user": user_id},
                )
                .mappings()
                .first()
            )
            if row is None:
                raise MemberNotFound
            before = _member_info(row)
            if before.version != expected_version or (
                before.role == role and before.active == active
            ):
                raise MembershipConflict
            if before.active and before.role == Role.OWNER and (not active or role != Role.OWNER):
                owners = connection.execute(
                    text("""SELECT count(*) FROM memberships
                    WHERE workspace_id=:workspace AND active=true AND role='owner'"""),
                    {"workspace": workspace_id},
                ).scalar_one()
                if owners <= 1:
                    raise LastOwnerConflict
            updated = (
                connection.execute(
                    text("""UPDATE memberships SET role=:role,active=:active,
                version=version+1 WHERE workspace_id=:workspace AND user_id=:user
                AND version=:version RETURNING user_id,role,active,version"""),
                    {
                        "role": role,
                        "active": active,
                        "workspace": workspace_id,
                        "user": user_id,
                        "version": expected_version,
                    },
                )
                .mappings()
                .one()
            )
            member = _member_info(updated)
            self._audit(
                connection, workspace_id, actor.user_id, member, "membership_changed", before
            )
            return member

    def history(self, principal: Principal, workspace_id: UUID, *, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            self._owner(connection, principal, workspace_id)
            rows = connection.execute(
                text("""SELECT actor_id,target_id,operation,from_role,to_role,
                from_active,to_active,membership_version,created_at FROM workspace_events
                WHERE workspace_id=:workspace ORDER BY created_at DESC,id LIMIT :limit"""),
                {"workspace": workspace_id, "limit": limit},
            ).mappings()
            return [dict(row) for row in rows]
