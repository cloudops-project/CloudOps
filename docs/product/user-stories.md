# Version 1 User Stories

## Purpose and audience

Product owners and delivery teams use these stories to seed issues and acceptance criteria; they do not imply completion.

## Identity and tenancy

- As an Organization Administrator, I can create an organization, invite members, and assign scoped roles so access matches responsibility.
- As any user, I can access only organizations and records for which I have an active membership.
- As an Auditor, I can trace membership and role changes as audit events.

## AWS and scanning

- As an Administrator, I can register a role ARN and external-ID-backed connection without entering access keys.
- As a Security Analyst, I can start or schedule an EC2/S3/IAM scan and see bounded job status and failures.
- As a Cloud Engineer, I can inspect normalized asset evidence and the exact deterministic rule version.

## Findings and response

- As an Analyst, I can filter, assign, suppress with policy, or request remediation while retaining status history.
- As an authorized approver, I can approve or reject an idempotent remediation request with rationale.
- As an Engineer, I can choose manual work or an approved action-specific playbook and verify completion by rescan.
- As a risk owner, I can accept risk with justification, owner, expiry, and audit evidence.

## Assistance and communication

- As a user, I can request a redacted AI explanation and distinguish it from deterministic evidence.
- As an Analyst, I can draft a Jira ticket and send an approved email/Teams notification without exposing secrets.
- As a Stakeholder, I can view an accessible posture report with caveats and provenance.

## Open questions

Backlog refinement must define exact role-permission matrices, risk-score inputs, export formats, notification priority, and rule counts after research.
