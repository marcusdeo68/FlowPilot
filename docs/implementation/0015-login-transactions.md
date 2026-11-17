# Implementation 0015 - Single-use login transactions

## Behavior and request/data path

`LoginTransactions` is an internal service for the next browser login adapter.
It introduces no HTTP routes, provider requests or authentication bypass.
`begin()` generates independent 256-bit state and PKCE verifier values, inserts
their SHA-256 digests with trusted configuration, and appends a creation audit
event in the same PostgreSQL transaction. The returned frozen `PendingLogin`
hides both secrets from its representation and exposes the S256 challenge.

The record binds issuer, API audience, OAuth client ID and exact callback URI.
The callback is derived from validated loopback `BrowserConfig.origin` plus
`/api/v2/login/callback`; this path is reserved, not currently served. Database
statement time fixes expiry at five minutes after creation. `consume(state,
verifier)` conditionally marks an unused matching record consumed and appends its
audit event atomically. Unknown, mismatched, expired, malformed and replayed
inputs fail. Concurrent valid consumption has exactly one winner.

## Why this structure

State correlates a callback with an initiated login; PKCE binds code redemption
to the verifier. The future adapter will retain the server-generated verifier in
an HttpOnly callback cookie, while PostgreSQL stores only its digest. The S256
challenge is the base64url encoding of that digest. Neither raw secret, an OAuth
code nor a provider token is persisted here. The result repr hides secrets to
reduce accidental diagnostic exposure; explicitly logging secret fields remains
unsafe. Do not serialize this result directly into API responses or logs.

Row locking followed by conditional UPDATE avoids a read-then-write race and
evaluates expiry after lock acquisition. Independent review found FP-014: a single
UPDATE could evaluate its expiry predicate before waiting on an unchanged locked
row, then consume after expiry. A new regression reproduced this before the fix.
Retaining a consumed record
allows append-only lifecycle audit with foreign-key attribution. Audit failure
rolls back creation/consumption, so callers cannot receive success without history.
SQL values are bound; storage failures expose a generic service exception.

## Concrete example

A synthetic login starts on `http://127.0.0.1:8001`. Its state and challenge will
eventually go to a reviewed authorization endpoint; the verifier stays in the
browser cookie. The callback must supply the matching state and cookie verifier.
Consumption succeeds once and returns no identity. Only then can a future adapter
exchange the code using that verifier and invoke the unchanged strict access-token
verifier before issuing a browser session. A copied state without the verifier,
or a callback on port 8002, cannot consume this record.

## Validation

Tests cover the published S256 example, independent generation, secret-free storage
and repr, fixed expiry, all configuration bindings, malformed/wrong secrets,
replay, concurrent consumption, audit immutability/rollback, storage failure and
migration downgrade/re-upgrade. Final execution evidence belongs in [STATUS](../STATUS.md).

Independent verification over base `46cb903`: eight focused tests passed; full
PostgreSQL/Chromium-enabled pytest passed 189 tests without skips (113 ordinary,
61 PostgreSQL, 15 Chromium). FP-014 first reproduced as a failing regression and
passed after the lock-first fix. Quality/build evidence and exact-candidate CI
are recorded with the final PR; no existing test was weakened or removed.

Migration `0006_login_transactions` adds two tables and advances readiness's
expected revision. Apply migrations explicitly before starting the workspace API;
no migration runs automatically at startup. Existing session/token rules remain.

## Limits and next increment

This is a complete transaction-storage slice, not browser sign-in. Provider
compatibility review, trusted authorization/token endpoints, bounded code exchange,
callback parsing, token verification, session issuance and browser tests come next.
No new provider or scopes are selected. The strict access-token profile in
[0007](0007-verified-workspace-api.md) still applies. Provider-specific OAuth
capabilities must be reviewed before connecting a live account.

The callback cookie must permit a top-level provider redirect (normally SameSite
Lax), have an exact narrow path, and be cleared on completion/failure. Existing
Strict session cookies are a separate credential. HTTP initiation must check
origin, prevent unsolicited login and avoid overwriting an active session; this
service alone cannot enforce browser request protections. An exchange failure
after consumption requires a new login attempt, never replay of the same attempt.
No identity or workspace mutation is authorized by consumption.

Expired/consumed hashes and audit remain until a reviewed retention mechanism is
implemented. Request limits, deployment controls, live accounts and provider data
remain outside this local synthetic increment.

References: [PKCE and S256](https://www.rfc-editor.org/rfc/rfc7636.html),
[OAuth security best current practice](https://www.rfc-editor.org/rfc/rfc9700.html).
