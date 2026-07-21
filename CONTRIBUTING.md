# Contributing to CloudFix

## Purpose and audience

This guide defines collaboration rules for all contributors and reviewers during Stage 0 and later implementation stages.

## Before contributing

Work from a linked issue with acceptance criteria. During Stage 0, submit only documentation, governance, planning, or non-executable configuration. Do not initialize frameworks, add dependencies, credentials, workflow YAML, or cloud resources. Review [development rules](docs/engineering/development-rules.md), [Git workflow](docs/engineering/git-workflow.md), and the [definition of done](docs/engineering/definition-of-done.md).

## Workflow

1. Branch from protected `main` using `feature/<issue>-description`, `fix/<issue>-description`, `docs/<issue>-description`, or `research/<issue>-description`.
2. Make focused commits using Conventional Commits, for example `docs(architecture): define STS trust boundary`.
3. Keep documentation consistent: Version 1 covers EC2, S3, and IAM; AI is advisory; scans are read-only; remediation requires approval.
4. Open a pull request, link the issue, complete the checklist, and request at least one independent reviewer.
5. Obtain designated security/architecture review for authorization, tenancy, IAM, remediation, audit, secrets, AI data handling, or schema-boundary changes.
6. Squash merge after checks and review; delete the short-lived branch.

## Review expectations

Reviewers verify correctness, tenant isolation, least privilege, failure behavior, accessibility, test implications, auditability, and documentation impact. Authors must not approve their own PR. Material architectural changes require an ADR. Never post vulnerabilities or secrets in public issues; follow [SECURITY.md](SECURITY.md).

## Governance proposals

Recommended repository settings are a private repository, protected `main`, pull requests required, one approval minimum, stale approval dismissal, resolved conversations, and restricted force-push/deletion. Dependabot, secret scanning, and code scanning are future setup work; enabling them is not part of Stage 0.
