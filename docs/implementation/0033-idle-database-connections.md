# Implementation 0033 — Release idle database connections

FlowPilot uses a connection pool by default. A pool keeps physical connections
open so the next request can reuse them. Railway's sleep feature uses outbound
traffic to detect inactivity. Database connections can keep a service awake,
which matters for a low-traffic pilot on the free allowance. [Railway sleep behavior](https://docs.railway.com/deployments/serverless)

For the staging experiment, set `FLOWPILOT_DATABASE_POOL=disabled` on the
Railway web service. Enable **Serverless** under **Settings → Deploy** and deploy
the service for the setting to take effect. [Railway Serverless setup](https://docs.railway.com/pricing/cost-control#enabling-serverless)

The shared PostgreSQL engine factory selects SQLAlchemy
`NullPool`. The application or migration command opens a fresh connection at
each checkout. When its scope exits, SQLAlchemy closes the physical connection.
For example, saving a task commits its transaction before closing the connection.
If the transaction raises an error, SQLAlchemy rolls it back and closes the
connection. The next read opens a new connection to the same database.
[SQLAlchemy connection pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)

Use `FLOWPILOT_DATABASE_POOL=pooled` or omit the setting for the default pool.
The pooled engine checks whether a connection is alive before reusing it.
An unsupported value fails startup with a configuration error. The shared
engine factory still hides SQL parameter values when rendering errors.

Local PostgreSQL tests verify that a committed write survives reconnecting,
a failed transaction rolls back, and both physical connections close. Unit
tests cover the default mode, explicit modes, and configuration errors.
Opening a fresh connection adds setup latency. During sustained traffic it can
also increase connection churn, since this mode has no pool-imposed concurrency
limit. During staging, measure cold-start latency, actual idle time, and combined
app and database usage. The platform's sleep behavior and cost remain to be
verified alongside the [Railway ingress and identity checks](0032-railway-pilot.md#staging-and-pilot-checks).
