# Implementation 0034 — Authenticate the pilot's HTTPS proxy

The Worker is an optional gateway. The current pilot uses
[Railway-only ingress](0035-railway-direct-pilot.md).

The optional proxy mode lets the app accept a request after verifying a
credential from a controlled gateway. This addresses Railway's lack of a
published stable ingress peer range. The Cloudflare Worker in
[edge/worker.mjs](../../edge/worker.mjs) is the gateway candidate. The free
`workers.dev` address supports hobby projects. FlowPilot has exercised the
gateway locally. Cloudflare and Railway deployment remain pending.
[Workers hobby routing](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/)
· [Railway proxy guidance](https://station.railway.com/questions/fastapi-uvicorn-trusted-proxy-configura-9c06fa12)

## Staging settings

- Deploy the Worker from `edge/worker.mjs` with a current Workers compatibility
  date. Use its exact HTTPS address for `FLOWPILOT_BROWSER_ORIGIN` in both
  services, and the exact Railway HTTPS address for the Worker's
  `FLOWPILOT_UPSTREAM_ORIGIN`. Set `FLOWPILOT_PROXY_UPSTREAM_HOST` on Railway to
  the matching hostname without the scheme.
- Generate a random 32-byte secret and store its lowercase hex encoding as
  `FLOWPILOT_PROXY_SECRET` in both services. Use a Worker secret and a Railway
  service secret. The gateway needs only its own deployment rights and the
  shared secret. It handles browser requests and cookies and needs zero
  database, workspace, or OAuth provider credentials.
  [Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
- Retain `FLOWPILOT_PROBE_HOST=healthcheck.railway.app` and leave
  `FORWARDED_ALLOW_IPS` empty. Use Railway's HTTPS URL for the upstream
  hop, with certificate validation on the Worker fetch. Keep PostgreSQL
  private and application access logs disabled as in [0032](0032-railway-pilot.md).

For example, a login POST to the Worker's address is sent to the fixed Railway
host with the shared credential. The Worker replaces any caller-supplied
credential and leaves browser Origin intact. The backend requires one exact
upstream Host and one valid credential. It builds the application request
using the configured public hostname and HTTPS, and removes the credential
before routing. Existing cookie, Origin, and CSRF checks still apply. Railway's
health requests take a separate path using the dedicated probe hostname.
Direct requests to Railway app routes receive 404. The Worker passes redirects
and session cookies back to the browser and uses manual redirect handling and
no-store so the credential stays on the upstream hop.
[Workers request behavior](https://developers.cloudflare.com/workers/runtime-apis/request/)

## Verification and next step

Local tests cover invalid configuration, missing or duplicate credentials,
spoofed forwarding headers, the scoped readiness probe, and the existing
synthetic PostgreSQL login and cross-origin write protection through the
authenticated ingress. Node tests cover the gateway's pinned HTTPS destination,
manual redirects, cookies, and failure before fetch. Run
`node --test edge/worker.test.mjs` for the gateway tests.

Cloudflare enables observability for newly created Workers. Before configuring
real sign-in, disable invocation logs or disable observability. Keep traces
and request exports away from real OAuth callbacks.
[Cloudflare Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)

In staging, exercise both platform hops with synthetic data. Verify header
delivery, the actual Railway Host, the browser redirect, secure cookies, no
secret disclosure, probe behavior, and rejection of direct app requests.
Confirm that callback query values and request headers containing credentials
are absent from operator-accessible logs at both services before enabling
real sign-in. Coordinate secret rotation between services. The gateway sees
application traffic and should remain under the project owner's control.
