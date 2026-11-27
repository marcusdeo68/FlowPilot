# Implementation 0036 — Search work by title

Open **Work items**, enter part of a title, and choose **Search**. For example,
`budget` finds “Old Budget Review” even when it sits beyond the first page.
Search works in All work, Events, Shared work, and My private work.
**Clear search** returns to the unfiltered view. Today and Due tasks keep
their existing deadline lists.

The browser sends the applied term and page options in JSON to
`POST /api/v2/workspaces/{workspace_id}/work-page/search`. The route uses the
same read scope, server-side membership rules, and keyset pagination as the
work list. Cookie requests use the existing Origin and CSRF checks.
Putting the term in the body keeps it out of the request URL. The endpoint
reads records without writing state or audit events.

PostgreSQL applies the title match to the authorized rows before the page
limit. It lowercases the title and bound search term and checks for a literal
substring. For example, `50%_draft` matches the percent and underscore themselves.
An authorized cursor remains a position even if someone renames that item.
The browser resets the search when changing workspaces or signing out and
reuses the applied term for later pages and retries.

The PostgreSQL regression covers case, literal characters, validation, private
and foreign items, existing view filters, and pagination. A Chromium regression
exercises the search, no-match feedback, and clearing. There is no schema
migration. This search covers titles in the work list. For larger workspaces,
measure query performance before adding an index or expanding the search.
