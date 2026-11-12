"""Resolve stored membership for a verified identity within the caller's transaction."""

from uuid import UUID

from sqlalchemy import Connection, text

from flowpilot_api.access import AccessDenied, Membership, Role, require_membership


def resolve_member(
    connection: Connection, *, issuer: str, subject: str, workspace_id: UUID, write: bool = False
) -> Membership:
    row = (
        connection.execute(
            text("""
        SELECT m.user_id, m.workspace_id, m.role, m.active
        FROM memberships m JOIN users u ON u.id = m.user_id
        WHERE m.workspace_id = :workspace AND u.issuer = :issuer AND u.subject = :subject
        FOR SHARE OF m
    """),
            {"workspace": workspace_id, "issuer": issuer, "subject": subject},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise AccessDenied
    try:
        role = Role(row["role"])
    except ValueError as exc:
        raise AccessDenied from exc
    member = Membership(row["user_id"], row["workspace_id"], role, row["active"])
    require_membership(member, workspace_id, write=write)
    return member
