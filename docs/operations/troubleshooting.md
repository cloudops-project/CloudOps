# Troubleshooting

## Repository and migrations

- Confirm the intended worktree/branch and a clean status before diagnosing.
- `python -m alembic heads` must return only `0019_live_remediation_data_model`.
- A migration container that upgrades successfully but fails its current-head assertion usually
  indicates a stale runtime expectation, not a failed migration.

## API readiness

Health proves process liveness; readiness also depends on required database/configuration checks.
Inspect correlation IDs and sanitized service logs. Do not paste provider bodies or secrets into
issues.

## Workers and scheduler

Check heartbeat freshness, queue depth, due jobs, lease expiration, retry count, and dead-letter
reason. Never manually mark a leased job complete or modify tenant IDs.

## AWS identity

Stop on root, IAM-user static keys, expired SSO, caller-account mismatch, wrong region, missing
role/External ID, or unexpected permissions. Do not fall back to a default profile or invent an ARN.

## Remediation refusal

Refusal is expected when flags are off, emergency stop is active, sandbox approval is absent,
trust is incomplete, approval/snapshot is stale, tags or prefix are missing, caller account differs,
lease is invalid, evidence drifted, or the action is not allowlisted. Fix the underlying prerequisite;
do not weaken gates or edit the database.

## Providers

Bedrock, SES, Jira, SMTP, Slack, and Teams errors must stay sanitized. Use mocks/Stubber locally.
Live provider testing requires explicit provider/account/recipient authorization.
