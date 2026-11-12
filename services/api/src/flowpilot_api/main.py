"""FlowPilot local API entry point."""

import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from flowpilot_api.database import connect, initialize_database
from flowpilot_api.domain import CommitmentStatus
from flowpilot_api.repository import (
    CommitmentNotFound,
    InvalidTransition,
    VersionConflict,
    create_commitment,
    get_commitment,
    list_commitments,
    list_events,
    transition_commitment,
)
from flowpilot_api.schemas import (
    CommitmentCreate,
    CommitmentEventOut,
    CommitmentListOut,
    CommitmentOut,
    CommitmentTransition,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="FlowPilot API",
    description="Local development foundation for commitments and their lifecycle.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


@app.middleware("http")
async def local_browser_boundary(request: Request, call_next):
    """Reduce cross-site browser access to the unauthenticated local demo."""
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        if (origin is not None and origin != expected_origin) or request.headers.get(
            "sec-fetch-site"
        ) == "cross-site":
            return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    # FastAPI's development API docs load their own scripts and styles.
    if request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
    return response


_WEB_ROOT = Path(__file__).resolve().parent / "web"


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    """Serve the local dashboard shell; API authorization is still not implemented."""
    return FileResponse(_WEB_ROOT / "index.html")


@app.get("/app.js", include_in_schema=False)
def web_script() -> FileResponse:
    return FileResponse(_WEB_ROOT / "app.js", media_type="text/javascript")


@app.get("/styles.css", include_in_schema=False)
def web_styles() -> FileResponse:
    return FileResponse(_WEB_ROOT / "styles.css", media_type="text/css")


@app.get("/healthz", tags=["operations"])
def health() -> dict[str, str]:
    """Process liveness only; this does not check dependencies or authorization."""
    return {"status": "ok"}


@app.get("/readyz", tags=["operations"])
def readiness() -> dict[str, str]:
    """Return success only when the local database is reachable."""
    try:
        with closing(connect()) as connection:
            connection.execute("SELECT 1")
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ready"}


@app.post(
    "/api/v1/commitments",
    response_model=CommitmentOut,
    status_code=status.HTTP_201_CREATED,
    tags=["commitments"],
)
def create(payload: CommitmentCreate) -> dict[str, object]:
    return create_commitment(payload)


@app.get(
    "/api/v1/commitments",
    response_model=CommitmentListOut,
    tags=["commitments"],
)
def list_all(
    status_filter: Annotated[CommitmentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    items = list_commitments(status=status_filter, limit=limit)
    return {"items": items, "count": len(items)}


@app.get(
    "/api/v1/commitments/{commitment_id}",
    response_model=CommitmentOut,
    tags=["commitments"],
)
def get_one(commitment_id: UUID) -> dict[str, object]:
    try:
        return get_commitment(commitment_id)
    except CommitmentNotFound as exc:
        raise HTTPException(status_code=404, detail="Commitment not found") from exc


@app.post(
    "/api/v1/commitments/{commitment_id}/transitions",
    response_model=CommitmentOut,
    tags=["commitments"],
)
def transition(commitment_id: UUID, payload: CommitmentTransition) -> dict[str, object]:
    try:
        return transition_commitment(
            commitment_id,
            target=payload.target_status,
            expected_version=payload.expected_version,
            reason=payload.reason,
        )
    except CommitmentNotFound as exc:
        raise HTTPException(status_code=404, detail="Commitment not found") from exc
    except VersionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="Commitment changed; fetch its current version and retry",
        ) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail="Invalid commitment state transition") from exc


@app.get(
    "/api/v1/commitments/{commitment_id}/events",
    response_model=list[CommitmentEventOut],
    tags=["commitments"],
)
def events(commitment_id: UUID) -> list[dict[str, object]]:
    try:
        return list_events(commitment_id)
    except CommitmentNotFound as exc:
        raise HTTPException(status_code=404, detail="Commitment not found") from exc
