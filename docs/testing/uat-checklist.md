# CloudOps V1 UAT evidence template

Record environment, commit, API/web digests, migration head, tester, date, and evidence links.

## Transport prerequisite

- [ ] HTTPS is active before any credential, customer-data, sensitive, Bedrock, or SES test.
- [ ] If the temporary HTTP-only staging escape hatch is active, UAT is limited to non-sensitive
      infrastructure health checks with synthetic public data.
- [ ] Temporary HTTP mode reports port 80 and its warning output; WAF and private ECS/RDS boundaries
      remain present.
- [ ] Full UAT remains blocked until DNS and ACM are ready, HTTP mode is disabled, port 443 is the
      only public listener, and secure cookies plus HSTS are restored.

## Tenant and access

- [ ] Owner/member/viewer/admin capabilities match policy.
- [ ] Organization A cannot infer Organization B list/detail/update/delete/export/job data.
- [ ] External ID is absent from normal account responses and available only to authorized onboarding.
- [ ] Audit export is tenant-scoped and contains no secret sentinel.

## AWS discovery

- [ ] Workload identity uses no static access key.
- [ ] Exact customer role and External ID are assumed.
- [ ] caller account identity is verified.
- [ ] discovery remains read-only and partial failures are visible.
- [ ] credentials expire/refresh without persistence.

## Jobs and providers

- [ ] Scheduler enqueues one occurrence across replicas.
- [ ] worker lease/heartbeat/retry/dead-letter paths operate.
- [ ] Bedrock synthetic advisory is schema-valid and non-authoritative.
- [ ] SES synthetic approved delivery records sanitized evidence.
- [ ] notification approval changes/revocation block delivery.

## Remediation

- [ ] Preview and immutable snapshot are visible.
- [ ] unauthorized approval/execution is rejected.
- [ ] stale evidence and altered snapshots fail closed.
- [ ] kill switch blocks execution.
- [ ] dry run records no AWS mutation.

## Release and recovery

- [ ] exact staging-tested digests reach the deployment.
- [ ] migration task exits zero before service movement.
- [ ] readiness/smoke tests pass.
- [ ] rollback rehearsal restores previous tasks.
- [ ] backup restore rehearsal meets recorded RPO/RTO.
- [ ] alarms route to an acknowledged operator.

## Decision

- Result: PASS / FAIL
- Exceptions:
- Residual risks:
- Product approval:
- Security approval:
- Operations approval:
