"""Verified browser and bearer entry points for private notes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from flowpilot_api.identity import AccessIdentity
from flowpilot_api.notes import Note, NoteBody, NoteEdit, NotePage, NotesService, NoteState


class NoteValidationProblem(BaseModel):
    detail: str


class NoteRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": "Invalid note request"})

        return handle


def notes_routes(service: NotesService, read_identity, write_identity) -> APIRouter:
    router = APIRouter(
        prefix="/api/v2/workspaces/{workspace_id}/notes",
        tags=["Private notes"],
        route_class=NoteRoute,
        responses={422: {"model": NoteValidationProblem}},
    )

    @router.get("")
    def page(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        archived: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        after: UUID | None = None,
    ) -> NotePage:
        return service.page(
            user.principal, workspace_id, archived=archived, limit=limit, after=after
        )

    @router.post("", status_code=201)
    def create(
        workspace_id: UUID,
        payload: NoteBody,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ) -> Note:
        return service.create(user.principal, workspace_id, payload)

    @router.patch("/{note_id}")
    def edit(
        workspace_id: UUID,
        note_id: UUID,
        payload: NoteEdit,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ) -> Note:
        return service.update(user.principal, workspace_id, note_id, payload)

    @router.post("/{note_id}/state")
    def set_state(
        workspace_id: UUID,
        note_id: UUID,
        payload: NoteState,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ) -> Note:
        return service.update(user.principal, workspace_id, note_id, payload)

    return router
