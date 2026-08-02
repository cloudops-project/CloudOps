# Guide demonstration

The demonstration uses synthetic data and an authorized local user. It proves implemented product
behavior, not live AWS deployment or remediation.

## Five-minute path

1. State the problem: deterministic cloud security evidence without stored AWS keys or AI authority.
2. Show the [architecture](../architecture/system-architecture.md).
3. Log in and show organization/RBAC context.
4. Show assets, findings, deterministic risk components, and compliance mappings.
5. Generate one AI explanation and point out minimized context and advisory status.
6. Show remediation preview, human approval boundary, audit evidence, and current deployment status.

## Ten-minute path

Add AWS role onboarding/trust instructions, a durable discovery job, finding evidence, risk worked
example, notification/Jira draft, owner-only remediation administration status, and a dry-run
execution. Explain why live flags and emergency stop remain safe by default.

## Fifteen-minute technical path

Add tenant-denial evidence, migration head, PostgreSQL job lease/heartbeat behavior, AI hashes and
staleness, exact S3/EC2 allowlists, mandatory tags, immutable snapshot/drift checks, rollback-state
capture, CI jobs, and the controlled sandbox topology/cost boundary.

## Offline fallback

- Use deterministic synthetic inventory and mocked/Stubber provider tests.
- Show retained test output or CI links rather than claiming a provider call.
- Use Mailpit/mock notification and mock remediation.
- If the network or AWS is unavailable, explicitly mark onboarding/provider/live actions as
  simulated or not yet verified.

See the [checklist](demo-checklist.md) and [speaker script](demo-script.md).
