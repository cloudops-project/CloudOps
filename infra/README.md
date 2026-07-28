# CloudOps AWS infrastructure

This directory defines the CloudOps staging and production reference platform. It has not been applied to an AWS account in this repository.

## Architecture

Terraform provisions an internet-facing ALB and WAF in public subnets. API, web, scheduler, job worker, migration tasks, and PostgreSQL run in private subnets. ECS task roles are separate from GitHub deployment identities. API and worker roles can assume only the exact customer discovery-role ARNs supplied by onboarding operations. Temporary STS credentials remain inside the application process.

The runtime task secret is an empty Secrets Manager container. Terraform never receives or writes secret values. Before the first task starts, an authorized operator must populate these JSON fields through the approved secret-management process:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `AWS_SES_FROM_EMAIL` when SES delivery is enabled

Optional provider configuration remains non-secret environment metadata. SMTP/provider credentials, when used, belong in the same environment-specific secret or a separately named secret with an equally narrow task-definition reference. The release variables must also provide the public frontend URL, exact trusted hosts, and matching Bedrock model ARN/ID when Bedrock is enabled. Terraform injects the exact API and worker task-role ARNs used in customer trust policies, avoiding an account-root principal.

## State bootstrap

Run `bootstrap/` once with a tightly controlled platform identity. It creates a versioned, KMS-encrypted, public-blocked state bucket; a point-in-time-protected DynamoDB lock table; and GitHub OIDC roles. Record only its non-secret outputs as repository variables. Never commit backend configuration, state, plans, or populated tfvars.

Example backend initialization:

```text
terraform init \
  -backend-config="bucket=<STATE_BUCKET>" \
  -backend-config="key=cloudops/staging.tfstate" \
  -backend-config="region=<AWS_REGION>" \
  -backend-config="dynamodb_table=<LOCK_TABLE>" \
  -backend-config="encrypt=true"
```

## Environment isolation and cost

Staging uses one NAT gateway, one API/web/worker replica, a single-AZ small database, seven-day backups, and 30-day logs. Production fixes two NAT gateways, Multi-AZ RDS, two API/web replicas, two job workers, deletion protection, final snapshots, 35-day backups, and 365-day logs. Changing those production safeguards requires code review.

Route 53 records and ACM certificate issuance are deliberately external inputs because domain ownership is organization-specific. Both production-like staging and production reject an empty certificate ARN.

## Release ordering

Task definitions are immutable and use only `@sha256` images. Terraform creates services at zero tasks and then ignores task-definition and desired-count drift; the release workflow owns those two deployment fields. This prevents a first environment creation or later infrastructure apply from starting application code before the migration gate. The release workflow:

1. applies reviewed infrastructure and registers the new task definitions;
2. runs the additive migration task and requires exit code zero;
3. updates services to the captured task-definition ARNs and declared target counts;
4. waits for the ECS deployment circuit breaker;
5. runs smoke tests;
6. restores prior task definitions and counts on failure.

Schema rollback is never automatic. Database evolution follows expand-and-contract.

## Least privilege and unavoidable wildcards

Customer role assumption uses exact supplied ARNs. Secret retrieval and KMS decrypt use one named secret and key. Bedrock and SES permissions use one approved model and identity. `ecr:GetAuthorizationToken`, ECS task registration/description, CloudWatch alarm reads, and Logs Insights query APIs require `Resource: "*"` or have limited resource-level support; these statements are isolated and do not grant IAM, S3, EC2, RDS, or customer mutation.

The bootstrap deployment roles update ECS only. A separate reviewed Terraform provisioning role is still required for environment creation/update. It must be created by the organization’s cloud-security process with a permissions boundary; no administrator policy or long-lived key is provided here.

## Validation

Local:

```text
terraform fmt -check -recursive infra
terraform -chdir=infra/bootstrap init -backend=false
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/environments/staging init -backend=false
terraform -chdir=infra/environments/staging validate
terraform -chdir=infra/environments/production init -backend=false
terraform -chdir=infra/environments/production validate
```

CI also runs Checkov. Plans must be generated only with placeholder/non-secret variables and stored as protected deployment evidence.

## Live prerequisites

AWS account IDs, ECR repository URLs, OIDC role ARNs, ACM certificates, SES identity, Bedrock model access, Route 53 records, customer role ARNs, runtime secret values, alarm routing, and remote-state backend values are external prerequisites. No `terraform apply`, staging deployment, or production deployment has been performed by this implementation.
