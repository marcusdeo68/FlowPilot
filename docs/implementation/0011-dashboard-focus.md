# 0011 — Show the actual local workload

An empty local dashboard used to show one commitment due today. The SQLite
database contained none: the browser had substituted three illustrative tasks
and counted one of them. A database read failure took the same path. Chromium
reproduced FP-011 before the fix: expected 0, received 1.

The Today panel now shows only persisted commitments, or an empty state. A
failed read displays an unknown count and a Retry loading button. The independently
labeled sample inbox, schedule and draft panels remain illustrations. “Show recent”
expands the focus list from four records to as many as 50, and can collapse it
again. The footer no longer makes a permanent claim that all changes are saved.

## Request and design

The browser sends its local calendar day to `GET /api/v1/focus?day=YYYY-MM-DD`.
SQLite counts all commitments due on that date except completed/canceled ones,
then selects the 50 most recently updated records for display. Both queries use
the same read transaction so a concurrent save cannot change the dataset between
the count and the list. List rows omit details and evidence. Reading the count
never writes anything. This endpoint belongs only to the existing loopback demo.

For example, the user may have 50 newer commitments without dates and an older
one due today. A count over the visible list would say zero; the new query says
one. Using the browser's local day avoids shifting a date-only deadline because
the server is in another time zone. An open tab recalculates the date when data
reloads; it does not automatically refresh at midnight.

`loadTasks` gives each read a sequence number. If two refreshes overlap, the
older response cannot replace what the newer request shows. GET can be retried
without creating another record. The explicit write/transition controls still
send their existing version checks. No authentication, connector, or workspace
API impersonation path was introduced.

Initial reads, refreshes, and retries show a loading message, an unknown count,
and `aria-busy` while awaiting the current response. Only the newest request may
clear that busy state. Failure replaces loading with the explicit retry control;
a successful empty result alone may show zero. Chromium tests hold a real HTTP
response until after a newer read finishes, then release either the older success
or failure to verify that the current display survives. A fixed clock and explicit
Los Angeles browser time zone also exercise the previous calendar day at UTC midnight.

## Verification and next step

The original branch recorded 95 passing tests, including nine Chromium workflows;
43 PostgreSQL checks were skipped locally. The reconciled revision passed 13
Chromium workflows, including loading, overlapping-response and browser-date
regressions. [PR #10](https://github.com/marcusdeo68/FlowPilot/pull/10) records
independent verification, exact-candidate CI, and merge history; all are required
before sign-off. Tests cover the empty count, a load failure followed by recovery,
expanding actual records, terminal-state exclusion and an older due item outside
the display window. The legacy demo still does not show the private workspace
inbox. Next: interactive synthetic-source review against the verified API.
