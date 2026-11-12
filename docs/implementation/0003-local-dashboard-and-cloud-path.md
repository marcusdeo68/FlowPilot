# Implementation 0003 — Local dashboard and cloud delivery path

**Status: local dashboard shell implemented; cloud delivery planned.**

## What changed

The API now serves a same-origin dashboard at `/`. The shell presents a command-center layout for Today, a unified inbox, tasks, schedule, review/send, and connections. The manual task workflow is functional: the user can create a local commitment, see saved records, and advance eligible records through the existing deterministic lifecycle. The empty workspace shows clearly labeled sample cards for product review; those cards are not real messages or connected source records.

## Why this is the next web increment

The product needs to demonstrate the daily loop before integrations: notice what's due, review new signals, create or progress work, and see upcoming events. This UI makes that shape visible while the data and access model remain local and synthetic. It intentionally does not pretend that sample inbox cards are backed by Gmail, Slack, Teams, Keep, or a real calendar.

## Software and design concepts

- **Same-origin client:** FastAPI serves HTML, CSS, JavaScript, and `/api/v1` from one local origin. This avoids a separate dev server and cross-origin policy during the first learning step.
- **Progressive foundation:** The client uses platform HTML/CSS/JavaScript and has no build dependency. A framework decision can be made once routes, authenticated sessions, and a larger UI system are justified.
- **Safe rendering:** API-provided values are put into DOM `textContent` fields, not interpolated into `innerHTML`. User text therefore remains text rather than becoming executable markup.
- **Server-owned state:** Creating a task and completing it use the existing API. The UI sends a requested transition; the server checks the lifecycle and expected version. Sample task checkboxes are disabled because samples are not stored records.
- **Explicit prototype boundary:** The API remains unauthenticated SQLite local-development software. The UI does not create workspace isolation or provider authorization, and is not suitable for network exposure.

## AWS path and trade-offs

AWS is a strong portfolio target when it demonstrates a coherent delivery pipeline rather than a collection of services. Keep the app as a modular monolith, package it in a container, store images in ECR, and run the API/UI on ECS Fargate. Fargate runs ECS tasks without the project managing EC2 hosts ([AWS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)). Move persistence to PostgreSQL and then use RDS for managed database operations ([RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)). Use Secrets Manager, task-specific least-privilege IAM, CloudWatch, and Terraform.

GitHub Actions should authenticate to AWS via OIDC with a trust condition limited to this exact repository and protected deployment branch/environment. That avoids static AWS credentials in repository secrets; GitHub documents the IAM trust constraints and the required workflow token permission ([GitHub OIDC in AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)). Pin third-party workflow actions to immutable commit SHAs. AWS Budget notifications help track cost, but billing data updates at least daily, so alerts are not a hard spend cap or real-time guard ([AWS Budgets best practices](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)).

Do not deploy the current unauthenticated scaffold. Complete workspace authorization, PostgreSQL migrations, secrets design, and a reviewed threat model first. The architecture can create ongoing charges (including networking, load balancing, database, container, logs, and storage), so resource creation needs a deliberate low-cost plan and an agreed spend boundary.

## Resume-ready skills this roadmap can demonstrate

1. **Secure multi-tenant backend:** object-level authorization, workspace isolation, migrations, optimistic concurrency, append-only audit, and exact-payload approvals.
2. **Cloud and DevOps:** Docker, ECS/Fargate, ECR, RDS, IAM, VPC networking, Terraform, GitHub Actions OIDC, rollback, and CloudWatch.
3. **Reliable integrations:** OAuth least privilege, webhook signatures, idempotency, retries/backoff, provider revocation, and source visibility.
4. **Applied AI engineering:** evidence-grounded structured proposals, abstention, prompt-injection handling, evaluation fixtures, and model/tool separation.
5. **Product UI and accessibility:** a keyboard-usable inbox/review flow, responsive command center, explicit source provenance, and visible action approvals.

Prioritize the first two as the portfolio backbone, then add one provider integration and one measured AI evaluation workflow. Avoid adding unrelated services solely to list more technologies.

## Next decisions and implementation

- Complete Stage 1 authorization and visibility design before changing the database or adding provider data.
- Add product-grade synthetic fixtures and connect the inbox and schedule to typed local source records.
- Choose authentication/session approach and PostgreSQL/Alembic after the data access matrix is agreed.
- Add UI and API checks when the runtime is available; this increment has not yet been run locally because the Python runtime is unavailable in the environment.
- After the repository exists, add CI for linting and application checks, then add Docker and Terraform as separately reviewed increments.
