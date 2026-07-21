# ADR-001: Feature-Based Monorepo

**Status:** Proposed
**Date:** 2026-07-20

## Purpose and audience

Architects and all contributors use this ADR to govern repository boundaries. A five-member team needs coordinated frontend, backend, worker, infrastructure, shared contracts, tests, and documentation without premature package fragmentation.

## Decision

Use one `cloudfix` repository organized primarily by business feature within each future app. Keep shared packages minimal, prohibit a generic `utils` area, circular dependencies, and direct access to another feature's internal repository.

## Alternatives and consequences

Separate repositories offer independent releases but increase coordination and governance overhead. A layer-only monolith makes feature ownership and boundaries less visible. The monorepo simplifies atomic reviews and shared standards, but CI scope and ownership rules must prevent coupling.

## Validation and follow-up

Approve dependency rules and CODEOWNERS before Stage 1; revisit only when release cadence or scaling evidence justifies separation.
