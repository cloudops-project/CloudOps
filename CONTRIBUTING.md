# Contributing to CloudFix

CloudFix uses the CloudOps name in runtime components and historical records. Contributors must treat current source, migrations, tests, infrastructure definitions, and workflows as stronger evidence than older planning text.

## Workflow

1. Start from the approved baseline and a short-lived `feature/`, `fix/`, `docs/`, or `research/` branch.
2. Link work to acceptance criteria and keep changes focused.
3. Stage reviewed files explicitly, for example `git add -- docs/file-one.md docs/file-two.md`.
4. Use Conventional Commits such as `docs(architecture): reconcile current job flow`.
5. Run proportionate checks and record whether evidence is local, reported, or externally retained.
6. Open a pull request; obtain independent review and designated security/architecture review for authorization, tenancy, IAM, remediation, audit, secrets, AI data handling, or schema-boundary changes.
7. Merge only through the protected branch process after required checks and approvals.

Never commit secrets, use broad staging, push directly to shared branches, force-push shared branches, deploy without authorization, or test live AWS without explicit opt-in. Version 1 remains EC2/S3/IAM focused; deterministic rules detect findings; AI is advisory; remediation is dry-run only unless future code and authorization prove otherwise.

## Review expectations

Review correctness, tenant isolation, least privilege, failure behavior, accessibility, tests, auditability, migration safety, operations, and documentation impact. Authors do not approve their own changes. Material architecture changes require an ADR. Report vulnerabilities through [SECURITY.md](SECURITY.md), never through a public issue.

Repository protection, required reviewers, secret scanning, dependency automation, and code scanning are externally administered controls. Their live configuration must be verified rather than inferred from repository files.
