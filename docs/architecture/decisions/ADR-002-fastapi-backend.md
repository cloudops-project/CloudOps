# ADR-002: FastAPI Backend

**Status:** Proposed
**Date:** 2026-07-20

## Purpose and audience

Backend engineers and architecture/security reviewers use this ADR to align the API technology and layering constraints.

## Context and decision

CloudFix needs typed REST APIs and close alignment with Python/Boto3 security work. Use Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, Ruff, and Pytest. Routes remain thin and call injected application services; they do not call Boto3, AI, or repositories directly.

## Alternatives and consequences

Django provides more built-ins; Node frameworks could align frontend language. FastAPI offers explicit schemas and a focused learning path, but authentication, authorization, job orchestration, and administrative capabilities require deliberate design. Async will be used only for demonstrated I/O value.

## Security and follow-up

Pydantic is validation, not authorization. Organization scope, rate limits, safe errors, parameterized persistence, and audit events remain mandatory. Prototype service boundaries and error mapping in Stage 1 after approval.
