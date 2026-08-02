# CloudOps current status

Audited against repository commit `bec5753ad127d8ed8968d539ee625130c6a2e06f`. A check mark means
the stated evidence exists; it does not imply deployment. “CI verified” refers to the seven-job
GitHub Actions CI workflow for this commit. Operational and deployment columns require retained
external evidence, not source code alone.

| Capability | Implemented | Automated tests | CI verified | Operationally tested | Deployed |
|---|:---:|:---:|:---:|:---:|:---:|
| Authentication and RBAC | Yes | Yes | Yes | Not yet verified | No |
| Tenant isolation | Yes | Yes | Yes | Not yet verified | No |
| AWS account onboarding | Yes | Yes (mocked/Stubber) | Yes | Not yet verified | No |
| AWS discovery | Yes | Yes (mocked/Stubber) | Yes | Not yet verified | No |
| Finding generation | Yes | Yes | Yes | Not yet verified | No |
| Compliance assessment | Yes | Yes | Yes | Not yet verified | No |
| Deterministic risk scoring | Yes | Yes | Yes | Not yet verified | No |
| AI explanations | Yes | Yes (mocked/Stubber) | Yes | Not yet verified | No |
| AI data sanitization | Yes | Yes | Yes | Not yet verified | No |
| Jira integration | Yes | Yes (mocked) | Yes | Not yet verified | No |
| Remediation preview and approval | Yes | Yes | Yes | Not yet verified | No |
| Privileged remediation administration | Yes | Yes | Yes | Not yet verified | No |
| S3 allowlisted executor | Yes, default-disabled | Yes (mocked/Stubber) | Yes | No | No |
| EC2 security-group executor | Yes, default-disabled | Yes (mocked/Stubber) | Yes | No | No |
| Controlled AWS sandbox Terraform | Yes | Static/Terraform tests | Yes | No | No |
| EC2 deployment | Planned runbook | No | N/A | No | No |
| Cloudflare exposure for AWS sandbox | Not authorized | No | N/A | No | No |
| Live S3 remediation | Code exists | No live test | N/A | No | No |
| Live security-group remediation | Code exists | No live test | N/A | No | No |
| Rollback-state capture | Yes | Yes | Yes | No live rollback | No |

## Current operational gate

Operator-reported state, not independently verified by repository contents:

- AWS IAM Identity Center (SSO) setup is incomplete.
- AWS identity preflight has not completed.
- No sandbox Terraform plan exists and apply is not authorized.
- No sandbox resources or EC2 host have been created through this workflow.
- CloudOps has not been deployed to the sandbox.
- Cloudflare is not authorized for this deployment phase.
- No live AWS remediation or rollback exercise has occurred.

The next safe sequence is identity confirmation in a dedicated non-production account, offline
validation, a saved and reviewed Terraform plan, explicit apply authorization, deployment with
live remediation disabled, workload-identity verification, and separately approved controlled
tests. See the [sandbox runbook](../operations/aws-remediation-sandbox.md).
