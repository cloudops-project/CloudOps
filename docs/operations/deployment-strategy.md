# Deployment Strategy

> See [DEPLOYMENT.md](../../DEPLOYMENT.md) at the repository root for how the local two-day demo
> relates to (and does not exercise) this release path. This document remains authoritative for the
> actual staging/production release path below.

## Current release path (authoritative)

The implemented GitHub Actions release pipeline uses short-lived OIDC identities, builds API/web once, generates SBOMs, scans images, pushes once, captures ECR digests, promotes those exact digests to staging, runs an additive one-shot migration, then moves ECS services. Production planning preserves the exact binary and JSON plan as review evidence; only the subsequent apply job enters the protected GitHub Environment. Production also requires the explicit workflow input and exact `ALLOW_PRODUCTION_DEPLOY=YES` variable.

Terraform initially creates ECS services at zero tasks, and service resources deliberately ignore task-definition and desired-count drift. This lets infrastructure register new definitions without starting a new environment or moving existing services before the migration succeeds. After migration, the workflow activates the declared target counts and exact task definitions. Production records prior task definitions and restores them on rollout or smoke failure; schema downgrade is never automatic.

Required evidence is the release manifest, SBOMs, scan output, reviewed Terraform plan JSON, migration task ARN/exit code, service events, alarm states, smoke output, approver, and final task definitions.

The workflow and Terraform are implemented but have not been run against AWS staging or production. Cloud-side state, OIDC, ECR, secret content, ACM/DNS, SES, Bedrock, alerting, and protected-environment prerequisites remain external gates.

An additional organization-managed single-host option is implemented in `compose.selfhost.yml`.
It uses a named Cloudflare Tunnel and a migration-gated private Docker topology. It is not the
Terraform AWS staging/production topology and does not prove AWS deployment, managed backups,
canary, or rollback. See [Self-hosted Cloudflare deployment](self-hosted-cloudflare-deployment.md).

Staging includes a temporary, explicit, default-off HTTP-only escape hatch for use solely while DNS
and ACM validation are pending. In that mode traffic is unencrypted, so credentials, customer data,
sensitive security validation, live Bedrock, and live SES must remain out of scope. WAF and private
task/database networking remain enabled. Production has no HTTP-only input and stays HTTPS-only.
The escape hatch must be removed as soon as a validated staging certificate is available; the
reviewed migration plan must replace port 80 with the TLS port-443 listener before normal staging
qualification continues. See `infra/README.md` for the exact temporary values and removal sequence.

The historical text below predates the implemented Docker, Terraform, and pipeline files and is retained only as planning history.

## Purpose and audience

Platform, security, and engineering teams use this proposed path for later deployment. Stage 0 creates no Dockerfiles, Terraform resources, pipelines, or cloud services.

GitHub Actions is the proposed CI/CD platform. After Stage 14 approval, builds should produce immutable artifacts, run quality/security gates, generate provenance, use short-lived OIDC cloud credentials, and promote the same artifact through development, staging, and production with protected-environment approval. Terraform manages CloudOps-owned infrastructure; it is not the scanning engine. Boto3 handles runtime discovery and approved actions.

Deploy API, worker, web assets, PostgreSQL, queue, audit archive, monitoring, and secrets through independently scalable but version-compatible units. Database migrations require backup/readiness checks, review, observability, and roll-forward/rollback strategy. Prefer rolling or blue/green deployment based on measured cost and stateful compatibility.

Remediation Lambda functions are narrowly scoped, versioned playbooks and must not be deployed or invoked without customer authorization and security review. Open decisions: AWS topology/region, compute services, managed Redis versus SQS, artifact registry, rollout method, and production approval roles.
