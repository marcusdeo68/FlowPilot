# Implementation 0032 — Railway portfolio pilot

The signed-in workspace accepts Railway's database URL and can reserve its
readiness checks for Railway's probe hostname. The first live deployment will
use an isolated project and synthetic data.

## Deployment configuration

1. In the Railway dashboard, create an isolated project and add a PostgreSQL
   service named `Postgres`. Keep its public TCP proxy disabled.
2. Connect the web service to the FlowPilot GitHub repository. Railway detects
   the root Dockerfile and uses its start command.
3. In the web service's Deploy settings, set **Pre-Deploy Command** to
   `alembic upgrade head`. Railway runs it in a separate container with access
   to the private database. Set a pre-deploy timeout to bound a failed migration.
4. Set **Healthcheck Path** to `/readyz`. FlowPilot returns success once it can
   read the expected Alembic revision. Railway uses this check when switching
   deployments. Keep later migrations compatible with the serving version until
   the new deployment is active. Rolling back the app leaves schema changes in place.

See [Dockerfile detection](https://docs.railway.com/builds/dockerfiles),
[pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command),
and [health checks](https://docs.railway.com/deployments/healthchecks).

For the isolated staging web service, set the following values:

| Setting | Value |
| --- | --- |
| `PORT` | `8000`. Use the matching target port for the HTTP domain. |
| `FLOWPILOT_HOSTED` | `1`, the image default. |
| `FLOWPILOT_BROWSER_ORIGIN` | The Railway service's assigned HTTPS origin, without a trailing slash. |
| `FLOWPILOT_RAILWAY_EDGE` | `1` for the dedicated pilot. See [0035](0035-railway-direct-pilot.md). |
| `FORWARDED_ALLOW_IPS` | Empty. |
| `FLOWPILOT_PROBE_HOST` | `healthcheck.railway.app`. |
| `FLOWPILOT_DATABASE_URL` | `${{Postgres.DATABASE_URL}}` for a service named `Postgres`. Verify the referenced URI uses the private Railway hostname. |
| `FLOWPILOT_DATABASE_POOL` | `disabled` for the low-traffic staging experiment. See [0033](0033-idle-database-connections.md). |
| Identity variables | Use the placeholders below for the anonymous smoke check. Configure a compatible provider and register the exact callback for live sign-in. See [browser sign-in](0016-browser-login.md). |

For synthetic staging without sign-in, set
`FLOWPILOT_OIDC_ISSUER=https://identity.invalid`,
`FLOWPILOT_OIDC_AUDIENCE=flowpilot-synthetic`, and
`FLOWPILOT_OIDC_JWKS_URL=https://identity.invalid/jwks`. Leave
`FLOWPILOT_LOGIN_*` unset. The anonymous smoke check exercises the app routes
without contacting an identity provider.

The app and Alembic share the same URL parser. A standard `postgresql://` URI
selects psycopg and keeps the original credentials and connection options.
Configure service variables in Railway, and give the web service access to
only the needed database and identity settings. Keep the database on the
private network with public TCP access disabled. Limit Railway's GitHub app
access to the FlowPilot repository. See [Railway PostgreSQL](https://docs.railway.com/databases/postgresql)
and [GitHub autodeploys](https://docs.railway.com/deployments/github-autodeploys).

For example, HTTP `GET /readyz` with Host `healthcheck.railway.app` can check
the database revision. The same path on the public hostname returns 404.
Application routes still require the exact browser hostname and effective
HTTPS. The probe hostname selects a route. Private networking and the Railway
edge determine which requests can reach it.

## Staging and pilot checks

- Use the [Railway-only mode and public smoke check](0035-railway-direct-pilot.md).
  Keep the environment dedicated to FlowPilot and trusted PostgreSQL. Verify
  the actual Host, forwarding headers, and access paths with synthetic data
  before allowing real sign-in.
  [Public networking](https://docs.railway.com/networking/public-networking/specs-and-limits)
  · [Railway's proxy guidance](https://station.railway.com/questions/fastapi-uvicorn-trusted-proxy-configura-9c06fa12).
- Confirm the real health check reaches the expected host and the public host
  returns 404 for both probe paths. Exercise a failed readiness check and check
  that the previous deployment continues to serve traffic.
- Check Railway HTTP logs with a synthetic callback query before enabling real
  sign-in. Verify that login credentials and OAuth codes stay out of logs,
  redirects use the canonical origin, cookies are Secure, and two accounts
  cannot read each other's private workspace records.
  [Railway HTTP logs](https://docs.railway.com/observability/logs).
- Enable Serverless on the web service and deploy before measuring cold starts
  and usage. Check whether the service sleeps between visits with pooling
  disabled. Keep a short demo and screenshots
  for times the app is unavailable. Check what data persists when the trial
  ends before asking anyone to rely on it.
  [Railway free plan](https://docs.railway.com/pricing/free-plan)
  · [Railway trial](https://docs.railway.com/pricing/free-trial)
  · [Railway sleep behavior](https://docs.railway.com/deployments/serverless).

Local checks cover escaped credentials and connection options, readiness against
migrated PostgreSQL, the separate health hostname, rejection of duplicate Host
headers, and the existing hosted sign-in flow. The Linux container smoke test
used a disposable PostgreSQL schema and the standard URL. The probe returned
503 before migration and 200 afterward. The public host received 404 for
`/readyz` and a forged HTTPS forwarding header did not pass the app's gate.
Verify the Railway edge and a compatible identity provider in synthetic staging.
