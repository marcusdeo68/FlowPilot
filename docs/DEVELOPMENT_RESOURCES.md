# Development resources and agent handoffs

Updated: 2026-11-16. This is a reference and proposed work sequence, not a claim
that the proposed changes are installed or implemented. The
[engineering guardrails](ENGINEERING_GUARDRAILS.md) remain authoritative.

## Recommended sequence

1. Run PostgreSQL 17 locally through Docker Desktop/Compose, with a separate
   database ending in `_test` for integration tests. Earlier local
   verification skipped 53 database-dependent checks; closing that gap reduces
   dependence on hosted CI for debugging. Existing [compose.yaml](../compose.yaml)
   creates `flowpilot_dev` only. Never point the test suite at development data.
2. Add compact task handoffs and a concise current checkpoint above historical
   evidence in [STATUS](STATUS.md). Keep durable context in versioned documents.
3. Add one verification entry point with complete logs and a short revision-bound
   result summary. Preserve existing required independent checks.
4. Retain Playwright traces/screenshots on browser failures and publish test
   reports through GitHub Actions artifacts and job summaries.
5. Add Context7 for targeted library documentation; evaluate Playwright CLI for
   routine browser work. Trial Serena only if code navigation becomes a bottleneck.

## Resource assessment and observed state

| Resource | State at this checkpoint | Intended benefit |
| --- | --- | --- |
| GitHub plugin | Authenticated as the repository owner in this chat | Repository, PR and CI access |
| GitHub remote MCP | User confirmed connected in a separate PowerShell Codex session | GitHub tools in that client; distinct from this chat's plugin |
| Playwright MCP | Saved and enabled; initialization listed 25 tools; synthetic browser navigation verified after restart | Interactive browser inspection and reproduction |
| OpenAI Developers | Plugin directory confirms installed | Official OpenAI development guidance when the AI pipeline is implemented |
| Context7 | Available; suggested, installation/connection not confirmed | Version-specific library documentation and examples |
| Playwright CLI + Skills | Recommendation; installation not verified | Concise browser commands for coding workflows |
| Serena | Optional future trial; installation not verified | Symbol/reference navigation and focused code retrieval |
| Local PostgreSQL test environment | Separate PostgreSQL 17 test container verified; independent full suite 177 passed, no skips; FP-013 fixture fix recorded in STATUS | Migration, authorization and session checks before CI |
| Shared verification command and failure artifacts | Proposed improvements | Less repeated command/log discovery and better debugging evidence |

Existing project tools include uv, pytest, Ruff, pinned Pyright, Alembic,
SQLAlchemy, Python Playwright browser tests and GitHub Actions. Reuse these before
adding another testing or orchestration framework. See [README](../README.md),
[architecture](ARCHITECTURE.md) and [browser sessions](implementation/0012-browser-sessions.md).

Context7 retrieves library documentation; it does not remember FlowPilot's design.
Serena's symbol tools may reduce broad source reads, but their value should be
measured on this repository. No particular token saving is guaranteed. Microsoft's
Playwright guidance recommends evaluating CLI + Skills for coding-agent efficiency;
MCP is useful when rich, continuing browser inspection helps the task.

## Agent roles and handoffs

- Planner: read-only exploration and a written plan before implementation.
- Builder: one scoped deliverable, with targeted checks during development.
- Independent auditor: fresh context, whole diff review and the complete required
  verification before sign-off. Do not preload the builder's success narrative.
- Debugger: investigate repeated failures when the cause remains unclear.

Use this compact task brief rather than repeatedly copying the whole conversation:

```text
Original user request:
One deliverable and acceptance criteria:
Base revision / current revision / working-tree state:
Branch and PR:
Required instructions: AGENTS.md and docs/ENGINEERING_GUARDRAILS.md
Relevant design notes and source/test paths:
Constraints, access boundaries and out-of-scope work:
Unresolved questions or known reproductions:
Expected output and next action:
```

For an auditor's initial brief, supply requirements and revisions without the
builder's conclusions or test results. The auditor discovers and checks evidence
independently. For other handoffs, include a concise factual verification summary
where useful. Required documentation still needs to be read directly.

Prefer focused searches and relevant file sections, concise agent reports and
bounded logs. Keep a capable routine model as the default; use more expensive
reasoning only when task complexity justifies it. More agents are useful when
their tasks are distinct, not when they repeat the same exploration.

## Verification and diagnostics

During building, run affected checks after meaningful changes. Before sign-off,
the independent reviewer executes the complete checks required by the guardrails.
Never weaken tests, silently skip unavailable suites, or treat formatter/syntax
checks as typechecking. Record exact revision/configuration, commands, exit codes,
pass/fail/skip counts and links to full logs. Inspect exact-candidate CI before a
merge and inspect the resulting main revision afterward.

Proposed failure artifacts should capture disposable synthetic browser sessions.
DOM snapshots, network records and traces can contain sensitive information;
exclude real accounts and reusable credentials, and choose bounded retention.
Avoid automatic retry-until-green behavior that hides the original failure.

## PostgreSQL installation choice

Preferred for this project: install Docker Desktop with its WSL2 backend and run
PostgreSQL 17 in a container using Compose. Docker runs the PostgreSQL server; it
does not replace PostgreSQL. This matches the existing development configuration
and CI major version, keeps versions reproducible and separates disposable test
data from development data. Docker Desktop adds resource and virtualization
requirements. A native PostgreSQL installation is a valid alternative when that
overhead is unsuitable. No installation or database configuration was performed
when recording this recommendation.

## Primary references

- [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Compose readiness and health checks](https://docs.docker.com/compose/how-tos/startup-order/)
- [Native PostgreSQL for Windows](https://www.postgresql.org/download/windows/)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Playwright CLI and Skills](https://github.com/microsoft/playwright-cli)
- [Playwright Python Trace Viewer](https://playwright.dev/python/docs/trace-viewer)
- [Context7](https://github.com/upstash/context7)
- [Serena](https://github.com/oraios/serena)
- [GitHub Actions job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)
- [GitHub Actions artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data)
