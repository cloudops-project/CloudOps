# Governed live AWS remediation runbook

## Status and authorization boundary

CloudOps implements a default-disabled, two-action AWS executor and an isolated sandbox definition.
Neither has been validated against a live AWS account. No infrastructure has been applied, no
sandbox has been approved, and no live mutation has been executed. This runbook is preparation,
not deployment evidence.

The only supported actions are `s3.enable_public_access_block` and
`ec2.revoke_approved_public_ingress`. Deterministic rules detect the finding; AI cannot select,
approve, or execute remediation. Automatic rollback execution is not implemented.

## Human prerequisites

1. Use a dedicated non-production AWS account and a short-lived administrative AWS SSO session.
2. Confirm the exact account ID and `ap-south-1`; reject an AWS root caller.
3. Review the `infra/sandbox` Terraform plan, current prices, IAM policies, Checkov exceptions, and
   all billable resources. Obtain explicit apply authorization.
4. Apply only the exact reviewed plan through an approved human change process.
5. Deploy CloudOps to the host separately. Verify the instance profile and default Boto3 provider
   chain; never add static access keys.
6. If a Cloudflare hostname is authorized separately, migrate it without changing the sandbox IAM
   or exposing application ports. Cloudflare credentials are outside this repository and runbook.
7. Create distinct discovery and remediation External IDs. Store them only through the approved
   secret/configuration workflow.
8. Onboard the discovery role and validate read-only STS access.
9. Configure the separate remediation role and External ID, then grant sandbox approval with actor,
   timestamp, organization ownership, and audit evidence.

CloudOps provides owner-only administration routes under `/api/v1/aws/accounts/{account_id}`:

- `PUT /remediation-trust` configures a same-account IAM role and returns a server-generated
  remediation External ID once.
- `POST /remediation-trust/rotate` rotates that External ID and revokes sandbox approval.
- `DELETE /remediation-trust` clears trust and approval atomically.
- `POST /sandbox-approval` and `DELETE /sandbox-approval` grant or revoke approval with a mandatory
  audited reason.

These routes only change tenant-scoped database governance state. They do not contact AWS, enable
feature flags, enqueue work, or replace AWS-side trust-policy review. Never edit the database ad
hoc.

## Discovery and approval

1. Run discovery and evaluation. Confirm exact S3 Public Access Block values or EC2
   `SecurityGroupRuleId` evidence is present.
2. Confirm the finding targets only the Terraform-owned, tagged lab resource.
3. Create a preview. Review action version, exact target, immutable snapshot hash, preconditions,
   postconditions, rollback-state requirements, and `dry_run` status.
4. After the normal request has been approved, an owner calls
   `POST /api/v1/remediations/{request_id}/prepare-live`. The server derives the action, target,
   finding evidence, and asset-evidence hash, assigns `live_aws`/`aws`/non-dry-run state, and returns
   the request to `pending_approval`. Client-supplied executor, target, operation, or evidence fields
   are rejected.
5. A separate actor with the existing remediation-approval capability approves the newly prepared
   immutable snapshot. AI cannot prepare or approve it. Preparing does not enqueue or execute it.

## Harness gates

The harness defaults to refusal and never runs in normal CI. It reads bearer and remediation
External ID material from files, never command-line values. It requires all of these exact values:

```text
CLOUDOPS_LIVE_AWS_TESTS=true
EXPECTED_AWS_ACCOUNT_ID=<EXACT_ACCOUNT>
EXPECTED_AWS_REGION=ap-south-1
EXPECTED_REMEDIATION_ROLE_ARN=<EXACT_ROLE_ARN>
EXPECTED_SANDBOX_TAG=AllowCloudOpsRemediation=true
EXPLICIT_CONFIRMATION=RUN-CLOUDOPS-LIVE-AWS-SANDBOX
```

It additionally requires the HTTPS CloudOps URL, organization/request UUIDs, one allowlisted action,
one exact lab resource identifier, an authentication-token file, and a remediation-External-ID
file. Both private files and the generated plan must be outside the repository. Do not paste either
private value into a command, terminal transcript, chat, or screenshot.

First produce and review a sanitized, read-only plan:

```text
python scripts/live_remediation_harness.py plan --plan-file <SECURE_EVIDENCE_PATH>.json
```

This verifies non-root caller account, assumes only the expected remediation role, verifies the
assumed account, reads mandatory tags, enforces the `cloudops-lab-*`/security-group allowlist, and
checks that the tenant-owned request is approved, `live_aws`, non-dry-run, and action-matched.

Execution is a separate command and additionally requires:

```text
EXECUTION_CONFIRMATION=EXECUTE-CLOUDOPS-GOVERNED-REMEDIATION
python scripts/live_remediation_harness.py execute --plan-file <SECURE_EVIDENCE_PATH>.json
```

The command revalidates the plan and only enqueues the fixed CloudOps request. The worker then
reauthorizes the actor and rechecks feature flags, emergency stop, lease, tenant/account, sandbox
approval, role trust, snapshot, target, tags, caller account, drift, and postconditions before the
static executor can mutate anything.

## Action verification and rollback

For S3, confirm only the four bucket Public Access Block fields changed to true; do not change ACLs,
policy, objects, encryption, versioning, or logging. For EC2, confirm only the approved ingress rule
ID is absent and every unrelated rule is unchanged. Run rediscovery/evaluation and verify the
deterministic finding resolves. Preserve sanitized before/after evidence, request IDs, snapshot,
job correlation, and audit events.

Rollback is manual and separately approved. Use the captured exact prior PAB configuration (or
explicit absence) or exact security-group rule structure. Never destructively roll back the database
or infer missing rule fields. Re-run discovery and verification afterward.

## Emergency and incident response

Set `REMEDIATION_EMERGENCY_STOP=true` first, then set `REMEDIATION_LIVE_AWS_ENABLED=false` and
`REMEDIATION_EXECUTION_ENABLED=false`. Stop remediation jobs without disabling unrelated evidence
collection where safe. Revoke the remediation role trust or rotate its External ID after preserving
audit evidence. Inspect CloudTrail, CloudOps audit events, request IDs, lease history, and exact
before/after state. Never log credentials or raw provider errors.

## Shutdown and cleanup

Stop the hosting instance when idle. Review the two-step destroy wrapper in the sandbox runbook;
confirm account, region, state ownership, mandatory tags, and a delete-only allowlisted plan. Capture
sanitized evidence before cleanup. Do not weaken bucket `prevent_destroy` until a human confirms the
bucket is empty and explicitly approves final cleanup.

Remaining production limitations include no live AWS validation, no automatic rollback executor,
no customer-account authorization, and no production deployment evidence.
