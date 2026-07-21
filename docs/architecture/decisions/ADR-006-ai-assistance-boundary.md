# ADR-006: AI Is an Advisory Layer

**Status:** Proposed
**Date:** 2026-07-20

## Purpose and audience

Product, AI, security, and engineering reviewers use this ADR to enforce the advisory AI boundary.

## Context and decision

AI can improve explanation and drafting but cannot supply authoritative security decisions. Use a provider-neutral API client, versioned prompts, minimized/redacted inputs, Pydantic-validated structured output, sanitization, timeout/retry/cost limits, audit metadata, and deterministic fallback.

AI may explain findings, business impact, compliance context, remediation options, Jira content, and reports. It may not receive credentials/secrets, call AWS, detect findings independently, approve or execute remediation, alter mappings without review, or close findings.

## Consequences and follow-up

Core workflows remain available without AI; output must be visually labeled and reviewed for sensitive recommendations. Provider selection, residency, retention/training terms, cost ceilings, redaction tests, and permitted data classes require approval before Stage 8.
