# Pull Request

## Purpose and audience

Authors and reviewers use this template to demonstrate scope, risk, validation, and readiness for merge.

## Purpose and linked work

Explain the outcome and link the issue (`Closes #...`). State the stage/milestone and why the change belongs in scope.

## Changes and exclusions

- Changed:
- Deliberately not changed:
- User/security/tenant impact:

## Validation evidence

List reviews, commands/tests, manual scenarios, screenshots/accessibility evidence, or state **documentation-only / not applicable**. Do not invent results or include secrets/customer data.

## Checklist

- [ ] Acceptance criteria and Version 1 EC2/S3/IAM boundary are respected.
- [ ] Organization isolation and server-side authorization were considered.
- [ ] AWS credentials/secrets are absent; scanning stays read-only.
- [ ] Remediation changes require approval, separate permissions, idempotency, and verification.
- [ ] AI remains advisory; inputs are minimized/redacted and outputs validated/untrusted.
- [ ] Errors, logs, audit events, retries, concurrency, and recovery were considered.
- [ ] Tests/accessibility/security checks are appropriate and evidenced.
- [ ] Documentation, ADR/threat model, project memory, and changelog impact are handled.
- [ ] Designated owners were requested for security-sensitive changes.

## Risks, rollout, and rollback

Describe residual risk, dependencies, migration/deployment considerations, rollback or recovery, and open questions.
