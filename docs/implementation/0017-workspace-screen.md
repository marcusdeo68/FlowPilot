# Implementation 0017 - Signed-in workspace screen

The verified workspace app serves a browser shell at `/api/v2/workspace` when
browser sessions are enabled. The sign-in success page links to it. A signed-in
user can select a listed workspace, create one, load more work items, and sign out.

The shell contains no user data. It checks the session before requesting the
workspace list and submits creation and sign-out with the session's CSRF token
held in memory. The browser carries the existing HttpOnly cookie. Existing
services still authorize each workspace request against stored membership and
work visibility. The shell renders text and uses fixed same-origin assets with
a restrictive content security policy.

For example, a signed-in user with no memberships can create a workspace named
Planning and see its empty work list. Work pages fetch twenty records at a time
using the cursor returned by the API. Switching workspaces resets the list and
invalidates older responses. Access errors clear the active list. Sign-out or
session expiry clears the displayed workspace data and in-memory token. A user
can explicitly clear an invalid cookie before signing in again.

The list endpoint returns up to 100 workspaces. A workspace just created remains
selectable in the current view even if it falls beyond that list.
Work items are browsable by title, kind and status. This slice uses synthetic
data and keeps the SQLite demo separate. Next, build an authenticated manual
task or private review workflow on this screen.

Focused Chromium tests cover synthetic HTTPS sign-in, workspace creation, reload,
pagination, literal rendering, sign-out, server expiry and delayed responses from
an older selection. Ruff, Pyright, JavaScript syntax and the source and wheel
builds passed locally. The wheel includes all three screen assets. See
[STATUS](../STATUS.md) for tracked fixes and the pull request for full verification.
