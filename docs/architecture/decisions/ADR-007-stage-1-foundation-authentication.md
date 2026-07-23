# ADR-007: Consolidate Foundation and Authentication in Stage 1

**Status:** Accepted by implementation authorization
**Date:** 2026-07-22

## Purpose and audience

Product, architecture, engineering, and security reviewers use this ADR to reconcile the authorized Stage 1 implementation with the original phase plan.

## Context

The original roadmap separated executable platform setup into Stage 1 and authentication/tenant management into Stage 2. The implementation authorization explicitly defines “Stage 1 — Foundation & Authentication,” requires identity, tenant, invitation, RBAC, admin, and audit-ready authentication foundations, and prohibits AWS onboarding or later cloud-security capabilities.

## Decision

Stage 1 combines the original platform-foundation and authentication/tenant-management deliverables. This is a sequencing change only. AWS onboarding, discovery, scanning, rules, compliance, AI, remediation, scheduling, monitoring integrations, deployment infrastructure, and UAT remain deferred.

This supersedes only the Stage 0 phase split that placed authentication/tenancy in Stage 2; it does not supersede any security boundary or later-stage dependency.

## Alternatives considered

- Keep authentication in Stage 2: rejected because the authorized Stage 1 deliverable requires an operable multi-tenant foundation.
- Build only backend authentication in Stage 1: rejected because the requested acceptance flow includes the Stage 1 admin frontend.
- Renumber all later stages: rejected to preserve historical references and avoid unnecessary roadmap churn.

## Consequences and validation

Stage 1 has a larger verification surface and must demonstrate cross-tenant isolation, token lifecycle security, migrations, backend/frontend tests, and build quality. Acceptance is demonstrated only by the Stage 1 verification report; an unavailable required check leaves Stage 1 incomplete.
