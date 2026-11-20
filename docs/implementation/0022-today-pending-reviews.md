# Implementation 0022 — Pending reviews in Today

Today shows up to five of your most recently updated pending task suggestions in
the selected workspace. For example, a suggestion called “Send the workshop
packet” appears in Today until you accept or dismiss it in Private inbox.
Use **Open private inbox** to return to the sources and review their evidence.

The view calls the existing read-scoped `GET /proposals?limit=5` endpoint.
The service checks active workspace membership and returns only the caller's
pending proposals. Today renders the titles as text. The inbox still requires
the appropriate permissions and the saved proposal version for each decision.

The review request has its own loading and retry state, so a transient error
leaves the due-task list usable. A generation check ignores old responses,
including authorization errors, after a workspace, view, or session change.
Both reads use the same workspace access. An active 403 clears both lists,
invalidates the other request, and prompts the user to refresh their workspaces.
Chromium covers retry, the change after dismissal, and a late response from
the previous workspace. See [STATUS](../STATUS.md) and the PR for results.

The list is a snapshot on entering Today or changing workspaces. It shows up to
five titles and uses the existing schema, API, and local test setup. Upcoming
events are a separate roadmap increment.
