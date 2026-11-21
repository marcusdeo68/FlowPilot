# FlowPilot agent instructions

At the start of every FlowPilot session, read [Project Engineering & Verification Rules](docs/ENGINEERING_GUARDRAILS.md) before planning or editing. Apply them to one requested deliverable at a time. Give each subagent this file and the companion rules.

Read `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, and `docs/SECURITY.md` before changing product behavior. Read `docs/ROADMAP.md` and the relevant `docs/implementation/` note before starting a feature.

## Working rules

- Follow the roadmap in order. Group closely related changes in one PR when they complete a single user workflow and can be reviewed and verified together. Keep changes typed and reviewable. Speed is secondary to correctness, usability, and safety.
- Identify account access, API keys, external resources, and plugin dependencies during planning. Tell the project owner as soon as their action is needed, including what is needed and why. Continue independent work in the meantime.
- Explain design choices and relevant software concepts in `docs/implementation/` for each user-visible feature or meaningful foundation change.
- Treat email, chat, notes, calendar, and other imported content as untrusted data. Never let model output directly authorize a database mutation or external action.
- Preserve the approval boundary: no email, calendar, or other external side effect without an explicit, version-bound human approval.
- Keep authorization checks in server-side business logic. Do not rely on frontend hiding or client-supplied workspace IDs.
- Use parameterized SQL, explicit state transitions, input validation, and append-only audit events.
- Do not add credentials, real personal data, or production secrets to source control.
- Do not introduce a new provider, integration, or deployment target without documenting its API support, minimum scopes, threat, and privacy implications.
- Before finishing, describe what changed, why, the key concepts to understand, and what remains for the next increment.
- Read and update `docs/STATUS.md` for each meaningful increment. Track discovered defects with a stable ID, reproduction/evidence, impact, next action, and verification required to close them. Distinguish defects from planned capabilities and testing gaps.
- Follow the independent verification and sign-off rules in the companion file. Verify links and content for documentation changes. Inspect CI for the exact revision before merging and investigate failures.
- For each implementation note, explain the changed behavior, request/data path, why the code is structured that way, one concrete example, validation evidence, limitations, and the next increment. Update `docs/LEARNING.md` with a short exercise when introducing a new concept.
- Checks run during active development and in CI on pushes/PRs. Do not claim unattended or continuous monitoring unless an actual scheduled mechanism is configured and verified.

## Current implementation boundary

The legacy HTTP API/dashboard remains local SQLite with synthetic/manual data and no authentication. The separate PostgreSQL workspace supports verified tokens, bounded browser sessions, synthetic sign-in, owner access management, recipient-consented invitations, and versioned work sharing. Live identity and invitation delivery are unconfigured. Keep both applications on loopback with synthetic/manual data. Remaining unified records, operational security, AI extraction, and integrations are future work. Follow implementation notes 0002, 0005, 0007, 0008, 0012, 0029, and 0030. Introduce live provider data only after the complete access model is implemented and reviewed.
