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

Run `bootstrap/` only with a tightly controlled, short-lived platform identity after verifying the
caller account and region. It creates a versioned, KMS-encrypted, public-blocked state bucket; a
point-in-time-protected DynamoDB lock table; and explicitly selected GitHub OIDC roles. It does not
deploy the CloudOps application and does not create ECR repositories. Record only its non-secret
outputs as repository variables. Never commit backend configuration, state, plans, or populated
tfvars.

The safe deployment-role default is staging only:

```hcl
deployment_environments = ["staging"]
```

Creating a production deployment role requires an explicit, separately reviewed selection:

```hcl
deployment_environments = ["staging", "production"]
```

Only `staging` and `production` are supported. Empty or unknown environment selections fail
validation. Staging bootstrap authorization never authorizes the production selection.

The GitHub Actions OIDC provider mode is also explicit and fail closed. Inspect the target account
with an approved AWS SSO profile before choosing a mode:

```text
aws sts get-caller-identity --profile <STAGING_SSO_PROFILE>
aws iam list-open-id-connect-providers --profile <STAGING_SSO_PROFILE>
```

Do not continue until the caller account and selected region match the approved staging target.
Never display credential material. To create the provider when the account does not already have
the GitHub Actions provider:

```hcl
github_oidc_provider_mode         = "create"
existing_github_oidc_provider_arn = ""
```

To reuse the account's existing GitHub Actions provider without creating or importing another:

```hcl
github_oidc_provider_mode         = "existing"
existing_github_oidc_provider_arn = "<EXISTING_GITHUB_OIDC_PROVIDER_ARN>"
```

Create mode rejects a supplied existing ARN. Existing mode requires the exact syntactically valid
GitHub Actions provider ARN. The resolved ARN is used by the same repository-, branch-, and
environment-restricted trust policies in both modes. Bootstrap outputs include the resolved OIDC
provider ARN, whether it is managed by this root, the publishing-role ARN, and a deployment-role
ARN map keyed only by selected environment.

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

Route 53 records and ACM certificate issuance are deliberately external inputs because domain
ownership is organization-specific. HTTPS is the default for every environment, and production
always rejects an empty certificate ARN.

### Temporary HTTP-only staging

Staging alone has an explicit, default-off escape hatch for the period before DNS ownership and ACM
certificate validation complete. It does not exist in the production root. The exact temporary
staging values are:

```hcl
enable_http_only_staging = true
certificate_arn          = ""
frontend_url             = "http://<TEMPORARY_STAGING_HOST>"
allowed_origins          = ["http://<TEMPORARY_STAGING_HOST>"]
trusted_hosts            = ["<TEMPORARY_STAGING_HOST>"]
bedrock_model_arn        = ""
bedrock_model_id         = ""
ses_identity_arn         = ""
```

This creates only a port-80 listener, labels the staging resources with
`TemporaryHttpStaging = "true"`, emits a warning output, disables secure cookies and HSTS for that
staging runtime, and keeps Bedrock and SES disabled. Traffic is unencrypted: do not enter real
credentials, secrets, personal data, customer data, or other sensitive test content. WAF, private
ECS tasks, restricted security-group paths, encrypted private RDS, Secrets Manager, logging, alarms,
tenant authorization, and dry-run remediation controls remain in place.

Return to HTTPS immediately after DNS and ACM are ready:

1. Validate the certificate in the staging region and record its ARN.
2. Change all staging URLs and origins to `https://`.
3. Set `certificate_arn` to the validated ARN.
4. Set `enable_http_only_staging = false`.
5. Review a plan proving port 80 is removed and only the TLS 1.2/1.3 port-443 listener remains.
6. Apply only after normal staging authorization, then verify HTTPS, secure cookies, HSTS, WAF, and
   health checks before permitting sensitive or live-provider validation.

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
terraform -chdir=infra/environments/staging test
terraform -chdir=infra/environments/production init -backend=false
terraform -chdir=infra/environments/production validate
python infra/tests/test_temporary_http_staging.py
```

CI also runs Checkov. Plans must be generated only with placeholder/non-secret variables and stored as protected deployment evidence.

Credential-free bootstrap tests:

```text
terraform -chdir=infra/bootstrap test
python infra/bootstrap/tests/test_bootstrap_static.py
```

These tests use Terraform's mock provider and static source assertions; they do not call AWS.

## Live prerequisites

AWS account IDs, ECR repository URLs, OIDC role ARNs, ACM certificates, SES identity, Bedrock model access, Route 53 records, customer role ARNs, runtime secret values, alarm routing, and remote-state backend values are external prerequisites. No `terraform apply`, staging deployment, or production deployment has been performed by this implementation.

## Governed remediation sandbox

The separate [`sandbox/`](sandbox/) root defines a controlled, billable lab for future explicitly
authorized live-remediation testing. It is not part of staging or production and has not been
applied. See the [AWS remediation sandbox runbook](../docs/operations/aws-remediation-sandbox.md)
for its exact resource, identity, cost, and operator-safety boundaries.
