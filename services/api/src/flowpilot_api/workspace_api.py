"""Separate bearer-authenticated API factory; the legacy demo is not mounted."""

import os
from contextlib import asynccontextmanager
from datetime import UTC, date
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from flowpilot_api.access import AccessDenied, EvidenceVisibility, Role, Visibility
from flowpilot_api.browser_sessions import (
    BrowserConfig,
    BrowserSessions,
    InvalidSession,
    SessionUnavailable,
)
from flowpilot_api.identity import (
    AccessIdentity,
    AccessTokenVerifier,
    IdentityConfig,
    IdentityUnavailable,
    InvalidAccessToken,
)
from flowpilot_api.inbox import InboxPage, InboxService
from flowpilot_api.ingress import (
    PROBE_PATHS,
    AuthenticatedIngress,
    ProxyIngress,
    RailwayIngress,
    railway_edge_enabled,
)
from flowpilot_api.login import Exchange, LoginConfig, LoginFlow
from flowpilot_api.login_transactions import InvalidLoginTransaction, LoginStorageUnavailable
from flowpilot_api.membership_service import (
    InvitationConflict,
    InvitationInfo,
    InvitationNotFound,
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
from flowpilot_api.notes import NoteNotFound, NotesService
from flowpilot_api.notes_routes import notes_routes
from flowpilot_api.proposal_routes import proposal_routes
from flowpilot_api.proposals import ProposalNotFound, ProposalService, ReviewConflict
from flowpilot_api.repository import InvalidTransition, VersionConflict
from flowpilot_api.session_routes import BrowserAuth, session_cookie
from flowpilot_api.storage import SCHEMA_REVISION, create_database_engine
from flowpilot_api.work import (
    Event,
    EventScheduleChange,
    InvalidEventSchedule,
    LocalEventSchedule,
    TaskDetails,
    TaskPriority,
    TaskStatus,
    WorkBase,
    WorkDetails,
    WorkItem,
)
from flowpilot_api.work_service import (
    DueTasks,
    ManualSource,
    ProjectNotFound,
    ReminderCandidates,
    ReminderCategory,
    SharePreview,
    SourceNotFound,
    StoredWork,
    UpcomingEvents,
    WorkNotFound,
    WorkPage,
    WorkService,
    WorkspaceProject,
)
from flowpilot_api.workspace_ui import workspace_ui


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


def parse_calendar_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "Use a valid local calendar date") from exc


class CreateWork(Command):
    item: WorkItem
    visibility: Visibility = Visibility.PRIVATE
    project_id: UUID | None = None
    priority: TaskPriority = "normal"


class CreateProject(Command):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00]+$"
        ),
    ]


class SearchWork(Command):
    q: str = Field(max_length=200, pattern=r"^[^\x00]*$")
    limit: int = Field(default=50, ge=1, le=100, strict=True)
    after: UUID | None = None
    kind: Literal["event"] | None = None
    visibility: Visibility | None = None
    task_status: TaskStatus | None = None
    project_id: UUID | None = None
    priority: TaskPriority | None = None


class ExpectedVersion(Command):
    expected_version: int = Field(ge=1, strict=True)


class TransitionWork(ExpectedVersion):
    target: str = Field(min_length=1, max_length=20)


class EditTask(ExpectedVersion):
    details: TaskDetails


class CreateManualEvent(WorkBase):
    schedule: LocalEventSchedule


class EditManualEvent(ExpectedVersion):
    details: WorkDetails
    schedule: EventScheduleChange | None = None


class EventEditorSchedule(BaseModel):
    version: int
    time_zone: str
    starts_at: str
    ends_at: str


class LinkEvidence(ExpectedVersion):
    source_id: UUID
    visibility: EvidenceVisibility


class AddMember(Command):
    user_id: UUID
    role: Role = Role.MEMBER


class ChangeMember(ExpectedVersion):
    role: Role
    active: bool = Field(strict=True)


