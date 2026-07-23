# Customer Onboarding Templates — Stage 0 Placeholder

## Purpose and audience

Future AWS/security engineers and customer administrators will use this area for reviewed CloudFormation and/or Terraform templates described in [AWS onboarding](../../docs/architecture/aws-account-onboarding.md).

Templates will create a least-privilege read-only scan role trusting the exact CloudOps principal with a per-connection external ID. A distinct action-specific role/model will be required for approved remediation. Templates must never request customer access keys.

No template or IAM policy is generated in Stage 0. Exact collector permissions, partition support, principal topology, and template formats require approval and sandbox validation.
