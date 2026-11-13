# Application typecheck

Run `npx --yes --package pyright@1.1.407 pyright` after installing the locked
development environment. Pyright reads the package scope and virtual environment
from `pyproject.toml`. CI runs the same command on Windows and Linux. It checks
the application under `services/api/src/flowpilot_api`. Pytest exercises runtime
behavior, including PostgreSQL and browser workflows in their dedicated CI jobs.

The first independent review found nine diagnostics. Three concerned environment
values that could be missing. Testing each value explicitly lets the typechecker
see why it is safe to construct the identity configuration. Five concerned
annotations for proposal handlers. Each handler now declares its existing read
or write dependency at the parameter where FastAPI uses it. The remaining
diagnostic concerned parsing database results as tasks, commitments or events.
A Pydantic root model validates each result with the existing discriminator.

For example, a workspace API started with an empty audience must fail before it
can accept a request. The environment regression exercises each missing or empty
setting and a valid configuration. The signed HTTP and PostgreSQL tests exercise
authorization and the stored work variants. The next implementation should run
these checks again against its own revision.
