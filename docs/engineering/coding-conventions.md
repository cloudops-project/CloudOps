# Coding Conventions

## Purpose and audience

Future backend and frontend contributors use these conventions to make reviews predictable and boundaries visible.

## Naming

Folders use lowercase kebab-case (`aws-accounts`). Python packages/functions/variables use snake_case; classes use PascalCase; constants use UPPER_SNAKE_CASE. React components and TypeScript types use PascalCase, hooks `useCamelCase`, functions camelCase, and feature folders kebab-case. Database tables are plural snake_case. Rules use `EC2-001`, `S3-001`, `IAM-001`; ADRs use `ADR-001-description.md`.

## Code structure

Prefer small cohesive functions, immutable domain values where practical, explicit types, and dependency injection. Public contracts have concise intent/constraint documentation. Avoid hidden globals, boolean parameter ambiguity, magic strings, premature abstraction, circular imports, and cross-feature internal imports.

## Tooling proposals

Ruff will format and lint Python; Pytest will test it. TypeScript strict mode plus an approved linter/formatter will apply in Stage 1. Generated code, lockfiles, and tool configurations require separate initialization review; none are created in Stage 0.

## Security-sensitive review

Flag authorization, organization scoping, IAM, secrets, evidence redaction, audit behavior, remediation, and AI-boundary changes in the PR and request designated owners.
