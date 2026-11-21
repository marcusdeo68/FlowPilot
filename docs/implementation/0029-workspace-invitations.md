# Implementation 0029 — Recipient-consented workspace invitations

Open **Invitations** after signing in with a synthetic account. Register your
profile to get a FlowPilot user ID even if you have zero workspaces. An owner
enters that ID and the offered role under **Workspace access**. For example,
an owner can offer Observer access to a synthetic workshop workspace. The
recipient sees the workspace name, exact role and deadline and can accept or
decline. An owner can revoke a pending offer. Pending offers create no membership.

Registration uses the verified issuer and subject and the same idempotent user
insert as workspace creation. The recipient endpoint scopes offers to that
registered identity. The owner endpoint checks active stored owner membership
and a registered same-issuer target. Offers are pending for up to seven days.
The browser displays up to 20 outgoing or incoming invitations.

All offer writes take the workspace lock used for membership changes. A decision
locks the invite row and checks its exact version and expiry after waiting. Accept
rechecks the original inviter's active owner role and membership version before
inserting a new membership. The invitation decision, audit entry, membership,
and membership audit commit together. Failed, stale and ambiguous responses
refresh authoritative data before another UI attempt. Acceptance never overwrites
an existing membership and reactivation remains an explicit owner operation.

Apply `alembic upgrade head` to reach `0009_workspace_invitations`. A downgrade
preserves existing work and membership data and refuses to discard recorded
invitations. The signed synthetic direct-grant API continues to support its
existing callers. Use the consent flow in the browser. Email delivery, live
account integration, rate limits and retention remain future work.

PostgreSQL verifies identity isolation, expiry, stale decisions, concurrent
revocation, and audit rollback. Chromium uses separate owner and recipient
sessions to exercise profile registration, offer, decline, revoke, stale
acceptance and successful acceptance. See [STATUS](../STATUS.md) for results.
