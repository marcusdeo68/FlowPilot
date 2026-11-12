# Implementation 0001 — Local API and commitment lifecycle

## What this adds

The first code increment creates a local FastAPI application, operational health endpoints, validated commitment contracts, SQLite persistence, lifecycle rules, optimistic concurrency, and an event history. A user can manually create a candidate commitment, list or retrieve it, request a permitted status transition, and inspect its events.

## Why this is the first feature

The product's core value depends on maintaining trustworthy commitment state over time. A small deterministic API gives us a place to establish identifiers, status semantics, validation, transactions, and conflict behavior before adding AI, email access, accounts, or user-interface complexity.

## Software understanding

- FastAPI maps routes to HTTP operations and produces a local OpenAPI document.
- Pydantic parses JSON before business logic runs. `extra="forbid"` rejects fields the server did not define.
- Domain transitions live in a plain Python module so policy does not depend on a web request or a database query.
- The repository uses SQLite bound parameters. It never builds SQL by concatenating user input.
- `expected_version` is optimistic concurrency: a stale client gets `409 Conflict` and must reload current state.
- The status update and event insert are in one write transaction. They commit together or both roll back.
- `healthz` only measures process liveness. `readyz` checks the configured database.

## Design and security boundaries

- New records start at `detected`; they cannot be created directly as completed.
- Illegal transitions and stale updates are rejected by the API.
- Input fields have size limits, unknown keys fail validation, and evidence excerpts are stored only as provided user input.
- The app is local-development-only: there is no identity or authorization layer. It must not be exposed to a network or used with real private data.
- There are no model calls or external side effects. A future approval object must bind approval to the exact action payload and destination.

## Learning path

Trace `main.py` → `schemas.py` → `repository.py` → `domain.py` and `database.py`. Ask what changes if two clients transition the same record, what a database transaction protects, and why an AI-generated state change still needs deterministic validation.

## Current limitations

SQLite schema creation is a starter adapter, not a migration system. The actor is a local placeholder. There is no authentication, multi-tenant access control, automated test suite, frontend, AI extraction, or live integration in this increment. The roadmap tracks these explicitly.
