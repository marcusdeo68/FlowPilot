# Implementation 0012 - Bounded browser sessions

Status: implementation and independent verification in progress. No live identity
provider, sign-in screen, dashboard migration, or external account is added.

## Behavior and request path

The separate workspace API can optionally exchange a compatible, verified bearer
access token for an opaque browser session. Set `FLOWPILOT_BROWSER_ORIGIN` to its
exact loopback origin (for example `http://127.0.0.1:8001`) and apply migration
`0005_browser_sessions`. Without this setting, session routes and cookie
authentication are disabled. Empty or noncanonical settings fail startup. Use
`localhost` or `127.0.0.1`, omit trailing slashes and default ports, and include
nondefault ports. The configured origin must match the API's own origin.

1. `POST /api/v2/session` requires a verified bearer token with `flowpilot:read`,
   an exact Origin header, and no existing session cookie.
2. The service generates 256 random bits, stores only their SHA-256 digest with
   verified issuer/subject/scopes, API audience, browser origin and absolute expiry,
   and commits the session and creation audit together. No user is provisioned.
3. The response sets a host-only HttpOnly, SameSite=Strict cookie at `/api/v2`.
   HTTPS sets Secure. Omitting Secure is permitted only for explicitly configured
   loopback HTTP development. Reverse proxies and network deployment are unsupported.
4. Cookie requests resolve identity server-side. Unsafe methods require exact
   Origin and `X-CSRF-Token`; safe reads reject foreign supplied Origin or Fetch
   Metadata. Same-origin GET may omit Origin. Membership, role, privacy and
   record-version checks still happen inside existing business services.
5. `GET /api/v2/session` returns absolute Unix expiry and a stable CSRF token so a
   page reload can recover it. The token is an HMAC keyed by the opaque cookie;
   knowing the database digest does not reveal either credential. The raw cookie
   is never returned in JSON. Responses are no-store; there is no permissive CORS.
6. `DELETE /api/v2/session` requires exact Origin and, for an active session,
   its CSRF token. Revocation and audit commit before cookie deletion. Repeated
   logout is safe. Missing, malformed, expired or revoked cookies can be cleared
   with exact Origin alone because they cannot authorize anything; this branch
   does not mutate persisted state. Storage outages return 503 and do not falsely
   report successful logout.

Bearer-plus-cookie and duplicate credentials are rejected. Sessions are bound to
issuer, audience and origin, including port. Cookies themselves are not port-bound,
so requests from another localhost port still need origin/fetch checks. The legacy
SQLite application remains separate.

## Why this structure

`browser_sessions.py` owns persistence, expiry and atomic lifecycle audit;
`session_routes.py` owns browser request/cookie rules. The existing identity
dependency selects a single credential type and leaves authorization to the same
services. Server-side revocation avoids waiting for a signed cookie to expire.
An append-only audit records identifiers, operation and time without provider
tokens or message content. Concurrent revokes produce one event.

Session lifetime never exceeds the verified token's expiry, even inside JWT clock
skew allowance. There is no refresh, sliding extension or remembered-login mode.
Logout prevents subsequent authentication; operations already authenticated may
finish. Membership removal independently blocks later workspace operations.

## Synthetic example

A test identity has `flowpilot:read flowpilot:write` and expires in five minutes.
The browser exchanges its signed token once, receives an HttpOnly cookie, and
keeps the returned CSRF value in memory. A workspace creation sends that CSRF
value in `X-CSRF-Token`; the browser supplies Origin and the cookie. Reloading
recovers CSRF through GET session. Logging out revokes the server row; replaying
the old cookie returns 401. None of these steps sends email or approves an action.

The automated browser harness performs this sequence with an ephemeral RSA key,
real PostgreSQL and Chromium. It is test-only, not a token-pasting login screen.
To run locally, configure the dedicated `_test` PostgreSQL database described in
[0005](0005-postgres-work-storage.md), install Chromium as in
[0006](0006-browser-regressions.md), then run:

```powershell
$env:FLOWPILOT_BROWSER_TESTS = '1'
.venv\Scripts\python.exe -m pytest -q tests/test_browser_sessions.py tests/test_session_browser.py
```

## Validation evidence

Initial local checks: 119 tests passed (including 13 existing Chromium workflows),
53 PostgreSQL-dependent checks skipped because no local test database is running.
This includes 17 new ordinary session checks. Pinned Pyright reports zero errors.
CI's browser job supplies PostgreSQL for two new authenticated Chromium workflows.
Full candidate CI and independent audit are required before sign-off. Existing
tests are retained; PostgreSQL's dedicated job excludes browser-marked tests because
those execute with Chromium in the browser job.

## Limitations and next increment

A compatible bearer token is still required. Provider selection/configuration,
authorization-code/PKCE sign-in and callback, frontend integration, invitation
consent, idle timeout, rate limits, identity-provider logout/revocation signals,
and HTTPS deployment controls remain future work. Logging out this session does
not revoke its original bearer token or other sessions. No real provider data is
permitted yet.

Expired/revoked session rows and audit history are retained. There is no cleanup
worker or retention policy in this increment; expiry is enforced during every
resolution without deleting audit attribution. This is a local synthetic-data
foundation, not production session management. Next: review a compatible identity
provider and implement complete sign-in/callback before wiring the workspace UI.

Reference: [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
