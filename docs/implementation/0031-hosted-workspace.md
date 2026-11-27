# Implementation 0031 — Hosted workspace foundation

This note documents the generic container and the original AWS load balancer
design. Follow [0032](0032-railway-pilot.md) for the selected Railway pilot.

The signed-in workspace can run behind an HTTPS load balancer on a configured
hostname. Set `FLOWPILOT_HOSTED=1` and `FLOWPILOT_BROWSER_ORIGIN` to the canonical
origin, for example `https://staging.flowpilot.example`. Hosted mode accepts one
lowercase DNS hostname on the standard HTTPS port. Use an origin without an
explicit port, path, or trailing slash. The root URL redirects to the workspace.

The load balancer terminates TLS and preserves the public Host. At that edge,
replace any client-supplied `X-Forwarded-Proto` with a single header carrying the
actual client scheme. Uvicorn accepts this header only from its trusted immediate
peer. The app checks the effective HTTPS scheme and exact Host before routing requests.
Exact `GET /healthz` and `GET /readyz` support private probes with the target IP
as Host. Health reports process availability and readiness checks the database
revision. The browser continues to check Origin and CSRF on cookie writes. The
configured origin supplies the OAuth callback and binds the session cookie.
[AWS forwarded headers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/x-forwarded-headers.html)
and [AWS health probe behavior](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-troubleshooting.html)
describe the load balancer contract.

Build the image from the repository root:

```text
docker build -t flowpilot-workspace .
docker run --rm flowpilot-workspace alembic heads
```

The image uses locked dependencies, launches the workspace API as a non-root
user on port 8000, and includes Alembic and the UI assets. Provide these settings
through the container service or its secret store:

- `FLOWPILOT_BROWSER_ORIGIN` with the staging HTTPS origin. The image enables
  `FLOWPILOT_HOSTED=1` by default.
- `FLOWPILOT_DATABASE_URL` with the PostgreSQL connection string. Use verified
  TLS and the appropriate database CA in staging.
- `FLOWPILOT_OIDC_ISSUER`, `FLOWPILOT_OIDC_AUDIENCE`, and `FLOWPILOT_OIDC_JWKS_URL`
  for the verified access token. For browser sign-in, configure the three login
  settings and register the exact callback as described in
  [0016](0016-browser-login.md).
- `FORWARDED_ALLOW_IPS` with the trusted proxy IPs or CIDRs, when TLS terminates
  before Uvicorn. The image defaults to an empty list. Use a private app target
  reachable only by the load balancer and restrict the list to its peers. Keep
  wildcard proxy trust disabled. Route the configured host on the HTTPS listener
  and redirect HTTP at the load balancer. Use a higher-priority fixed 404
  listener rule for `/healthz` and `/readyz` so public probes stop at the edge.
  The load balancer's own target probes go directly to the app.
  See [AWS listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-rules.html).

Run `alembic upgrade head` as a one-off task using the image and migration
database credentials before starting or updating app replicas. Give the app its
own database credentials. Use `/readyz` as the target health path to check schema
readiness. The load balancer can still route traffic if all registered targets
are unhealthy, so complete migrations before app startup. Uvicorn access logs
are disabled in the image. Configure edge logging to protect OAuth callback
query strings as well.
See [AWS target health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html).

Tests cover the actual Uvicorn proxy middleware, the hosted OAuth callback and
session with synthetic identity and PostgreSQL, and the existing loopback flows.
The next increment is synthetic staging behind the actual load balancer with a
compatible identity configuration. Check that public probe paths return 404,
target health checks succeed, and client-supplied forwarding headers have no
effect. Live account access and provider data depend on that verification and
the remaining operational controls in [SECURITY](../SECURITY.md).
