"""Verified-identity onboarding and owner-controlled membership administration."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
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


class InvitationNotFound(Exception):
    pass


class InvitationConflict(Exception):
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


@dataclass(frozen=True)
class InvitationInfo:
    id: UUID
    workspace_id: UUID
    workspace_name: str
    recipient_id: UUID
    role: Role
    status: str
    version: int
    expires_at: datetime


def _member_info(row) -> MemberInfo:
    return MemberInfo(row["user_id"], Role(row["role"]), row["active"], row["version"])


def _invitation_info(row, workspace_name: str) -> InvitationInfo:
    return InvitationInfo(
        row["id"],
        row["workspace_id"],
        workspace_name,
        row["recipient_id"],
        Role(row["role"]),
        row["status"],
        row["version"],
        row["expires_at"],
    )


_INVITER_IS_OWNER = "m.active AND m.role = 'owner' AND m.version = i.inviter_version"


class MembershipService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _lock_workspace(self, connection: Connection, workspace_id: UUID) -> str:
        name = connection.execute(
            text("SELECT name FROM workspaces WHERE id=:workspace FOR UPDATE"),
            {"workspace": workspace_id},
        ).scalar_one_or_none()
        if name is None:
            raise AccessDenied
        return name

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
            self._lock_workspace(connection, workspace_id)
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

    def _profile_id(self, connection: Connection, principal: Principal) -> UUID:
        user_id = connection.execute(
            text("SELECT id FROM users WHERE issuer=:issuer AND subject=:subject"),
            {"issuer": principal.issuer, "subject": principal.subject},
        ).scalar_one_or_none()
        if user_id is None:
            raise ProfileNotFound
        return user_id

    def _ensure_profile(self, connection: Connection, principal: Principal) -> UUID:
        connection.execute(
            text("""INSERT INTO users (id, issuer, subject)
            VALUES (:id, :issuer, :subject) ON CONFLICT (issuer, subject) DO NOTHING"""),
            {"id": uuid4(), "issuer": principal.issuer, "subject": principal.subject},
        )
        return self._profile_id(connection, principal)

    def profile(self, principal: Principal) -> OwnProfile:
        with self.engine.begin() as connection:
            return OwnProfile(self._profile_id(connection, principal))

    def register_profile(self, principal: Principal) -> OwnProfile:
        with self.engine.begin() as connection:
            return OwnProfile(self._ensure_profile(connection, principal))

    def create_workspace(self, principal: Principal, payload: WorkspaceCreate) -> WorkspaceInfo:
        with self.engine.begin() as connection:
            user_id = self._ensure_profile(connection, principal)
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
            self._require_registered_user(connection, user_id, principal.issuer)
            return self._insert_member(connection, workspace_id, user_id, role, actor.user_id)

    def _require_registered_user(self, connection: Connection, user_id: UUID, issuer: str):
        found = connection.execute(
            text("SELECT id FROM users WHERE id=:id AND issuer=:issuer"),
            {"id": user_id, "issuer": issuer},
        ).first()
        if found is None:
            raise MemberNotFound

    def _insert_member(
        self, connection: Connection, workspace_id: UUID, user_id: UUID, role: Role, actor_id: UUID
    ) -> MemberInfo:
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
        self._audit(connection, workspace_id, actor_id, member, "member_added")
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

    def _record_invitation(
        self,
        connection: Connection,
        invitation_id: UUID,
        version: int,
        actor_id: UUID,
        operation: str,
    ) -> None:
        connection.execute(
            text("""INSERT INTO invitation_events (invitation_id, version, actor_id, operation)
                VALUES (:id, :version, :actor, :operation)"""),
            {"id": invitation_id, "version": version, "actor": actor_id, "operation": operation},
        )

    def invite(
        self, principal: Principal, workspace_id: UUID, recipient_id: UUID, *, role: Role
    ) -> InvitationInfo:
        with self.engine.begin() as connection:
            name = self._lock_workspace(connection, workspace_id)
            actor = self._owner(connection, principal, workspace_id)
            self._require_registered_user(connection, recipient_id, principal.issuer)
            params = {"workspace": workspace_id, "recipient": recipient_id}
            existing = connection.execute(
                text("""SELECT 1 FROM memberships WHERE workspace_id=:workspace AND user_id=:recipient
                    UNION ALL SELECT 1 FROM workspace_invitations
                    WHERE workspace_id=:workspace AND recipient_id=:recipient
                    AND status='pending' AND expires_at > clock_timestamp() LIMIT 1"""),
                params,
            ).first()
            if existing:
                raise InvitationConflict
            inviter_version = connection.execute(
                text(
                    "SELECT version FROM memberships WHERE workspace_id=:workspace AND user_id=:actor"
                ),
                {"workspace": workspace_id, "actor": actor.user_id},
            ).scalar_one()
            row = (
                connection.execute(
                    text("""INSERT INTO workspace_invitations
                    (id, workspace_id, inviter_id, inviter_version, recipient_id, role, expires_at)
                    VALUES (:id, :workspace, :actor, :inviter_version, :recipient,
                            :role, clock_timestamp() + INTERVAL '168 hours') RETURNING *"""),
                    {
                        **params,
                        "id": uuid4(),
                        "actor": actor.user_id,
                        "inviter_version": inviter_version,
                        "role": role,
                    },
                )
                .mappings()
                .one()
            )
            self._record_invitation(connection, row["id"], row["version"], actor.user_id, "created")
            return _invitation_info(row, name)

    def invitations(
        self, principal: Principal, *, workspace_id: UUID | None = None, limit: int = 50
    ) -> list[InvitationInfo]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as connection:
            if workspace_id is None:
                user_id = self._profile_id(connection, principal)
                scope = f"""i.recipient_id = :user AND ({_INVITER_IS_OWNER})
                    AND NOT EXISTS (SELECT 1 FROM memberships present
                        WHERE present.workspace_id=i.workspace_id AND present.user_id=i.recipient_id)"""
            else:
                self._owner(connection, principal, workspace_id)
                user_id = workspace_id
                scope = "i.workspace_id = :user"
            rows = connection.execute(
                text(f"""SELECT i.*, w.name AS workspace_name FROM workspace_invitations i
                    JOIN workspaces w ON w.id = i.workspace_id
                    JOIN memberships m ON m.workspace_id = i.workspace_id AND m.user_id = i.inviter_id
                    WHERE ({scope}) AND i.status = 'pending' AND i.expires_at > statement_timestamp()
                    ORDER BY i.expires_at, i.id LIMIT :limit"""),
                {"user": user_id, "limit": limit},
            ).mappings()
            return [_invitation_info(row, row["workspace_name"]) for row in rows]

    def decide_invitation(
        self,
        principal: Principal,
        invitation_id: UUID,
        *,
        decision: Literal["accept", "decline"],
        expected_version: int,
    ) -> InvitationInfo:
        with self.engine.begin() as connection:
            recipient = self._profile_id(connection, principal)
            workspace_id = connection.execute(
                text(
                    "SELECT workspace_id FROM workspace_invitations WHERE id=:id AND recipient_id=:recipient"
                ),
                {"id": invitation_id, "recipient": recipient},
            ).scalar_one_or_none()
            if workspace_id is None:
                raise InvitationNotFound
            name = self._lock_workspace(connection, workspace_id)
            if decision == "accept":
                authorized = connection.execute(
                    text(f"""SELECT 1 FROM workspace_invitations i JOIN memberships m
                        ON m.workspace_id=i.workspace_id AND m.user_id=i.inviter_id
                        WHERE i.id=:id AND ({_INVITER_IS_OWNER})"""),
                    {"id": invitation_id},
                ).first()
                if not authorized:
                    raise InvitationConflict
            result = self._finish_invitation(
                connection,
                workspace_id,
                name,
                invitation_id,
                recipient,
                expected_version,
                "accepted" if decision == "accept" else "declined",
            )
            if decision == "accept":
                self._insert_member(connection, workspace_id, recipient, result.role, recipient)
            return result

    def revoke_invitation(
        self,
        principal: Principal,
        workspace_id: UUID,
        invitation_id: UUID,
        *,
        expected_version: int,
    ) -> InvitationInfo:
        with self.engine.begin() as connection:
            name = self._lock_workspace(connection, workspace_id)
            actor = self._owner(connection, principal, workspace_id)
            return self._finish_invitation(
                connection,
                workspace_id,
                name,
                invitation_id,
                actor.user_id,
                expected_version,
                "revoked",
            )

    def _finish_invitation(
        self,
        connection: Connection,
        workspace_id: UUID,
        name: str,
        invitation_id: UUID,
        actor_id: UUID,
        expected_version: int,
        status: Literal["accepted", "declined", "revoked"],
    ) -> InvitationInfo:
        # Lock first so the expiration check is made after any wait, even if the row is unchanged.
        keys = {"id": invitation_id, "workspace": workspace_id}
        found = connection.execute(
            text(
                "SELECT id FROM workspace_invitations WHERE id=:id AND workspace_id=:workspace FOR UPDATE"
            ),
            keys,
        ).first()
        if found is None:
            raise InvitationNotFound
        row = (
            connection.execute(
                text("""UPDATE workspace_invitations SET status=:status, version=version+1
                WHERE id=:id AND workspace_id=:workspace AND status='pending'
                AND version=:expected AND expires_at > clock_timestamp() RETURNING *"""),
                {**keys, "status": status, "expected": expected_version},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise InvitationConflict
        self._record_invitation(connection, invitation_id, row["version"], actor_id, status)
        return _invitation_info(row, name)
