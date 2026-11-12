from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from flowpilot_api.identity import AccessIdentity
from flowpilot_api.proposals import Correction, Proposal, ProposalService, Review


def proposal_routes(service: ProposalService, read_identity, write_identity) -> APIRouter:
    router = APIRouter(prefix="/api/v2/workspaces/{workspace_id}", tags=["Task review"])
    read = Annotated[AccessIdentity, Depends(read_identity)]
    write = Annotated[AccessIdentity, Depends(write_identity)]

    @router.put("/sources/{source_id}/task-proposal")
    def suggest(workspace_id: UUID, source_id: UUID, user: write) -> Proposal:
        return service.suggest(user.principal, workspace_id, source_id)

    @router.get("/proposals")
    def queue(
        workspace_id: UUID, user: read, limit: Annotated[int, Query(ge=1, le=100)] = 50
    ) -> list[Proposal]:
        return service.queue(user.principal, workspace_id, limit)

    @router.get("/proposals/{proposal_id}")
    def get(workspace_id: UUID, proposal_id: UUID, user: read) -> Proposal:
        return service.get(user.principal, workspace_id, proposal_id)

    @router.patch("/proposals/{proposal_id}")
    def correct(
        workspace_id: UUID, proposal_id: UUID, payload: Correction, user: write
    ) -> Proposal:
        return service.correct(user.principal, workspace_id, proposal_id, payload)

    @router.post("/proposals/{proposal_id}/review")
    def review(workspace_id: UUID, proposal_id: UUID, payload: Review, user: write) -> Proposal:
        return service.review(user.principal, workspace_id, proposal_id, payload)

    return router
