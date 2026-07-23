# Development Rules

## Purpose and audience

All engineers and reviewers use these mandatory standards for Stage 1 and later approved work.

## Repository and boundaries

Use a feature-based modular monorepo. Group business features together, keep shared code minimal, create no generic `utils` dumping ground, prevent circular dependencies, and never let one service access another feature's internal repository. Architectural boundary changes require an ADR.

## Backend and frontend

Backend baseline: Python 3.12, FastAPI, typed code, Pydantic at external boundaries, SQLAlchemy, Alembic, Ruff for formatting/linting, Pytest, injected external adapters, structured logs, and explicit exception mapping. Use async only for clear measured value. Never call Boto3 or AI from route handlers; never commit secrets or customer credentials. A broad `except Exception` is allowed only at a boundary that logs safely and translates/rethrows an appropriate application error.

Frontend baseline: React, strict TypeScript, Vite, Tailwind CSS, Lucide React, TanStack Query, React Router, React Hook Form, and Zod boundary validation. Use feature folders; visual components do not make direct API calls. The UI never assumes authorization and must meet accessibility acceptance criteria.

## Data, API, security, and AI

PostgreSQL uses plural snake_case tables, UUIDs by default, UTC, foreign keys/constraints/indexes, organization ownership, transactions, and optimistic locking where concurrency matters. APIs use `/api/v1`, plural resources, correct semantics, structured errors, correlation IDs, bounded pagination/filtering/sorting, idempotency for retried actions, OpenAPI, and server-side authorization.

Least privilege and deny-by-default apply. Scans are read-only. No destructive action occurs without authorization and confirmation; no automation occurs without an approved playbook and approval. AI input is minimized/redacted, output untrusted/schema-validated, prompts versioned, timeouts/cost controls configured, and no sensitive action depends solely on AI.

## Exceptions

Document an exception in an issue/ADR with owner, rationale, security impact, expiry, and reviewer. Convenience is not sufficient.
