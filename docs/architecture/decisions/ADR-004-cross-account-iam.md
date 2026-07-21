# ADR-004: Cross-Account IAM with STS

**Status:** Proposed
**Date:** 2026-07-20

## Purpose and audience

AWS engineers, security reviewers, and customer-onboarding designers use this ADR to govern account access.

## Context and decision

Customers must connect AWS accounts without supplying long-lived keys. A customer-deployed template creates a read-only role trusting a designated CloudFix principal with an exact per-connection external ID. Workers call STS `AssumeRole`, hold short-lived credentials only in memory, and use Boto3 for approved EC2/S3/IAM metadata APIs.

## Alternatives and consequences

Stored access keys are rejected. Customer-hosted agents add operational burden for Version 1. Cross-account roles are standard and revocable but require careful principal, external-ID, permission, rotation, and CloudTrail design.

## Security and follow-up

Scanning remains read-only. Remediation uses a distinct action-specific role/path and approval. Review exact policies, partitions, session duration, external-ID protection, and onboarding templates in Stage 3.
