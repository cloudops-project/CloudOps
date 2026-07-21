# Low-Fidelity Wireframes

## Purpose and audience

Designers, stakeholders, accessibility reviewers, and frontend engineers use these text wireframes to review information priority before React implementation.

## Entry and setup

```text
LOGIN                         ORGANIZATION SETUP
+ CloudFix ----------------+  + Create organization --------+
| [Sign in with SSO]       |  | Name [___________________]  |
| Security/privacy links   |  | [Create] [Cancel]           |
+--------------------------+  +------------------------------+

AWS ACCOUNT ONBOARDING
+ Step 1 Template -- Step 2 Deploy -- Step 3 Validate -- Step 4 Result --+
| External ID: â€¢â€¢â€¢â€¢ [Copy] | CloudFormation | Terraform (planned)          |
| Role ARN [________________________________] [Validate connection]         |
| Never enter AWS access keys. Read-only permissions summary.              |
+--------------------------------------------------------------------------+
```

## Operational views

```text
MAIN DASHBOARD                 ASSET INVENTORY / SCAN HISTORY
+ Org â–¾ | Last scan/status --+ + Filters: account service region status --+
| Posture summary + caveat   | | Asset/resource | service | observed | ... |
| Findings by severity       | +-------------------------------------------+
| Coverage: EC2 S3 IAM       | | Scan | scope | coverage | state | errors  |
| Expiring risk acceptances  | +-------------------------------------------+
+----------------------------+

FINDINGS LIST                  FINDING DETAIL
+ severity status rule acct -+ + EC2-001 | High | Open -------------------+
| Resource | title | age     | | Deterministic evidence + observed time   |
| [...]                      | | Resource / rule version / compliance     |
+----------------------------+ | Status history | advisory AI explanation |
                               | [Create Jira] [Request remediation]       |
                               +-------------------------------------------+
```

## Decision and reporting views

```text
REMEDIATION APPROVAL            JIRA TICKET CREATION
+ Target + current evidence --+ + Project [ ] Assignee [ ] ---------------+
| Playbook/version + changes  | | Title/body draft; allowlisted evidence   |
| Preconditions / rollback    | | AI-generated text clearly labeled/editable|
| Separation-of-duties status | | [Create ticket]                           |
| [Reject] [Approve + confirm] | +------------------------------------------+
+-----------------------------+

COMPLIANCE / REPORTS            AUDIT LOG
+ framework/version/coverage -+ + time actor action target outcome -------+
| Controls mapped/unmapped    | | filters | export (authorized) | details  |
| Not a certification        | +------------------------------------------+
+-----------------------------+
```

## Administration

```text
USERS & ROLES                   SETTINGS
+ member | role | status -----+ + Organization | sessions | retention ----+
| [Invite] [Change role]      | | AWS connections | Jira | email/Teams    |
| permission impact shown    | | AI provider policy/status | notifications|
+-----------------------------+ +------------------------------------------+
```

All views require empty, loading/skeleton, partial, permission-denied, and error states; keyboard order and screen-reader structure are part of acceptance. Content and responsive behavior require user testing.
