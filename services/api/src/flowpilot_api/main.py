"""FlowPilot local API entry point."""

import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse

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
    status_filter: CommitmentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
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
