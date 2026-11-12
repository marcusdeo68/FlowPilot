"""Separate bearer-authenticated API factory; the legacy demo is not mounted."""

from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from flowpilot_api.access import AccessDenied, EvidenceVisibility, Role, Visibility
from flowpilot_api.identity import (
    AccessIdentity,
    AccessTokenVerifier,
    IdentityConfig,
    IdentityUnavailable,
    InvalidAccessToken,
)
from flowpilot_api.membership_service import (
    LastOwnerConflict,
    MemberInfo,
    MemberNotFound,
    MembershipConflict,
    MembershipService,
    OwnProfile,
    ProfileNotFound,
    WorkspaceCreate,
    WorkspaceInfo,
)
from flowpilot_api.proposal_routes import proposal_routes
from flowpilot_api.proposals import ProposalNotFound, ProposalService, ReviewConflict
from flowpilot_api.repository import InvalidTransition, VersionConflict
from flowpilot_api.storage import SCHEMA_REVISION, create_database_engine
from flowpilot_api.work import WorkItem
from flowpilot_api.work_service import (
    ManualSource,
    SourceNotFound,
    StoredWork,
    WorkNotFound,
    WorkService,
)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWork(Command):
    item: WorkItem
    visibility: Visibility = Visibility.PRIVATE


class ExpectedVersion(Command):
    expected_version: int = Field(ge=1, strict=True)


class TransitionWork(ExpectedVersion):
    target: str = Field(min_length=1, max_length=20)


class LinkEvidence(ExpectedVersion):
    source_id: UUID
    visibility: EvidenceVisibility


class AddMember(Command):
    user_id: UUID
    role: Role = Role.MEMBER


class ChangeMember(ExpectedVersion):
    role: Role
    active: bool = Field(strict=True)


