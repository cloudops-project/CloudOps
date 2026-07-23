# ADR-011: Deliver AWS account onboarding in Stage 2

**Date:** 2026-07-22
**Status:** Accepted by Stage 2 implementation authorization

## Context

ADR-007 consolidated the original foundation and authentication work into Stage 1 and temporarily reserved Stage 2, leaving AWS onboarding numbered Stage 3. After Stage 1 independent verification, the product owner explicitly authorized AWS account onboarding as Stage 2. The implementation needs a durable record of this numbering change without rewriting ADR-007 history.

## Decision

Stage 2 is AWS account onboarding. CloudOps stores an organization-scoped AWS account ID, role ARN, unique external ID, and validation state. It uses `sts:AssumeRole` and the returned temporary credentials only for `sts:GetCallerIdentity`; temporary credentials are never persisted. Owners and admins may manage connections. No resource discovery or scanning is included.

This ADR supersedes only ADR-007's reservation of Stage 2 and the Stage 3 numbering of onboarding. ADR-004 remains the cross-account IAM security decision. Later executable stages remain deferred.

## Alternatives

- Keep Stage 2 empty and implement onboarding as Stage 3. Rejected because it conflicts with the authorized delivery stage.
- Accept customer access keys. Rejected because long-lived credentials violate the threat model.
- Provision customer IAM automatically. Rejected because Stage 2 only generates reviewed instructions and policies.

## Consequences

- The API depends on boto3 and requires a configured trusted CloudOps AWS principal ARN.
- Customers create `CloudOpsReadOnlyRole`, attach AWS managed `SecurityAudit`, and apply the generated external-ID trust condition.
- Validation is synchronous and limited to STS identity verification. Production scaling and background execution are deferred.
- Existing future-stage numbering must be read in light of this ADR; Stage 3 begins asset discovery.

## Security and tenant implications

Every lookup verifies active organization membership and the centralized AWS-account-management capability. Account IDs and role ARNs are unique within an organization, external IDs are globally unique, audit metadata excludes credentials, and failures expose sanitized reason codes.

## Validation

Validate model/migration parity on disposable PostgreSQL, account/ARN/external-ID rules, owner/admin RBAC, tenant isolation, mocked STS success/failure/account mismatch, audit events, and frontend flows. No live customer account is required for automated tests.

## Follow-up

Stage 3 may consume only connected accounts and must introduce explicit discovery permissions and bounded collectors without expanding Stage 2 into scanning.
