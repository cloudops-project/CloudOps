# Deployment decision record

## Decision

**NO-GO for production deployment. GO only for repository/CI qualification work.**

Baseline commit `7926ab0f81daeca4234a13b5d92218b67f09defa` has successful seven-job CI and a current
documentation set. It does not have verified AWS identity, saved Terraform plan, sandbox/staging
apply, deployed health, live provider/remediation evidence, restore, rollback, alert delivery,
performance qualification, UAT, or production authorization.

## Conditions for changing the decision

1. Phase 1 baseline is reviewed and merged through the pull-request workflow.
2. Software/security reports prove no unresolved Critical and no unaccepted High findings.
3. A dedicated non-production account and short-lived non-root identity are verified.
4. Reviewed saved plans, cost limits, and exact authorization precede every apply.
5. Sandbox and managed staging pass health, security, discovery, provider, remediation, recovery,
   performance, observability, and UAT gates with retained evidence.
6. Production plan, canary, rollback point, on-call ownership, and budget are approved.
7. Live remediation remains disabled in production unless separately governed later.

## Immutable-artifact decision

Production must promote the exact staging-tested image digests. Database changes remain additive;
rollback restores application artifacts or uses a safe forward fix rather than destructively
downgrading schema.
