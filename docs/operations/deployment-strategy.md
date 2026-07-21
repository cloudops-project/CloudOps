# Deployment Strategy

## Purpose and audience

Platform, security, and engineering teams use this proposed path for later deployment. Stage 0 creates no Dockerfiles, Terraform resources, pipelines, or cloud services.

GitHub Actions is the proposed CI/CD platform. After Stage 14 approval, builds should produce immutable artifacts, run quality/security gates, generate provenance, use short-lived OIDC cloud credentials, and promote the same artifact through development, staging, and production with protected-environment approval. Terraform manages CloudFix-owned infrastructure; it is not the scanning engine. Boto3 handles runtime discovery and approved actions.

Deploy API, worker, web assets, PostgreSQL, queue, audit archive, monitoring, and secrets through independently scalable but version-compatible units. Database migrations require backup/readiness checks, review, observability, and roll-forward/rollback strategy. Prefer rolling or blue/green deployment based on measured cost and stateful compatibility.

Remediation Lambda functions are narrowly scoped, versioned playbooks and must not be deployed or invoked without customer authorization and security review. Open decisions: AWS topology/region, compute services, managed Redis versus SQS, artifact registry, rollout method, and production approval roles.
