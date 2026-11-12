# Implementation 0007 - Verified workspace API boundary

Status: merged in PR #6 after all six CI jobs passed for commit 11c0ca5 in
run 43227745975. Verification: 76 ordinary/backend/token tests, 20 real PostgreSQL
and signed-token HTTP tests, and six Chromium tests passed. Local full suite:
82 passed, 20 PostgreSQL tests explicitly skipped. Lint, formatting, JavaScript
syntax, and wheel/source builds passed on Windows/Linux Python 3.11/3.12.
This is a separate local API factory. No real identity account is connected.

## What changed

`workspace_api.create_workspace_app` exposes the PostgreSQL work/source/evidence
services under `/api/v2/workspaces/{workspace_id}`. It does not mount `/api/v1`
or the unauthenticated dashboard. This prevents the new API from accidentally
carrying the old unauthenticated write paths into its own application surface.
The existing dashboard remains available through `flowpilot_api.main:app` and
remains synthetic-only. Neither application is ready for public deployment.

The new factory requires explicit PostgreSQL and identity configuration. Missing
configuration fails startup instead of bypassing authentication. Its readiness
check verifies the applied migration revision. API responses use no-store caching
and do not expose SQL error parameters or bearer tokens. No migrations run at startup.

## Identity contract, scopes, and provider boundary

This increment implements a strict subset of the RFC 9068 JWT access-token profile
using PyJWT/cryptography. It accepts RS256 signatures with an access-token `typ`,
an expected issuer and API audience, a key ID, and bounded identity claims. Tokens
must include issuer, audience, subject, issued-at, expiry, token ID, and client ID;
integer lifetimes are limited to 15 minutes with 30 seconds of clock skew.
Expired, future, unsigned/symmetric, wrong-audience, wrong-issuer, and identity-token
inputs are rejected. Tokens are bounded to 16 KiB. Identity identifiers also reject
blank values and control characters. Work/source text rejects NUL at validation
because PostgreSQL text cannot store it; callers get an input error instead of
reaching a database-driver failure.

The JWKS URL is trusted application configuration, HTTPS, and on the issuer's
origin. Token-supplied key URLs, inline keys, certificate URLs, and critical custom
headers are rejected. PyJWT retrieves only the configured JWKS endpoint with a
bounded timeout and cached key set. Unknown keys do not fall back to unverified
claims. Identity network failure returns 503; invalid tokens return 401.
Key fetching is serialized and throttled to one attempt per 30 seconds per process,
including failure backoff, so arbitrary unknown key IDs cannot each trigger network
I/O. A newly rotated key can therefore take up to that interval to become visible;
routine cached key sets last five minutes. Request/CPU rate limits are still needed.

Read operations require `flowpilot:read`; writes require both `flowpilot:read` and
`flowpilot:write`. These API scopes are additional capabilities, not workspace roles.
The verified issuer/subject maps to a stored user and active membership; user IDs,
roles, and workspace authority never come from request bodies or token role claims.
An observer with an owner-looking token role is still denied by stored membership.

No specific OAuth/OIDC provider is selected or connected. Before choosing one,
verify it can issue this access-token profile, audience, scopes, short lifetimes,
and RS256 JWKS; many providers' default ID or access tokens will not match it.
Do not assume a Google ID token or default Cognito token is accepted. A future
provider adapter may need a separately documented and tested token profile.
Login would request only identity and FlowPilot API capabilities; there are no
Gmail, chat, calendar, or sending scopes in this contract.

The only network behavior here is retrieving public signing keys from a trusted
identity endpoint. Tokens contain identifiers and scopes, so do not log tokens,
put them in URLs, or persist them in browser localStorage. The frontend session
design, PKCE/login callback, user/workspace provisioning, consent, logout/revocation,
and membership administration are not implemented in this increment.

## Concrete request path

A signed access token requests a task transition. HTTPBearer extracts the token;
`AccessTokenVerifier` verifies signature and claims and constructs a Principal.
The route checks API scopes, validates the command and version, and calls the
PostgreSQL service. The service resolves active membership, scopes and locks the
work row, checks visibility/lifecycle/version, and commits the status and audit
event together. A valid signature proves identity, not permission to another
workspace's records. A client changing the URL workspace UUID still gets denied.

Source sharing follows the same chain and requires source ownership. Explicitly
sharing a summary never makes the underlying source readable by a workspace owner.
The HTTP integration tests verify this boundary using real PostgreSQL and signed
ephemeral test tokens.

## Start the separate API after provider configuration

```powershell
$env:FLOWPILOT_DATABASE_URL = '<local PostgreSQL connection URL>'
$env:FLOWPILOT_OIDC_ISSUER = 'https://your-reviewed-issuer.example'
$env:FLOWPILOT_OIDC_AUDIENCE = 'your-api-resource-identifier'
$env:FLOWPILOT_OIDC_JWKS_URL = 'https://your-reviewed-issuer.example/path/to/jwks'
uv run --locked uvicorn flowpilot_api.workspace_api:create_workspace_app --factory --host 127.0.0.1 --port 8001
```

These are placeholders, not a configured sign-in flow. Users and memberships must
already be provisioned through trusted setup; there is no public signup endpoint
or self-granting workspace endpoint. Do not copy the test key resolver into a
running configuration. Test signing keys are generated in memory and never committed.

## Verification and remaining work

Unit tests verify actual RSA signatures, required claims, algorithm/type confusion,
scope parsing, issuer/audience checks, JWKS resolution, malformed/oversized tokens,
future and excessive lifetimes, and network failure. PostgreSQL HTTP tests check
missing/forged authentication, removed legacy routes, extra role fields, observer
and scope denial, wrong workspace/private resource access, version conflicts,
and source-owner-controlled evidence. The hosted results above verified the exact
merged source revision; no production identity provider was used.

This API remains on loopback. Before network deployment add request/rate limits,
trusted proxy/HTTPS/host
configuration, database runtime roles, retention/deletion and backups, and reviewed
provider/session setup. JWT verification alone is not deployment readiness.

## Local environment repair

Copy mode did not eliminate the checkout's recurring package-metadata file locks.
The disposable environment is now outside OneDrive at
`%LOCALAPPDATA%/FlowPilot/venv`, with a machine-local `.venv` junction so Cursor
tasks keep working. Preserved files remain under ignored `.tools/venv-backup-0007`
and `.venv-stale-0007`, alongside the prior `.tools/venv-backup-0006`; no project
source or Git history was removed. An attempted directory move partially moved
environment files before Windows denied removing some folders; the residual folder
was renamed and retained. A fresh external environment installed successfully.
Future checkouts can use ordinary `.venv` directories; do not commit machine paths.

References: [RFC 9068](https://www.rfc-editor.org/rfc/rfc9068.html),
[PyJWT usage](https://pyjwt.readthedocs.io/en/latest/usage.html).
