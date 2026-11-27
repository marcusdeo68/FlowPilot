# Implementation 0046 — Rehearse the hosted workspace image

The workspace image job now starts the packaged Linux application against
disposable PostgreSQL with synthetic Railway settings. Compose waits for the
app’s private liveness probe. The test observes readiness returning 503
before migration, runs `alembic upgrade head` in a separate container from
the same image, and then observes readiness returning 200.

The HTTP probe uses the installed image’s public smoke check expectations.
For example, the same `/readyz` path returns 200 with the private probe host
after migration and 404 with the public host. It also checks the non-root
user, canonical redirect, workspace HTML, static assets, anonymous session
rejection, and refusal to serve the workspace without the expected scheme
or host. The requests run against the image's default server command.

## Run locally

From the repository root with Docker Desktop running, execute each command
in order. The Compose file defines its own internal network and in-memory
PostgreSQL storage. Both services have no published ports.

```powershell
docker build -t flowpilot-workspace:ci .
docker run --rm flowpilot-workspace:ci alembic heads
docker compose -f compose.hosted-test.yaml up -d --wait --wait-timeout 90
docker compose -f compose.hosted-test.yaml exec -T workspace python /tmp/hosted_image_smoke.py before-migration
docker compose -f compose.hosted-test.yaml run --rm -T --no-deps workspace alembic upgrade head
docker compose -f compose.hosted-test.yaml exec -T workspace python /tmp/hosted_image_smoke.py after-migration
docker compose -f compose.hosted-test.yaml down
```

If a check fails, inspect `docker compose -f compose.hosted-test.yaml logs`,
then run the teardown command before retrying. GitHub Actions collects logs
on failure and runs teardown on every result. The checks and their evidence
are tracked in [STATUS](../STATUS.md).

The rehearsal supplies the headers expected from Railway's edge. Live
staging must verify actual TLS, proxy behavior, private networking, log
privacy, and sign-in. The next milestone is the [public smoke check](0035-railway-direct-pilot.md#2-public-staging-smoke-check)
on the assigned HTTPS URL in the dedicated Railway environment.
