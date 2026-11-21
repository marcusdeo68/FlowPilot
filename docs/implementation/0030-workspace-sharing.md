# Implementation 0030 — Workspace sharing

Open **Work items** and choose **Share with workspace** on a private task or
scheduled event you created. The review names the workspace and displays the complete
saved title and description, status, due date or exact event schedule, and any
evidence visible to fellow members. For example, review a private workshop task
and its previously approved evidence summary, then confirm. An observer can
find the task in **Shared work** after refreshing. **My private work** shows the
author's private items.

The browser requests an author-only preview. PostgreSQL locks the same work row
used by field edits and evidence linking so the returned version, work fields
and evidence projection agree. The browser sends that version to the existing
share endpoint. It rechecks the creator, membership, visibility and version
before changing visibility and appending audit in one transaction. Closing the
review leaves visibility untouched. A conflict or unconfirmed response requires
refreshing and opening a fresh review.

Sharing publishes the canonical fields, metadata and history to current and
future active members. Existing write-role rules apply to status changes. Edits
to shared work stay visible. Source records and private linked evidence retain
their access checks. Evidence already approved for the workspace appears with
the approved summary or excerpt. Use the preview to review any canonical task
text previously copied from a synthetic source. The current share operation is
permanent. This increment uses the existing schema and synthetic workspace.

The visibility filter applies before cursor pagination, so older shared rows
remain discoverable even behind many private records. PostgreSQL tests cover
filtered cursors, exact evidence projection, and version-bound confirmation.
Chromium checks closing without sharing, a stale preview, exact task and event
content, and observer visibility in a separate session. See [STATUS](../STATUS.md)
for verification. Next, improve task organization and operational controls for
a live pilot.
