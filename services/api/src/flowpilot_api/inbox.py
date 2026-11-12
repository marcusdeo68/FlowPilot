"""Read model for the caller's private, manual-source inbox."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, text

from flowpilot_api.member_context import resolve_member
from flowpilot_api.proposals import State
from flowpilot_api.work_service import Principal, SourceNotFound


@dataclass(frozen=True)
class InboxReview:
    id: UUID
    state: State


@dataclass(frozen=True)
class InboxItem:
    id: UUID
    summary: str
    created_at: datetime
    review: InboxReview | None


@dataclass(frozen=True)
class InboxPage:
    items: list[InboxItem]
    next_after: UUID | None


class InboxService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def page(
        self, principal: Principal, workspace: UUID, *, limit: int, after: UUID | None
    ) -> InboxPage:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.engine.begin() as c:
            member = resolve_member(
                c, issuer=principal.issuer, subject=principal.subject, workspace_id=workspace
            )
            params = {"ws": workspace, "owner": member.user_id, "count": limit + 1}
            boundary = ""
            if after is not None:
                pivot = c.execute(
                    text("""SELECT created_at FROM source_items
                    WHERE workspace_id=:ws AND owner_id=:owner AND id=:after"""),
                    {**params, "after": after},
                ).scalar_one_or_none()
                if pivot is None:
                    raise SourceNotFound
                boundary = " AND (s.created_at, s.id) < (:pivot, :after)"
                params.update(pivot=pivot, after=after)
            query = """SELECT s.id, s.summary, s.created_at, p.id AS proposal_id, p.state
                FROM source_items s LEFT JOIN task_proposals p
                    ON p.workspace_id=s.workspace_id AND p.source_id=s.id AND p.owner_id=s.owner_id
                WHERE s.workspace_id=:ws AND s.owner_id=:owner"""
            rows = (
                c.execute(
                    text(query + boundary + " ORDER BY s.created_at DESC, s.id DESC LIMIT :count"),
                    params,
                )
                .mappings()
                .all()
            )
            items = [
                InboxItem(
                    id=row["id"],
                    summary=row["summary"],
                    created_at=row["created_at"],
                    review=InboxReview(id=row["proposal_id"], state=row["state"])
                    if row["proposal_id"] is not None
                    else None,
                )
                for row in rows[:limit]
            ]
            return InboxPage(items, items[-1].id if len(rows) > limit else None)
