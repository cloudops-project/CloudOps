# ADR-009: Tailwind CSS for the CloudOps Frontend

**Status:** Accepted by implementation authorization
**Date:** 2026-07-22

## Purpose and audience

Frontend, design, accessibility, and architecture reviewers use this ADR to govern Stage 1 styling and component ownership.

## Context

Stage 0 selected Material UI. The authorized Stage 1 technology list and official CloudOps design system specify Tailwind CSS and Lucide React.

## Decision

Use Tailwind CSS with semantic CSS design tokens. Build small feature-oriented React components rather than adding a second component framework. Use Lucide React for icons. React, strict TypeScript, Vite, React Router, TanStack Query, React Hook Form, and Zod remain unchanged.

This supersedes the Material UI selection in the Stage 0 system overview and development rules. It does not change the feature-based frontend architecture.

## Alternatives considered

- Retain Material UI: rejected because the authorized Stage 1 stack explicitly selects Tailwind and the official token system can be implemented directly.
- Use Material UI and Tailwind together: rejected because duplicate styling systems increase bundle size, inconsistency, and accessibility review cost.
- Build unstyled CSS only: rejected because it would not satisfy the selected frontend stack.

## Consequences and validation

Material UI is superseded and must not be installed alongside Tailwind. The team owns accessible component behavior, focus management, validation, responsive states, and token consistency. Frontend lint, type/build, component tests, keyboard checks, and design-token review must pass.
