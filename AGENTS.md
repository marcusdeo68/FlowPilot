# FlowPilot agent instructions

Read `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, and `docs/SECURITY.md` before changing product behavior. Read `docs/ROADMAP.md` and the relevant `docs/implementation/` note before starting a feature.

## Working rules

- Keep changes small, typed, reviewable, and aligned with the documented roadmap.
- Explain design choices and relevant software concepts in `docs/implementation/` for each user-visible feature or meaningful foundation change.
- Treat email, chat, notes, calendar, and other imported content as untrusted data. Never let model output directly authorize a database mutation or external action.
- Preserve the approval boundary: no email, calendar, or other external side effect without an explicit, version-bound human approval.
- Keep authorization checks in server-side business logic. Do not rely on frontend hiding or client-supplied workspace IDs.
- Use parameterized SQL, explicit state transitions, input validation, and append-only audit events.
- Do not add credentials, real personal data, or production secrets to source control.
- Do not introduce a new provider, integration, or deployment target without documenting its API support, minimum scopes, threat, and privacy implications.
- Before finishing, describe what changed, why, the key concepts to understand, and what remains for the next increment.
- Read and update `docs/STATUS.md` for each meaningful increment. Track discovered defects with a stable ID, reproduction/evidence, impact, next action, and verification required to close them. Distinguish defects from planned capabilities and testing gaps.
- Run checks appropriate to the change before committing. Behavior changes require relevant regression tests; use the existing lint, formatting, test, JavaScript syntax, and package checks when affected. Inspect CI for the exact revision before merging and investigate failures. Documentation-only changes need link/content and diff checks, not repeated runtime tests.
- For each implementation note, explain the changed behavior, request/data path, why the code is structured that way, one concrete example, validation evidence, limitations, and the next increment. Update `docs/LEARNING.md` with a short exercise when introducing a new concept.
- Checks run during active development and in CI on pushes/PRs. Do not claim unattended or continuous monitoring unless an actual scheduled mechanism is configured and verified.

## Current implementation boundary

The initial API is a local development foundation with SQLite and synthetic/manual data. It is not authenticated or ready for network exposure. Do not describe it as production-ready. PostgreSQL, team identity, workspace authorization, migrations, AI extraction, and external integrations are future work. The immediate next segment is documented in `docs/implementation/0002-unified-work-model.md`; do not add live provider data before its access model is implemented and reviewed.
