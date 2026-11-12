"""Deny-by-default policy for the next persistence adapter.

These inputs must come from verified identity and stored membership records.
They are not request schemas and must never be populated from client role claims.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    OWNER = "owner"
    MEMBER = "member"
    OBSERVER = "observer"


class Visibility(StrEnum):
    PRIVATE = "private"
    WORKSPACE = "workspace"


class EvidenceVisibility(StrEnum):
    PRIVATE = "private"
    SUMMARY_SHARED = "summary_shared"
    EXCERPT_SHARED = "excerpt_shared"


class AccessDenied(Exception):
    """A principal lacks the requested capability."""


@dataclass(frozen=True)
class Membership:
    user_id: UUID
    workspace_id: UUID
    role: Role
    active: bool = True


def require_membership(member: Membership, workspace_id: UUID, *, write: bool = False) -> None:
    if (
        member.active is not True
        or member.workspace_id != workspace_id
        or member.role not in (Role.OWNER, Role.MEMBER, Role.OBSERVER)
    ):
        raise AccessDenied
    if write and member.role not in (Role.OWNER, Role.MEMBER):
        raise AccessDenied


def require_work_access(
    member: Membership,
    workspace_id: UUID,
    creator_id: UUID,
    visibility: Visibility,
    *,
    write: bool = False,
) -> None:
    require_membership(member, workspace_id, write=write)
    if visibility not in (Visibility.PRIVATE, Visibility.WORKSPACE):
        raise AccessDenied
    if visibility == Visibility.PRIVATE and member.user_id != creator_id:
        raise AccessDenied


def require_source_access(member: Membership, workspace_id: UUID, owner_id: UUID) -> None:
    require_membership(member, workspace_id)
    # Workspace owners do not inherit access to private messages.
    if member.user_id != owner_id:
        raise AccessDenied


def visible_evidence(
    member: Membership,
    workspace_id: UUID,
    owner_id: UUID,
    visibility: EvidenceVisibility,
    *,
    summary: str,
    excerpt: str,
) -> dict[str, str]:
    """Project only explicitly shared fields; never return source bodies or links."""
    require_membership(member, workspace_id)
    if visibility not in (
        EvidenceVisibility.PRIVATE,
        EvidenceVisibility.SUMMARY_SHARED,
        EvidenceVisibility.EXCERPT_SHARED,
    ):
        raise AccessDenied
    if member.user_id == owner_id or visibility == EvidenceVisibility.EXCERPT_SHARED:
        return {"summary": summary, "excerpt": excerpt}
    if visibility == EvidenceVisibility.SUMMARY_SHARED:
        return {"summary": summary}
    return {}


def require_connection_action(
    member: Membership,
    workspace_id: UUID,
    owner_id: UUID,
    *,
    revoked: bool,
) -> None:
    require_membership(member, workspace_id, write=True)
    if member.user_id != owner_id or revoked is not False:
        raise AccessDenied
