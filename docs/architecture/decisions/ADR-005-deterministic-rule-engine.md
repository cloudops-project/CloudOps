# ADR-005: Deterministic Rule Engine

**Status:** Proposed
**Date:** 2026-07-20

## Purpose and audience

Security-rule authors, backend engineers, analysts, and auditors use this ADR to preserve reproducible detection.

## Context and decision

Security findings must be reproducible and explainable. Immutable rule versions evaluate normalized evidence using deterministic logic; a finding cites its rule version, scan run, affected resource, evidence, severity, and reviewed mappings.

## Alternatives and consequences

AI-only classification is rejected as non-deterministic and unsafe. Direct one-off checks inside collectors blur responsibilities. A rule engine adds schema/version lifecycle work but enables tests, deduplication, historical interpretation, and controlled change.

## Follow-up

Approve the rule schema, contextual-policy inputs, version activation, severity review, fixture corpus, and finding fingerprint algorithm before implementation.
