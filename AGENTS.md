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

## Current implementation boundary

The initial API is a local development foundation with SQLite and synthetic/manual data. It is not authenticated or ready for network exposure. Do not describe it as production-ready. PostgreSQL, team identity, workspace authorization, migrations, AI extraction, and external integrations are future work. The immediate next segment is documented in `docs/implementation/0002-unified-work-model.md`; do not add live provider data before its access model is implemented and reviewed.
