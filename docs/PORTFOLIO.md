# FlowPilot portfolio evidence

## Implemented and exercised

- Python and FastAPI serve a same-origin HTML, CSS, and JavaScript workspace.
  See [workspace UI](implementation/0017-workspace-screen.md).
- PostgreSQL, SQLAlchemy, and Alembic support workspace-scoped storage,
  transactional audit events, and versioned updates. See [work storage](implementation/0005-postgres-work-storage.md)
  and [work sharing](implementation/0030-workspace-sharing.md).
- The app verifies signed access tokens, authorizes workspace operations on
  the server, and uses bounded browser sessions and CSRF checks. The OAuth
  authorization-code and PKCE flow has synthetic provider coverage. See
  [browser sign-in](implementation/0016-browser-login.md).
- Docker and Docker Compose support local application packaging and
  PostgreSQL testing. GitHub Actions, pytest, Playwright/Chromium, Ruff,
  and Pyright support verification. See [hosted workspace](implementation/0031-hosted-workspace.md)
  and [the CI workflow](../.github/workflows/ci.yml).

## Deployment and provider claims

- Railway compatibility is tested locally and setup is documented. Live
  deployment, operational usage, and a friend pilot remain pending.
  See [Railway pilot](implementation/0032-railway-pilot.md) and the
  [image rehearsal](implementation/0046-hosted-image-rehearsal.md).
- The optional Cloudflare Worker gateway was implemented and tested locally
  with Node. The selected pilot uses Railway only. Hosted Worker operations
  remain unverified.
  See [authenticated ingress](implementation/0034-authenticated-pilot-ingress.md).
- AWS was evaluated during planning. ECS/Fargate, ECR, RDS, IAM/VPC deployment,
  Secrets Manager, CloudWatch, Terraform, and GitHub-to-AWS OIDC are unused in
  FlowPilot.
- Live identity, Gmail, Google Calendar, Slack, external notification delivery,
  and model inference remain future work. Private Notes are implemented
  directly in FlowPilot.

Once the pilot runs, record the deployment link, dates, number of people who
actually tested it, and what changed in response to their feedback.
