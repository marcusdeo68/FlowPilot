# Implementation 0028 — Signed-in workspace access

Open **Workspace access** to see your role in the current workspace and your
registered FlowPilot user ID. An owner can view active and inactive members and
recent access history. An owner with write scope can grant a role to a registered
synthetic user, update roles, remove access, or reactivate a former member.
For example, a teammate can share their own user ID, and an owner can enter it
and select Observer to give them read access to workspace-visible items.

The browser uses the existing same-origin membership routes and gets the
current user ID through `/api/v2/me`. It includes the tab's session token so a
changed cookie cannot load a successor session's data into the old page. The
server still resolves active stored membership and requires owner privilege for
roster and history. Writes also require write scope and CSRF. No schema change
is required.

Membership edits submit the exact row version plus the requested role and active
state. The workspace lock protects the last active owner across simultaneous
writes. A concurrent or unconfirmed change reloads access details before
another submission. A successful self-demotion clears the privileged view. A
self-removal discards that workspace and refreshes the accessible list. Recent
history identifies the actor, target, old and new state, time, and version.
The view displays up to 100 memberships and 20 history entries at a time.

Chromium exercises grants, role changes, removal and reactivation, stale
versions, last-owner protection, self-demotion and removal, read-only access,
workspace switches, and replacement browser cookies. See [STATUS](../STATUS.md)
for verification. The existing direct grant is for registered synthetic users
on loopback. Recipient-consented invitations and delivery are future work.
