# Implementation 0048 — Open a pending review from Today

On **Today**, select a pending suggestion to read its evidence in **Private
inbox**. For example, two messages might both suggest “Confirm the venue.”
Selecting the second suggestion opens the source associated with that row,
even if it is older than the first page of inbox results.

Today already receives the source and proposal identifiers with each pending
suggestion. The inbox uses those identifiers to request current details in
the selected workspace. The server checks the signed-in reader's access.
Opening the review makes no decision. Accepting, editing, and dismissing use
the existing review controls and their version checks.

Today lists up to five recent pending suggestions. A suggestion can change
between loading Today and opening it. The detail view reads the stored
state so the user can see a decision already made in another tab.

Chromium opened the older of two identically titled suggestions, retried a
failed detail read, and displayed the saved dismissal and the correct source
excerpt. The browser test checked that navigation used only GET requests,
that a denied inbox listing blocked the detail read, and that paging the
source into view restored keyboard focus to its row after closing details.

See [the review workflow](0020-signed-in-private-inbox.md) and the
[verification tracker](../STATUS.md). Live pilot testing through the
Railway HTTPS origin remains a separate milestone.
