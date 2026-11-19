# Implementation 0016 - Opt-in authorization-code login

## Behavior and request path

The separate workspace API can optionally serve a sign-in flow. It remains
disabled without explicit login and browser configuration. No real identity
provider or personal account is connected.

1. GET `/api/v2/login` displays a form. POST requires exact local Origin and
   acceptable Fetch Metadata, with no existing session or Authorization header.
   It creates a five-minute transaction, sets the verifier in an HttpOnly,
   host-only, SameSite=Lax cookie at `/api/v2/login`, and redirects to the
   configured authorization endpoint with state and S256 challenge.
2. GET `/api/v2/login/callback` validates bounded, duplicate-free state, issuer
   and code/error fields, exact request origin and verifier cookie. It presents
   an escaped, script-free Continue form. Callback GET never changes cookies or
   login state, including when validation fails. Bounded OAuth response
   extensions and provider diagnostics are ignored, including `error_uri`.
3. POST `/api/v2/login/complete` rechecks Origin, metadata, form, issuer, verifier
   and absence of session/auth credentials. It consumes the transaction once,
   exchanges the code, verifies the token and client, then issues the existing
   opaque Strict session. Completion clears the pending cookie only after the
   request passes the Origin check.
4. HTTPS exchange uses a direct TLS connection without redirects, inherited
   proxies or retries. TCP/TLS socket operations use five-second timeouts. After
   connection, a separate five-second deadline covers request, headers and body;
   a watchdog shuts down the TLS socket even if header bytes arrive slowly.
   Chunked reading caps the response at 32 KiB of duplicate-free JSON.
   Errors are generic. Codes/verifiers/tokens are not persisted. Access tokens
   and verifiers never enter page content; the short-lived code appears only in
   the callback URL and escaped form. The verifier travels only in its HttpOnly cookie.
5. Existing RS256 token verification remains strict. Login supplies an optional
   expected client ID, matched after signature and claim validation. The identity
   result shape remains unchanged. Both FlowPilot
   read/write scopes are required for manual workspace/task operations; stored
   membership still decides authorization. Login does not provision a workspace.

## Why a completion POST

A cross-site provider redirect can omit an existing Strict session cookie. Direct
issuance on callback GET could overwrite another tab's session. The callback
document's same-origin form POST restores Strict cookies, allowing rejection of
the session present on that request. Hidden fields remain untrusted and are
revalidated. No script or external asset runs on callback pages. All pages use
no-store, frame denial and restrictive CSP. The form pages use `strict-origin`
referrers, which preserves the Origin header on Chromium form submissions and
omits the callback path and query from the referrer. Only the initial page's
form-action permits the trusted authorization origin, since Chromium also applies
that policy to the initiation redirect. Callback forms submit only to FlowPilot.

## Configuration and provider compatibility

After migration 0006 and existing identity/browser/database configuration:

```powershell
$env:FLOWPILOT_LOGIN_CLIENT_ID = '<reviewed public OAuth client ID>'
$env:FLOWPILOT_LOGIN_AUTHORIZATION_URL = 'https://reviewed-issuer.example/authorize'
$env:FLOWPILOT_LOGIN_TOKEN_URL = 'https://reviewed-issuer.example/token'
uv run --locked uvicorn flowpilot_api.workspace_api:create_workspace_app --factory --host 127.0.0.1 --port 8001 --no-access-log
```

These are placeholders. Partial/empty settings fail startup. HTTPS endpoints must
share the issuer origin and have no credentials, query or fragment. Register the
exact `<FLOWPILOT_BROWSER_ORIGIN>/api/v2/login/callback` URI. The provider must
support a public client, PKCE S256, query-mode responses with matching RFC 9207
`iss`, and the strict RFC 9068 access-token profile in [0007](0007-verified-workspace-api.md),
including configured audience/client, scopes and short lifetime. Audience selection
is configured at the provider; no vendor-specific audience parameter is added.
No ID-token login, client secret, discovery, userinfo or refresh-token flow exists.

Only `flowpilot:read flowpilot:write` are requested, allowing manual workspace
onboarding/task operations. No Gmail, Calendar, Slack, Keep or outbound provider
scopes are requested. Review actual provider capabilities/consent/privacy before
live use. Keep all data synthetic and listeners loopback-only.

Disable HTTP access logs as above: callback query strings contain short-lived
code/state. Do not collect those URLs in logs, traces or support reports. App
headers cannot sanitize server logs or erase browser history.

## Example and validation

A synthetic browser starts login, visits a synthetic provider, returns and clicks
Continue. One exchange supplies a signed test token; an opaque session is issued.
Reloading GET session recovers CSRF, and membership controls work access. Replay
cannot exchange again. A session created while visiting the provider must survive
callback/completion, with replacement denied.

The full local suite passed 251 tests without skips: 147 ordinary, 87 PostgreSQL,
and 17 Chromium. Socket tests exercise a valid `Connection: close` response and
slow headers and body. Both new Chromium tests use an ephemeral HTTPS provider on
`localhost` and the workspace API on `127.0.0.1`, so Chromium follows an actual
cross-site redirect. The browser-only fixture trusts its temporary certificate
and the app exchanges synthetic signed tokens through the test seam. Review
findings and fix evidence are recorded in [STATUS](../STATUS.md).

## Limits and next increment

No live provider is configured. Provider errors or ambiguous exchange failures
require a fresh attempt; consumed codes are never retried. Pending retention and
audit limits remain as in [0015](0015-login-transactions.md). Requests already
admitted can finish; browser-wide concurrent login serialization is not implemented.
Cookie checks cover credentials on the current request. Rate limits, deployment,
recovery, invitation consent and provider-wide logout remain future work.
OS DNS resolution is synchronous and cannot be interrupted by the socket budget;
this is not a hard five-second wall-clock guarantee for all connection phases.

Next: provider compatibility review and authenticated workspace onboarding/selection
with synthetic browser coverage. Real provider data and external writes remain
gated by the complete access model.

References: [OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749.html),
[OAuth security practice](https://www.rfc-editor.org/rfc/rfc9700.html),
[issuer binding](https://www.rfc-editor.org/rfc/rfc9207.html),
[PKCE](https://www.rfc-editor.org/rfc/rfc7636.html).
