# Implementation 0035 — Railway-only pilot

The pilot uses the Railway-generated HTTPS URL and a dedicated environment
containing only FlowPilot and its trusted PostgreSQL service. The optional
[authenticated Worker gateway](0034-authenticated-pilot-ingress.md) is available
for other deployments. No additional account is required for the pilot ingress.

## 1. Railway HTTPS ingress

Follow [Railway setup](0032-railway-pilot.md). Set `FLOWPILOT_RAILWAY_EDGE=1`,
`FLOWPILOT_HOSTED=1`, `FLOWPILOT_BROWSER_ORIGIN` to the exact Railway HTTPS
origin, and `FLOWPILOT_PROBE_HOST=healthcheck.railway.app`. Leave
`FORWARDED_ALLOW_IPS` empty. Remove the Worker proxy settings if present.
Keep public TCP access disabled for both services.

Railway's public edge terminates TLS and supplies the forwarded scheme. The app
requires exactly one public Host and one `X-Forwarded-Proto: https` value before
restoring the HTTPS scheme. It strips forwarding metadata before routing.
Browser Origin, cookies, and application authorization continue to apply.
The Railway health Host can reach the two health endpoints without that header.
[Railway public networking](https://docs.railway.com/networking/public-networking/specs-and-limits)
· [Railway probe behavior](https://docs.railway.com/deployments/healthchecks)

Every service that can reach the app privately is inside the trust boundary.
For example, an untrusted workload placed alongside the app could supply
the same header as the public edge. The app cannot independently identify
Railway's proxy. Verify the dedicated topology in staging and keep other
workloads outside it. [Railway proxy guidance](https://station.railway.com/questions/fastapi-uvicorn-trusted-proxy-configura-9c06fa12)

## 2. Public staging smoke check

From the project environment, run:

```text
python -m flowpilot_api.check_railway https://<service>.up.railway.app
```

The command uses credential-free GET requests and verifies TLS. It checks
the canonical workspace redirect, workspace HTML, anonymous session rejection,
and 404 responses for the two private health paths. It reports only unexpected
statuses or headers and exits with status 1 on failure. The command leaves
redirects unfollowed and does not send credentials or write data.
If the first request returns 502 after waking a sleeping service, wait for it
to start and run the check again. [Railway sleep behavior](https://docs.railway.com/deployments/serverless)

Local tests exercise exact and duplicate headers, probe isolation, and the
synthetic sign-in and CSRF flow through the Railway mode. They also exercise
the smoke checker with successful responses and a public readiness leak.
The [hosted image rehearsal](0046-hosted-image-rehearsal.md) checks the
packaged app before and after migrations.
Run the command against synthetic staging and verify callback logs and
sign-in separately before inviting friends.
