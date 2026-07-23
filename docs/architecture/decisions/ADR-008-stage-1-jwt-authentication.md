# ADR-008: Application-Managed JWT Authentication for Stage 1

**Status:** Accepted by implementation authorization
**Date:** 2026-07-22

## Purpose and audience

Backend, frontend, security, and operations reviewers use this ADR to understand the Stage 1 authentication mechanism and its relationship to the earlier OIDC-ready direction.

## Context

Stage 0 proposed OIDC-compatible authentication and left the provider open. Stage 1 explicitly requires registration, password login, short-lived access JWTs, rotating refresh tokens, logout/revocation, and password change. No external identity provider is selected.

## Decision

Implement application-managed email/password authentication for Stage 1. Passwords use Argon2. Access JWTs are short-lived, signed with an environment-provided key, and returned for browser memory-only use. Refresh tokens are opaque high-entropy values delivered through an HttpOnly cookie; only SHA-256 hashes and session metadata are stored. Every successful refresh rotates the token; detectable reuse revokes its family.

The API validates JWT signature, algorithm, subject, type, and expiration. CORS, trusted hosts, cookie attributes, origin validation for unsafe cookie-authenticated requests, generic credential errors, a rate-limit abstraction, and audit events form the Stage 1 boundary.

## Alternatives, consequences, and follow-up

External OIDC, the Stage 0 proposal in the PRD and security guidance, remains the preferred future enterprise federation path but is superseded for Stage 1 because no provider is approved. Dispatch/workspace authentication is inapplicable to this independently hosted FastAPI/React product. Server-side opaque sessions were considered but do not meet the explicit access-JWT requirement. The local mechanism increases password/session security responsibilities and does not provide SSO, MFA, reset, or verification delivery. Access-token revocation is bounded by short expiry. Revisit federation before production exposure through a compatibility/migration ADR.
