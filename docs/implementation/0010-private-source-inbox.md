# 0010 — Return to a private manual-source inbox

The workspace API now lists the caller's own manual sources. A user who closed
the client after capturing a note can find it again and see whether they have
already suggested, accepted, or dismissed a task. Reading the list never creates
a suggestion. It requires verified read scope and active stored membership.

## Request and response

Call `GET /api/v2/workspaces/{workspace_id}/sources?limit=20`. Each row contains
the source ID, summary, capture timestamp, and either `review: null` or a review
ID and state. For example, a source with summary “Workshop outline” can appear
with a pending review. Open the source by ID for its excerpt or open the proposal
by ID for the editable title, due date and version. Listing does not return
excerpts, references, account identities, or accepted task contents.

Results run newest first. If `next_after` is a UUID, use it as the `after`
parameter on the next request; null means this traversal has reached the end.
The default page holds 50 entries and the maximum is 100. An unknown or
inaccessible cursor returns the same 404. Refresh the first page to see arrivals.

## Why pages use a source as their boundary

With page numbers, adding a source to the top can move the last row of page one
onto page two. This API instead asks for rows **older than the last row shown**.
A timestamp alone isn't enough: two sources may have identical capture times.
The source UUID breaks the tie. The server resolves the cursor under the same
owner and workspace filters as the page, then compares the pair of timestamp
and UUID. Supplying a cursor does not grant access to its source.

The query asks for one extra row to detect whether another page exists without
counting a person's entire inbox. A left join includes a proposal when one
exists; opening the inbox with no proposals still shows all the caller's sources.
Proposal edits do not reorder sources. Pagination is a live traversal, not a
snapshot across requests: a later commit with an older sort position can appear
on a later page. For now, manual sources have no edit/delete endpoint.

## Storage and verification

Migration `0004_source_inbox` adds an index on workspace, owner, timestamp and
source ID. A normal PostgreSQL B-tree can traverse that order backwards after
matching workspace and owner. Downgrading drops only this index. This is a
development migration; online index deployment for a large live table would
need a separate operational plan.

`tests/test_source_inbox.py` uses real PostgreSQL and signed HTTP requests.
It checks equal timestamps, a new arrival between pages, unauthorized pivots,
bounded limits, omitted private details, and proposal state before and after
review. Local verification: 91 passed, including Chromium; the 43 PostgreSQL
checks require the separate real-database job. The legacy dashboard does not yet
use it. Next: put the verified workflow through an interactive client with
synthetic data and exercise the full capture-to-review path.