class InvitationDecision(ExpectedVersion):
    decision: Literal["accept", "decline"]


def create_workspace_app(
    *,
    engine: Engine | None = None,
    verifier: AccessTokenVerifier | None = None,
    browser_origin: str | None = None,
    hosted: bool | None = None,
    login_config: LoginConfig | None = None,
    login_exchange: Exchange | None = None,
) -> FastAPI:
    if hosted is None:
        mode = os.environ.get("FLOWPILOT_HOSTED", "0")
        if mode not in ("0", "1"):
            raise ValueError("Set FLOWPILOT_HOSTED to 0 or 1")
        hosted = mode == "1"
    origin = (
        browser_origin if browser_origin is not None else os.environ.get("FLOWPILOT_BROWSER_ORIGIN")
    )
    if hosted and origin is None:
        raise ValueError("Hosted mode requires FLOWPILOT_BROWSER_ORIGIN")
    browser_config = BrowserConfig(origin, hosted=hosted) if origin is not None else None
    probe_host = os.environ.get("FLOWPILOT_PROBE_HOST")
    if probe_host is not None:
        if browser_config is None or not browser_config.hosted:
            raise ValueError("FLOWPILOT_PROBE_HOST requires hosted mode")
        if (
            BrowserConfig(f"https://{probe_host}", hosted=True).authority
            == browser_config.authority
        ):
            raise ValueError("FLOWPILOT_PROBE_HOST must differ from the public hostname")
    proxy = ProxyIngress.from_environment(browser_config, probe_host)
    railway_edge = railway_edge_enabled(browser_config, probe_host, proxy)
    login_config = login_config or LoginConfig.from_environment()
    if login_config is not None and browser_config is None:
        raise ValueError("Login requires an explicit browser origin")
    verifier = verifier or AccessTokenVerifier(IdentityConfig.from_environment())
    owns_engine = engine is None
    engine = engine if engine is not None else create_database_engine()
    service = WorkService(engine)
    memberships = MembershipService(engine)
    inbox = InboxService(engine)
    browser = (
        BrowserAuth(BrowserSessions(engine, verifier.config, browser_config))
        if browser_config is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield
        finally:
            if owns_engine:
                engine.dispose()

    app = FastAPI(title="FlowPilot Workspace API", version="0.2.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request: Request, exc: RequestValidationError):
        try:
            return await request_validation_exception_handler(request, exc)
        except UnicodeEncodeError:
            return JSONResponse({"detail": "Request contains invalid Unicode."}, status_code=422)

    if not hosted:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    bearer = HTTPBearer(auto_error=False)

    def bearer_identity(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> AccessIdentity:
        if session_cookie(request) is not None or len(request.headers.getlist("authorization")) > 1:
            raise HTTPException(401, "Bearer token without session cookie required")
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

    def identity(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> AccessIdentity:
        credential = session_cookie(request)
        if credential is not None:
            if browser is None:
                raise InvalidSession
            return browser.authenticate(request, credential)
        return bearer_identity(request, credentials)

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
        (InvalidSession, 401, "Invalid or expired browser session"),
        (SessionUnavailable, 503, "Session storage temporarily unavailable"),
        (InvalidLoginTransaction, 400, "Invalid login transaction"),
        (LoginStorageUnavailable, 503, "Login storage temporarily unavailable"),
        (ProposalNotFound, 404, "Proposal not found"),
        (
            ReviewConflict,
            409,
            "Proposal unchanged, already reviewed, or stale; reload before reviewing",
        ),
        (AccessDenied, 403, "Workspace capability denied"),
        (WorkNotFound, 404, "Work item not found"),
        (ProjectNotFound, 404, "Project not found"),
        (SourceNotFound, 404, "Source item not found"),
        (NoteNotFound, 404, "Note not found"),
        (VersionConflict, 409, "Work changed; reload its current version"),
        (InvalidTransition, 409, "Invalid work transition"),
        (IntegrityError, 409, "Conflicting or invalid record"),
        (MemberNotFound, 404, "Member or registered user not found"),
        (ProfileNotFound, 404, "Complete workspace onboarding first"),
        (MembershipConflict, 409, "Membership conflicts; reload its current state"),
        (LastOwnerConflict, 409, "Workspace must keep at least one active owner"),
        (InvitationNotFound, 404, "Invitation not found"),
        (InvitationConflict, 409, "Invitation changed, expired, or is unavailable"),
    ):
        app.add_exception_handler(exception, problem(code, message))

    @app.middleware("http")
    async def private_response_headers(request: Request, call_next):
        probe = request.method == "GET" and request.scope["path"] in PROBE_PATHS
        hosts = request.headers.getlist("host")
        if probe and probe_host is not None and hosts != [probe_host]:
            response = JSONResponse({"detail": "Not found"}, status_code=404)
        elif (
            browser_config is not None
            and browser_config.hosted
            and not probe
            and (request.scope["scheme"] != "https" or hosts != [browser_config.authority])
        ):
            response = JSONResponse({"detail": "Configured HTTPS host required"}, status_code=400)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    if hosted:

        @app.get("/", include_in_schema=False)
        def workspace_home():
            return RedirectResponse("/api/v2/workspace", status_code=307)

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

    @app.post("/api/v2/me", response_model=OwnProfile)
    def register_profile(user: Annotated[AccessIdentity, Depends(write_identity)]):
        return memberships.register_profile(user.principal)

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

    @app.get("/api/v2/workspaces/{workspace_id}", response_model=WorkspaceInfo)
    def selected_workspace(
        workspace_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]
    ):
        return memberships.workspace(user.principal, workspace_id)

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

    @app.get("/api/v2/invitations", response_model=list[InvitationInfo])
    def received_invitations(
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return memberships.invitations(user.principal, limit=limit)

    @app.get("/api/v2/workspaces/{workspace_id}/invitations", response_model=list[InvitationInfo])
    def workspace_invitations(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return memberships.invitations(user.principal, workspace_id=workspace_id, limit=limit)

    @app.post(
        "/api/v2/workspaces/{workspace_id}/invitations",
        response_model=InvitationInfo,
        status_code=201,
    )
    def offer_invitation(
        workspace_id: UUID,
        payload: AddMember,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return memberships.invite(user.principal, workspace_id, payload.user_id, role=payload.role)

    @app.post("/api/v2/invitations/{invitation_id}/decision", response_model=InvitationInfo)
    def answer_invitation(
        invitation_id: UUID,
        payload: InvitationDecision,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return memberships.decide_invitation(
            user.principal,
            invitation_id,
            decision=payload.decision,
            expected_version=payload.expected_version,
        )

    @app.post(
        "/api/v2/workspaces/{workspace_id}/invitations/{invitation_id}/revoke",
        response_model=InvitationInfo,
    )
    def remove_invitation(
        workspace_id: UUID,
        invitation_id: UUID,
        payload: ExpectedVersion,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return memberships.revoke_invitation(
            user.principal, workspace_id, invitation_id, expected_version=payload.expected_version
        )

    @app.get("/api/v2/workspaces/{workspace_id}/projects", response_model=list[WorkspaceProject])
    def projects(workspace_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]):
        return service.list_projects(user.principal, workspace_id)

    @app.post(
        "/api/v2/workspaces/{workspace_id}/projects",
        response_model=WorkspaceProject,
        status_code=201,
    )
    def create_project(
        workspace_id: UUID,
        payload: CreateProject,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.create_project(user.principal, workspace_id, payload.name)

    @app.get("/api/v2/workspaces/{workspace_id}/work", response_model=list[StoredWork])
    def list_work(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return service.list_work(user.principal, workspace_id, limit=limit)

    @app.get("/api/v2/workspaces/{workspace_id}/work-page", response_model=WorkPage)
    def work_page(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: UUID | None = None,
        kind: Literal["event"] | None = None,
        visibility: Visibility | None = None,
        task_status: TaskStatus | None = None,
        project_id: UUID | None = None,
        priority: TaskPriority | None = None,
    ):
        return service.list_work_page(
            user.principal,
            workspace_id,
            limit=limit,
            after=after,
            kind=kind,
            visibility=visibility,
            task_status=task_status,
            project_id=project_id,
            priority=priority,
        )

    @app.post("/api/v2/workspaces/{workspace_id}/work-page/search", response_model=WorkPage)
    def search_work_page(
        workspace_id: UUID,
        payload: SearchWork,
        user: Annotated[AccessIdentity, Depends(read_identity)],
    ):
        return service.list_work_page(
            user.principal,
            workspace_id,
            limit=payload.limit,
            after=payload.after,
            kind=payload.kind,
            visibility=payload.visibility,
            q=payload.q,
            task_status=payload.task_status,
            project_id=payload.project_id,
            priority=payload.priority,
        )

    @app.get("/api/v2/workspaces/{workspace_id}/work-due", response_model=DueTasks)
    def work_due(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        from_date: Annotated[str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")] = None,
    ):
        day = parse_calendar_date(from_date) if from_date is not None else None
        return service.list_due_tasks(user.principal, workspace_id, limit=limit, from_date=day)

    @app.get("/api/v2/workspaces/{workspace_id}/work-due-page", response_model=WorkPage)
    def work_due_page(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        from_date: Annotated[str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 5,
        after: UUID | None = None,
        after_version: Annotated[int | None, Query(ge=1)] = None,
    ):
        if (after is None) != (after_version is None):
            raise HTTPException(422, "Supply both deadline cursor fields together")
        cursor = (after, after_version) if after is not None and after_version is not None else None
        return service.list_due_page(
            user.principal,
            workspace_id,
            limit=limit,
            from_date=parse_calendar_date(from_date) if from_date is not None else None,
            after=cursor,
        )

    @app.get("/api/v2/workspaces/{workspace_id}/work-events", response_model=UpcomingEvents)
    def work_events(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 5,
    ):
        return service.list_upcoming_events(user.principal, workspace_id, limit=limit)

    @app.get("/api/v2/workspaces/{workspace_id}/work-schedule", response_model=WorkPage)
    def work_schedule(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        after: UUID | None = None,
        after_version: Annotated[int | None, Query(ge=1)] = None,
    ):
        if (after is None) != (after_version is None):
            raise HTTPException(422, "Supply both schedule cursor fields together")
        cursor = (after, after_version) if after is not None and after_version is not None else None
        return service.list_schedule(user.principal, workspace_id, limit=limit, after=cursor)

    @app.get("/api/v2/workspaces/{workspace_id}/reminders", response_model=ReminderCandidates)
    def reminders(
        workspace_id: UUID,
        request: Request,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        local_date: Annotated[str, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")],
        category: ReminderCategory = "both",
        event_lead_minutes: Annotated[int, Query(ge=5, le=60)] = 15,
    ):
        if session_cookie(request) is not None and "x-csrf-token" not in request.headers:
            raise InvalidSession
        try:
            day = date.fromisoformat(local_date)
        except ValueError as exc:
            raise HTTPException(422, "Use a valid local calendar date") from exc
        return service.reminder_candidates(
            user.principal,
            workspace_id,
            local_date=day,
            category=category,
            event_lead_minutes=event_lead_minutes,
        )

    @app.post(
        "/api/v2/workspaces/{workspace_id}/work-events", response_model=StoredWork, status_code=201
    )
    def create_manual_event(
        workspace_id: UUID,
        payload: CreateManualEvent,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.create_work(
            user.principal,
            workspace_id,
            Event(
                title=payload.title,
                description=payload.description,
                time_zone=payload.schedule.time_zone,
                starts_at=payload.schedule.starts_at,
                ends_at=payload.schedule.ends_at,
            ),
        )

    @app.post("/api/v2/workspaces/{workspace_id}/work", response_model=StoredWork, status_code=201)
    def create_work(
        workspace_id: UUID,
        payload: CreateWork,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.create_work(
            user.principal,
            workspace_id,
            payload.item,
            visibility=payload.visibility,
            project_id=payload.project_id,
            priority=payload.priority,
        )

    @app.get("/api/v2/workspaces/{workspace_id}/work/{work_id}", response_model=StoredWork)
    def get_work(
        workspace_id: UUID, work_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]
    ):
        return service.get_work(user.principal, workspace_id, work_id)

    @app.patch(
        "/api/v2/workspaces/{workspace_id}/work/{work_id}/task-details",
        response_model=StoredWork,
    )
    def edit_task(
        workspace_id: UUID,
        work_id: UUID,
        payload: EditTask,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        return service.edit_task(
            user.principal,
            workspace_id,
            work_id,
            details=payload.details,
            expected_version=payload.expected_version,
        )

    @app.get(
        "/api/v2/workspaces/{workspace_id}/work/{work_id}/event-details",
        response_model=EventEditorSchedule,
    )
    def event_editor_schedule(
        workspace_id: UUID, work_id: UUID, user: Annotated[AccessIdentity, Depends(read_identity)]
    ):
        work = service.get_work(user.principal, workspace_id, work_id)
        if not isinstance(work.data, Event):
            raise WorkNotFound
        zone = ZoneInfo(work.data.time_zone)
        try:
            start = work.data.starts_at.astimezone(zone)
            end = work.data.ends_at.astimezone(zone)
        except OverflowError:
            zone = ZoneInfo("UTC")
            start = work.data.starts_at.astimezone(UTC)
            end = work.data.ends_at.astimezone(UTC)
        return EventEditorSchedule(
            version=work.version,
            time_zone=zone.key,
            starts_at=start.replace(tzinfo=None).isoformat(),
            ends_at=end.replace(tzinfo=None).isoformat(),
        )

    @app.patch(
        "/api/v2/workspaces/{workspace_id}/work/{work_id}/event-details",
        response_model=StoredWork,
    )
    def edit_manual_event(
        workspace_id: UUID,
        work_id: UUID,
        payload: EditManualEvent,
        user: Annotated[AccessIdentity, Depends(write_identity)],
    ):
        try:
            return service.edit_event(
                user.principal,
                workspace_id,
                work_id,
                details=payload.details,
                schedule=payload.schedule,
                expected_version=payload.expected_version,
            )
        except InvalidEventSchedule as exc:
            raise HTTPException(422, str(exc)) from exc

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

    @app.get(
        "/api/v2/workspaces/{workspace_id}/work/{work_id}/share-preview",
        response_model=SharePreview,
    )
    def preview_share(
        workspace_id: UUID, work_id: UUID, user: Annotated[AccessIdentity, Depends(write_identity)]
    ):
        return service.share_preview(user.principal, workspace_id, work_id)

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

    @app.get("/api/v2/workspaces/{workspace_id}/sources", response_model=InboxPage)
    def source_list(
        workspace_id: UUID,
        user: Annotated[AccessIdentity, Depends(read_identity)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: UUID | None = None,
    ):
        return inbox.page(user.principal, workspace_id, limit=limit, after=after)

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
    app.include_router(notes_routes(NotesService(engine), read_identity, write_identity))
    if browser is not None:
        app.include_router(browser.routes(bearer_identity))
        app.include_router(workspace_ui(browser, login_enabled=login_config is not None))
        if login_config is not None:
            app.include_router(LoginFlow(browser, verifier, login_config, login_exchange).routes())
    if proxy is not None:
        app.add_middleware(AuthenticatedIngress, config=proxy)
    if railway_edge and browser_config is not None:
        app.add_middleware(RailwayIngress, public_host=browser_config.authority)
    return app
