# FlowPilot product intent

## Product statement

FlowPilot is a unified work coordination hub. It brings permitted signals from email, chat, notes, and calendars into one place; identifies changes, responsibilities, and deadlines; and helps people move the resulting work forward.

The unifying idea is not to mirror every source application or automate a user's desktop windows. FlowPilot creates a trustworthy, cross-app view of work while keeping each provider's permissions and source context visible.

## First audience and problem hypothesis

The initial audience is small teams of roughly 5–20 people coordinating events, projects, outreach, and administrative work. Their work is scattered across email, team chat, notes, and calendars. Important promises and dates can be missed because no one system owns the complete picture.

This problem hypothesis needs validation through interviews and pilot use. We should first prove a narrow workflow with one team and a small number of sources, then add providers based on demonstrated value.

## Product promise

FlowPilot helps a team answer:

- What changed across the connected sources?
- What needs attention today or soon?
- Who owns each commitment, task, or event?
- What evidence led FlowPilot to suggest it?
- What action is proposed, where will it happen, and who approved it?

## Core workflow

1. Connect a source with a clearly explained, minimum permission set, or add sample/manual content.
2. Record a source item with its provider, owner, timestamp, link, and visibility boundary.
3. Detect a possible commitment, task, deadline, event, or change and preserve the supporting evidence.
4. Let a person review, correct, confirm, dispute, or dismiss the proposal.
5. Track accepted work in a shared view, respecting the source owner's permissions.
6. Prepare an email, message, calendar change, or other action for review.
7. Show the exact account, destination, content, and effect; execute only after explicit approval.
8. Record and verify the result against the provider.

## Main product surfaces

- **Today / Command Center:** upcoming deadlines and events, overdue items, blockers, new changes, and pending approvals.
- **Unified Inbox:** source updates and candidate work grouped across connected providers, with source links and evidence.
- **Tasks & Projects:** accepted tasks, commitments, owners, dependencies, and project grouping.
- **Schedule:** important deadlines and events from work items and permitted calendar sources.
- **Review & Send:** prepared email/message/calendar actions with editable previews and clear approval.
- **Connections & Settings:** connected accounts, requested scopes, data retention, visibility, notification preferences, and revocation.

This should feel like a focused productivity workspace. A conversational assistant may help people search or explain changes later, but the core UI should work without prompting a model for every action.

## Canonical concepts

- **Source item:** a message, email, note, event, or update from a connected provider. It retains provider identity and access visibility.
- **Work item:** an accepted commitment, task, or event FlowPilot tracks. These are related but keep distinct fields and meanings.
- **Proposal:** a possible work item or state change produced from a source. It is not canonical state until reviewed or accepted under product rules.
- **Action proposal:** a specific draft operation, such as sending an email, with exact recipient, sender account, subject, body, and target.
- **Approval:** a person-authorized decision bound to an exact, versioned action proposal. Editing the action invalidates its approval.
- **Execution record:** the idempotent attempt, provider response, and verification outcome for an approved action.

## Email experience

FlowPilot may help draft professional email quickly. The interface should show the sender account, recipients, subject, body, and attachments before sending. A person's send action approves that exact payload. If any field changes after approval, FlowPilot requests approval again. The first release should save a draft where feasible; direct sending is a later capability requiring a separate permission review and a clearly labeled confirmation.

## Product and engineering principles

- Keep the commitment-to-completion workflow as FlowPilot's defining capability.
- Unify work across sources; do not attempt to reproduce every provider's entire interface.
- Treat imported content as untrusted data, not as instructions to FlowPilot.
- Preserve source provenance and let people inspect the evidence behind each suggestion.
- Keep personal messages private unless the authenticated user is authorized to share derived work.
- Separate read access from write/action permissions wherever a provider allows it.
- Treat AI output as a proposal; deterministic server rules and authorization decide what becomes state or causes a side effect.
- Keep the core manual workflow usable without AI or any connected provider.

## Current implementation boundary

The existing code is a local API scaffold for synthetic/manual commitment records, status transitions, and an event history. It has no accounts, workspaces, provider integrations, AI inference, or authenticated access. The next implementation segment must redesign the data model and authorization foundation before real connectors or user data are introduced.
