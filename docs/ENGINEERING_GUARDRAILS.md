# Project Engineering & Verification Rules

## Core guardrails

- Never delete, skip, or weaken existing tests to make a test suite pass.
- Never claim work is complete without executing the build, typecheck, and tests and verifying zero errors. Run the linter and the project's additional checks as well. Record failures, skips, unavailable checks, and the revision tested. A missing typechecker or a skipped integration suite is a verification gap.
- Keep changes minimal and scoped to one requested deliverable. State its acceptance criteria before implementation. Finish its independent verification before starting another deliverable.

## Roles and handoff

1. **Planner / Architect, before writing code.** Spawn a read-only planner. Give it the original request and repository instructions. Ask it to inspect the existing entry points, dependencies, tests, and data boundaries. It returns a written, step-by-step plan with the smallest change that meets the acceptance criteria and how to verify it. The builder implements that deliverable.
2. **Edge-Case & Security Auditor, before sign-off.** Spawn an independent subagent with fresh context for every feature, bug fix, or refactor. This auditor also performs the verification below. Give it the original requirements, repository instructions, and base and candidate revisions (or working tree). Start without the builder's conversation, conclusions, or test results. Have it inspect error paths, invalid input, permission boundaries, credential handling, retries, races, and partial failures where relevant. Keep findings tied to changed behavior, with file locations and concrete evidence.
3. **Debugger / Root-Cause Investigator, only when stuck.** When the same failure recurs and its cause is unclear, give a fresh debugger the failing command, logs, and a minimal reproduction. It traces the execution path and reports the underlying cause and a focused fix. The builder applies the fix and returns the revised change to independent verification.

## Prompt for the independent verification subagent

Before considering this task complete, independently audit the change against the original user requirements.

1. **Diff audit.** Run `git status` and `git diff`. Inspect the whole change from its base, including committed, staged, unstaged, and new files as applicable. Compare every changed line against the requirements. Flag bugs, security issues, missing edge cases, unintended side effects, and unnecessary complexity.
2. **Test integrity.** Check that no existing test was weakened or bypassed. Verify that matching unit or integration tests cover normal inputs, edge cases, and failure states. For a documentation deliverable, also check the startup path, links, and requested content.
3. **Live execution.** From the terminal, run the project's full test suite, linter, formatter check, build, and typechecker. Use the [README](../README.md) and [CI workflow](../.github/workflows/ci.yml) to identify commands and prerequisites, including real PostgreSQL and Chromium. If a service suite runs in CI, verify its results for the candidate revision. Report each suite separately. Syntax checks and formatting do not establish type correctness.
4. **Final report.** Give the revision or working-tree state, exact commands, exit codes, pass/fail/skip totals or final output lines, findings, and remaining risks. Redact secrets from evidence. If any check fails, return the evidence to the builder to fix the root cause and rerun independent verification on the revised change. Withhold sign-off until all required checks pass cleanly.
