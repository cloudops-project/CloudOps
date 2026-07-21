# ADR-003: PostgreSQL Database

**Status:** Proposed
**Date:** 2026-07-20

## Purpose and audience

Backend, database, and security engineers use this ADR to align persistence technology and integrity expectations.

## Context and decision

CloudFix requires relational integrity, tenant-scoped queries, lifecycle transactions, indexing, and auditable relationships. PostgreSQL is the intended production system of record with SQLAlchemy and Alembic. Use plural snake_case tables, UUID keys, UTC timestamps, foreign keys, constraints, explicit indexes, and organization ownership.

## Alternatives and consequences

SQLite is allowed only for isolated experiments or lightweight tests because it does not represent intended concurrency and production behavior. A document database offers flexible asset payloads but complicates relational workflows and integrity. PostgreSQL may use constrained JSONB for service-specific evidence while core ownership stays relational.

## Follow-up

Approve RLS as defense-in-depth, retention, partitioning thresholds, encryption/key ownership, backup objectives, and migration review rules before production design.
