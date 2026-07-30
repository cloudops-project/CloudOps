# Architecture Decision Records

> See [DECISIONS.md](../../../DECISIONS.md) for the consolidated index, which also carries the
> `ADR-Dxx` records made during demo hardening (same-origin proxy, synthetic demo discovery, Quick
> Tunnel as temporary access only, dry-run remediation, Mailpit/mock providers, the forwarded-host
> same-origin allowance, no Jira, and application-role versus IAM-role separation). The numbered
> `ADR-0xx` files in this directory remain authoritative for the decisions they cover.

## Purpose and audience

ADRs give contributors a durable record of important choices, alternatives, consequences, and status. They describe intent and do not prove implementation.

## Status process

Use **Proposed**, **Accepted**, **Superseded**, or **Rejected**. A proposed ADR requires the project lead plus the relevant security/technical owner; accepted security-boundary changes require designated security review. Never edit a superseded decision to hide history—add a replacement and link both.

## Index

- [ADR-001: Feature-based monorepo](ADR-001-feature-based-monorepo.md) — Proposed
- [ADR-002: FastAPI backend](ADR-002-fastapi-backend.md) — Proposed
- [ADR-003: PostgreSQL database](ADR-003-postgresql-database.md) — Proposed
- [ADR-004: Cross-account IAM](ADR-004-cross-account-iam.md) — Proposed
- [ADR-005: Deterministic rule engine](ADR-005-deterministic-rule-engine.md) — Proposed
- [ADR-006: AI assistance boundary](ADR-006-ai-assistance-boundary.md) — Proposed
- [ADR-007: Consolidate foundation and authentication in Stage 1](ADR-007-stage-1-foundation-authentication.md) — Accepted by implementation authorization
- [ADR-008: Application-managed JWT authentication for Stage 1](ADR-008-stage-1-jwt-authentication.md) — Accepted by implementation authorization
- [ADR-009: Tailwind CSS for the CloudOps frontend](ADR-009-tailwind-frontend.md) — Accepted by implementation authorization
- [ADR-010: CloudOps implementation product name](ADR-010-cloudops-product-name.md) — Accepted by implementation authorization
- [ADR-011: Deliver AWS account onboarding in Stage 2](ADR-011-stage-2-aws-account-onboarding.md) — Accepted by Stage 2 implementation authorization

ADR-007 through ADR-010 govern Stage 1. ADR-011 supersedes only ADR-007's reserved Stage 2 numbering and establishes AWS onboarding as Stage 2. ADR-010 permits historical records to retain the former CloudFix name; active product and implementation documentation uses CloudOps.

## Template

Record date, status, context, decision, alternatives, consequences, security/tenant implications, validation, and follow-up actions. Number files `ADR-NNN-kebab-description.md`.
