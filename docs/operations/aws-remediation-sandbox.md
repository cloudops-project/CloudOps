# AWS remediation sandbox infrastructure

> **Current operational status:** source and automated validation are implemented. Operator-reported
> AWS SSO setup is incomplete; identity preflight, saved plan, apply, EC2 creation, CloudOps
> deployment, Cloudflare, live remediation, rollback, and teardown have not been verified. Do not
> infer account or resource state from this document.

This Terraform root defines—but has not created—a dedicated CloudOps lab in `ap-south-1`. It is
separate from staging and production. Applying or destroying it requires a human-approved AWS
account, a reviewed plan, short-lived non-root identity, and a separate operational authorization.
The operator qualification uses Terraform `1.10.5`; `infra/sandbox/versions.tf` accepts Terraform
`>=1.10,<2`, and the committed provider lock selects AWS provider `5.100.0` within `~>5.100`.

## Scope and cost

The default plan contains one `t3a.large` hosting instance with a 50 GiB encrypted gp3 root disk,
one VPC, two subnets, an internet gateway, IAM roles, an empty versioned S3 test bucket, and one
intentional test security group. The optional private `t3a.nano` instance is disabled. There is no
NAT Gateway, load balancer, managed database, or Elastic IP. EC2, EBS, S3, CloudWatch detailed
monitoring, and data-transfer charges may apply while resources exist; obtain a current AWS Pricing
Calculator estimate before any apply.

VPC flow-log delivery is intentionally omitted from this short-lived, no-customer-data lab to avoid
continuous logging infrastructure cost. This is a documented Checkov exception and a production
limitation, not a precedent for staging or production. Host, application, Terraform, CloudTrail,
and remediation request-ID evidence remain required.

The hosting instance has no public application ports. SSH is limited to one explicit administrator
CIDR, IMDSv2 is required, the root disk is encrypted, and the workload uses an instance profile.
Prefer Session Manager. A public ephemeral address supplies outbound HTTPS for SSM, packages, and
a separately authorized tunnel; no Cloudflare resource is managed here.

## Identity design

- The platform instance role has `AmazonSSMManagedInstanceCore` and may assume only the two exact
  sandbox roles.
- The discovery role has `SecurityAudit` plus the list/read calls needed for exact S3 Public Access
  Block and EC2 security-group-rule evidence.
- The remediation role uses a distinct External ID. It can change only the lab bucket Public Access
  Block and revoke or restore ingress on the exact Terraform-owned test security group. Describe
  APIs use `Resource = "*"` where AWS does not support resource scoping.
- No role can mutate IAM, delete buckets or objects, terminate instances, or delete security groups.

## Intentional findings

Account-level S3 Public Access Block remains fully enabled. The empty `cloudops-lab-*` bucket has an
intentionally incomplete bucket-level configuration so deterministic discovery can detect it
without making data public. The tagged test security group intentionally permits TCP/22 from
`0.0.0.0/0`; it is not attached to the hosting instance. The optional test instance is disabled by
default, has no public IPv4 address, and must never contain sensitive data.

## Safe operator workflow

Use `scripts/aws-sandbox.ps1` on Windows or `scripts/aws-sandbox.sh` on POSIX systems. These wrappers
delegate to the same fixed-operation Python tool. They never accept arbitrary AWS operations.

```text
python scripts/aws_sandbox.py validate
python scripts/aws_sandbox.py preflight --expected-account-id <EXACT_ACCOUNT> --region ap-south-1 --profile <SSO_PROFILE>
python scripts/aws_sandbox.py plan --expected-account-id <EXACT_ACCOUNT> --region ap-south-1 --profile <SSO_PROFILE> --plan-file <SECURE_PATH>.tfplan
python scripts/aws_sandbox.py cost-inventory --plan-file <SECURE_PATH>.tfplan
python scripts/aws_sandbox.py prepare --expected-account-id <EXACT_ACCOUNT> --region ap-south-1 --profile <SSO_PROFILE>
```

The plan command is read-only but contacts AWS. Do not run it without explicit identity and plan
authorization. This implementation session ran no AWS command and no Terraform apply or destroy.

Destroy is deliberately two-step. The first command creates a destroy plan; a separately reviewed
command adds `--execute-reviewed-plan`. Both require the exact phrase
`DESTROY-CLOUDOPS-AWS-SANDBOX`, the expected account and region, and the expected state owner.
Bucket `prevent_destroy` must be separately reviewed before final cleanup; never weaken it merely
to make automation pass.

## Shutdown and evidence

Stop the hosting instance when the lab is idle, understanding that EBS and S3 charges continue.
Before any cleanup, retain only sanitized Terraform plan summaries, resource identifiers, test
results, and audit records. Never retain state, External IDs, credentials, or populated variable
files in source control. A human must verify state ownership and empty resources before reviewing
the destroy plan.