def create_workspace_app(
    *, engine: Engine | None = None, verifier: AccessTokenVerifier | None = None
) -> FastAPI:
    verifier = verifier or AccessTokenVerifier(IdentityConfig.from_environment())
    owns_engine = engine is None
    engine = engine if engine is not None else create_database_engine()
    service = WorkService(engine)
    memberships = MembershipService(engine)

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield
        finally:
            if owns_engine:
                engine.dispose()

    app = FastAPI(title="FlowPilot Workspace API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    bearer = HTTPBearer(auto_error=False)

    def identity(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> AccessIdentity:
        if credentials is None:
            raise HTTPException(
                401, "Bearer access token required", headers={"WWW-Authenticate": "Bearer"}
            )
        try:
            return verifier.verify(credentials.credentials)
        except InvalidAccessToken as exc:
            raise HTTPException(
                401,
                "Invalid access token",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            ) from exc
        except IdentityUnavailable as exc:
            raise HTTPException(503, "Identity verification temporarily unavailable") from exc

    def read_identity(user: Annotated[AccessIdentity, Depends(identity)]) -> AccessIdentity:
        if "flowpilot:read" not in user.scopes:
            raise HTTPException(403, "Missing API read scope")
        return user

    def write_identity(user: Annotated[AccessIdentity, Depends(read_identity)]) -> AccessIdentity:
        if "flowpilot:write" not in user.scopes:
            raise HTTPException(403, "Missing API write scope")
        return user

    def problem(code, message):
        async def handle(_: Request, __: Exception):
            return JSONResponse({"detail": message}, status_code=code)

        return handle

    for exception, code, message in (
        (ProposalNotFound, 404, "Proposal not found"),
        (
            ReviewConflict,
            409,
            "Proposal unchanged, already reviewed, or stale; reload before reviewing",
        ),
        (AccessDenied, 403, "Workspace capability denied"),
        (WorkNotFound, 404, "Work item not found"),
        (SourceNotFound, 404, "Source item not found"),
        (VersionConflict, 409, "Work changed; reload its current version"),
        (InvalidTransition, 409, "Invalid work transition"),
        (IntegrityError, 409, "Conflicting or invalid record"),
        (MemberNotFound, 404, "Member or registered user not found"),
        (ProfileNotFound, 404, "Complete workspace onboarding first"),
        (MembershipConflict, 409, "Membership conflicts; reload its current state"),
        (LastOwnerConflict, 409, "Workspace must keep at least one active owner"),
    ):
        app.add_exception_handler(exception, problem(code, message))

    @app.middleware("http")
    async def private_response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                if revision != SCHEMA_REVISION:
                    raise HTTPException(503, "Database migration required")
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Database is unavailable or migrations are required") from exc
        return {"status": "ready"}

    @app.get("/api/v2/me", response_model=OwnProfile)
    def own_profile(user: Annotated[AccessIdentity, Depends(read_identity)]):
        return memberships.profile(user.principal)

    @app.get("/api/v2/workspaces", response_model=list[WorkspaceInfo])
    def my_workspaces(
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return memberships.list_workspaces(user.principal, limit=limit)

    @app.post("/api/v2/workspaces", response_model=WorkspaceInfo, status_code=201)
    def new_workspace(
        payload: WorkspaceCreate, user: Annotated[AccessIdentity, Depends(write_identity)]
    ):
        return memberships.create_workspace(user.principal, payload)

    @app.get("/api/v2/workspaces/{workspace_id}/members", response_model=list[MemberInfo])
    def members(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return memberships.list_members(user.principal, workspace_id, limit=limit)

    @app.post(
        "/api/v2/workspaces/{workspace_id}/members", response_model=MemberInfo, status_code=201
    )
    def member_add(
        workspace_id: UUID,
        payload: AddMember,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return memberships.add_member(
            user.principal, workspace_id, payload.user_id, role=payload.role
        )

    @app.patch("/api/v2/workspaces/{workspace_id}/members/{user_id}", response_model=MemberInfo)
    def member_change(
        workspace_id: UUID,
        user_id: UUID,
        payload: ChangeMember,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return memberships.change_member(
            user.principal,
            workspace_id,
            user_id,
            role=payload.role,
            active=payload.active,
            expected_version=payload.expected_version,
        )

    @app.get("/api/v2/workspaces/{workspace_id}/membership-history")
    def membership_history(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return memberships.history(user.principal, workspace_id, limit=limit)

    @app.get("/api/v2/workspaces/{workspace_id}/work", response_model=list[StoredWork])
    def list_work(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return service.list_work(user.principal, workspace_id, limit=limit)

    @app.post("/api/v2/workspaces/{workspace_id}/work", response_model=StoredWork, status_code=201)
    def create_work(
        workspace_id: UUID,
        payload: CreateWork,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.create_work(
            user.principal, workspace_id, payload.item, visibility=payload.visibility
        )

    @app.get("/api/v2/workspaces/{workspace_id}/work/{work_id}", response_model=StoredWork)
    def get_work(
        workspace_id: UUID, work_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]
    ):
        return service.get_work(user.principal, workspace_id, work_id)

    @app.post(
        "/api/v2/workspaces/{workspace_id}/work/{work_id}/transitions", response_model=StoredWork
    )
    def transition(
        workspace_id: UUID,
        work_id: UUID,
        payload: TransitionWork,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.transition(
            user.principal,
            workspace_id,
            work_id,
            target=payload.target,
            expected_version=payload.expected_version,
        )

    @app.post("/api/v2/workspaces/{workspace_id}/work/{work_id}/share", response_model=StoredWork)
    def share(
        workspace_id: UUID,
        work_id: UUID,
        payload: ExpectedVersion,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.share_work(
            user.principal, workspace_id, work_id, expected_version=payload.expected_version
        )

    @app.post("/api/v2/workspaces/{workspace_id}/sources", status_code=201)
    def source_create(
        workspace_id: UUID,
        payload: ManualSource,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return {"id": service.create_source(user.principal, workspace_id, payload)}

    @app.get("/api/v2/workspaces/{workspace_id}/sources/{source_id}", response_model=ManualSource)
    def source_get(
        workspace_id: UUID, source_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]
    ):
        return service.get_source(user.principal, workspace_id, source_id)

    @app.post(
        "/api/v2/workspaces/{workspace_id}/work/{work_id}/evidence", response_model=StoredWork
    )
    def link(
        workspace_id: UUID,
        work_id: UUID,
        payload: LinkEvidence,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.link_evidence(
            user.principal,
            workspace_id,
            work_id,
            payload.source_id,
            visibility=payload.visibility,
            expected_version=payload.expected_version,
        )

    @app.get("/api/v2/workspaces/{workspace_id}/work/{work_id}/evidence")
    def evidence(
        workspace_id: UUID, work_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]
    ):
        return service.evidence(user.principal, workspace_id, work_id)

    @app.get("/api/v2/workspaces/{workspace_id}/work/{work_id}/history")
    def history(
        workspace_id: UUID, work_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]
    ):
        return service.history(user.principal, workspace_id, work_id)

    app.include_router(proposal_routes(ProposalService(engine), read_identity, write_identity))
    return app
