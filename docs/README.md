# CloudOps documentation

This index is the canonical entry point for maintained CloudOps documentation. Implementation
claims are qualified as **Implemented**, **Unit tested**, **Integration tested**, **CI verified**,
**Operationally tested**, **Deployed**, **Planned**, or **Not yet verified**. Source code,
migrations, tests, workflows, and operational scripts take precedence over prose.

## Start here

- [Product overview](product/overview.md)
- [Current status](product/current-status.md)
- [System architecture](architecture/system-architecture.md)
- [Security controls](security/security-controls.md)
- [Local development](operations/local-development.md)
- [Testing strategy](testing/test-strategy.md)
- [Current release status](release/current-release-status.md)
- [Guide demonstration](demo/guide-demonstration.md)

## Product

- [Product requirements](../PRD.md)
- [Scope](product/scope.md)
- [Personas](product/personas.md)
- [User stories](product/user-stories.md)
- [Glossary](product/glossary.md)

## Architecture

- [System architecture](architecture/system-architecture.md)
- [Data flow](architecture/data-flow.md)
- [Trust boundaries](architecture/trust-boundaries.md)
- [AWS role architecture](architecture/aws-role-architecture.md)
- [Database design](architecture/database-design.md)
- [Deployment topology](architecture/deployment-topology.md)
- [API contracts](../API_CONTRACTS.md)
- [Data model](../DATA_MODEL.md)
- [Architecture decisions](architecture/decisions/README.md)

## Security

- [Threat model](security/threat-model.md)
- [Security controls](security/security-controls.md)
- [Credential handling](security/credential-handling.md)
- [Tenant isolation](security/tenant-isolation.md)
- [AI data minimization](security/ai-data-minimization.md)
- [Remediation governance](security/remediation-governance.md)

## Operations

- [Local development](operations/local-development.md)
- [Self-hosted deployment](operations/self-hosted-deployment.md)
- [AWS remediation sandbox](operations/aws-remediation-sandbox.md)
- [EC2 deployment runbook](operations/ec2-deployment-runbook.md)
- [Live AWS remediation runbook](operations/live-aws-remediation-runbook.md)
- [Rollback and recovery](operations/rollback-and-recovery.md)
- [Troubleshooting](operations/troubleshooting.md)
- [Teardown and cost control](operations/teardown-and-cost-control.md)

## Testing, release, and handover

- [Test strategy](testing/test-strategy.md)
- [CI pipeline](testing/ci-pipeline.md)
- [Security validation](testing/security-validation.md)
- [Current release status](release/current-release-status.md)
- [V1 handover](release/v1-handover.md)
- [New-chat context](../NEW_CHAT_CONTEXT.md)
- [Session memory](../memory.md)
- [Phases](../phases.md)
- [Changelog](../CHANGELOG.md)

## Demonstration

- [Guide demonstration](demo/guide-demonstration.md)
- [Demo checklist](demo/demo-checklist.md)
- [Demo script](demo/demo-script.md)

Historical plans remain under `docs/planning/`. They are not implementation evidence unless a
maintained status document explicitly incorporates them.
