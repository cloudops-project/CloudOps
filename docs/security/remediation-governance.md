# Remediation governance

CloudOps separates proposal, approval, live preparation, execution, verification, and rollback
planning. Mock/dry-run is the default. Arbitrary AWS operations and user-supplied API dispatch are
not supported.

## Owner-only administration

| Method and route | Purpose |
|---|---|
| `GET /api/v1/aws/accounts/{account_id}/remediation-administration` | Safe trust and approval status |
| `PUT /api/v1/aws/accounts/{account_id}/remediation-trust` | Configure same-account IAM role and distinct External ID |
| `POST /api/v1/aws/accounts/{account_id}/remediation-trust/rotate` | Rotate External ID and revoke approval |
| `DELETE /api/v1/aws/accounts/{account_id}/remediation-trust` | Atomically clear trust and approval |
| `POST /api/v1/aws/accounts/{account_id}/sandbox-approval` | Grant approval with mandatory reason |
| `DELETE /api/v1/aws/accounts/{account_id}/sandbox-approval` | Revoke approval with mandatory reason |
| `POST /api/v1/remediations/{request_id}/prepare-live` | Server-prepare an eligible approved request |

Operations require organization-owner capability, tenant-scoped row-locked loading, and immutable
audit events. Cross-tenant IDs use not-found behavior. IAM user/malformed/wrong-account ARNs are
rejected. Generated remediation External IDs are disclosed once and omitted from list/detail
responses afterward. Trust changes revoke sandbox approval atomically. Preparing live work returns
the request to pending approval and does not enqueue or execute it.

## Execution gates

Live execution requires both execution flags, live executor selection, `live_aws` mode, emergency
stop inactive, current approval, complete sandbox approval metadata, separate remediation role and
External ID, supported finding/action, matching tenant/account/region/target, valid immutable
snapshot hash and preconditions, mandatory resource tags, verified caller account, valid lease, and
idempotency protection.

Required tags are `CloudOpsLab=true`, `Environment=cloudops-test`, and
`AllowCloudOpsRemediation=true`.

## Allowlisted actions

### `s3.enable_public_access_block`

The target must be an S3 bucket whose name begins `cloudops-lab-`. CloudOps reads tags and the exact
four Public Access Block values, compares them with immutable evidence, calls only
`PutPublicAccessBlock` to set all four true, and verifies all four. Evidence records exact prior
configuration or absence, after state, provider request IDs, verification, and rollback state.
Bucket policy, ACL, objects, encryption, versioning, and logging are out of scope.

### `ec2.revoke_approved_public_ingress`

The target requires exact region, group ID, VPC ID, `SecurityGroupRuleId`, protocol, ports, and
IPv4/IPv6 source evidence. Egress is rejected. CloudOps revokes only the approved exact rule ID,
verifies its absence, and verifies unrelated rules are unchanged. Exact rollback rule data and
request IDs are retained.

## Rollback limitation

Rollback state capture is implemented and tested with doubles. Automatic rollback is not enabled;
restoration requires a separately governed, human-approved procedure. No live remediation or live
rollback has been operationally tested.
