# ADR-010: CloudOps Implementation Product Name

**Status:** Accepted by implementation authorization
**Date:** 2026-07-22

## Purpose and audience

Product, design, engineering, and documentation contributors use this ADR to avoid mixed product naming during implementation.

## Context

Stage 0 documents and the repository are named CloudFix. Subsequent design authorization established a “CloudOps” UI standard, and the Stage 1 implementation request consistently names the platform CloudOps.

## Decision

Use **CloudOps** as the application display and current product name from Stage 1 onward. Preserve the existing repository directory `cloudfix` and historical CloudFix references where they describe the original Stage 0 record. Update active setup, architecture, design, and project-memory documents as they are touched.

This supersedes CloudFix as the active product name while retaining it in historical ADR context and the local directory path.

## Alternatives considered

- Keep CloudFix everywhere: rejected because the repository remote and repeated implementation authorization establish CloudOps as current.
- Rewrite every historical reference: rejected because ADR provenance and the tagged Stage 0 record must remain intelligible.
- Rename the local/remote repository during Stage 1: rejected as unnecessary scope and because the remote is already CloudOps.

## Consequences

Historical ADRs remain unchanged for provenance. A repository/remote rename, domain, trademark review, and package-publication name are outside Stage 1.
