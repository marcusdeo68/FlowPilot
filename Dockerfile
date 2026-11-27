FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.12-slim-bookworm AS build

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/flowpilot
COPY pyproject.toml uv.lock README.md ./
COPY services/api/src ./services/api/src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 flowpilot \
    && useradd --uid 10001 --gid 10001 --no-create-home flowpilot
WORKDIR /opt/flowpilot
COPY --from=build /opt/flowpilot/.venv ./.venv
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/opt/flowpilot/.venv/bin:${PATH}" \
    FLOWPILOT_HOSTED=1 \
    FORWARDED_ALLOW_IPS="" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER flowpilot
EXPOSE 8000
CMD ["uvicorn", "flowpilot_api.workspace_api:create_workspace_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
