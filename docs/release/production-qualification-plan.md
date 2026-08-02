# CloudOps production-qualification plan

This plan converts source/CI evidence into controlled operational evidence. Each phase updates the
[readiness ledger](production-readiness-ledger.md), stores raw evidence only under the restricted
external evidence directory, commits sanitized summaries on a feature branch, and stops at the next
approval boundary.

## Evidence rules

- Every record contains timestamp, environment, source commit, approved action, sanitized result,
  external evidence SHA-256, pass/fail, and unresolved risks.
- Terraform state/plans, backups, credentials, External IDs, tokens, private inventories, and raw
  logs never enter Git.
- Mocked tests prove implementation behavior, not operational compatibility.
- A failed or unavailable gate earns no point and is never relabelled as passed.

## Qualification sequence

| Phase | Outcome | Entry gate | Mandatory stop |
|---|---|---|---|
| 1 Baseline | Ledger, inventories, risks, acceptance checklist | Merged docs baseline and green main CI | Baseline PR review/merge authorization |
| 2 Software quality | Reproducible complete local/CI gate evidence | Baseline merged | Any unexplained failure/skip |
| 3 Security | Retained application/supply-chain report; tenant gates | Isolated test environment | Critical/High finding or tenant failure |
| 4 Identity | Verified SSO assumed role in dedicated non-production account | Exact account classifications | Any caller/account/region/static-key mismatch |
| 5 Sandbox plan | Reviewed external plan/hash/cost/security inventory | Identity verified | Exact apply authorization |
| 6-8 Sandbox deploy/core | Applied lab, EC2 deployment, workload identity, read-only discovery | Exact reviewed plan approval | Any exposure, identity, cost, or health mismatch |
| 9 Providers | Live Bedrock, SES, Jira evidence using test resources | Explicit provider authorization | Any leakage or unapproved destination |
| 10 Remediation | One separately approved S3 and EC2 action | All governance gates and per-action approvals | Verification mismatch; immediately disable flags |
| 11-13 Reliability/operations | Restore, rollback, failure, load, metrics, alerts | Stable isolated environment | Data risk, threshold failure, missing evidence |
| 14-15 Managed staging/UAT | Full staging qualification and persona sign-off | Separate staging plan/apply authorization | Any blocking defect or missing UAT approval |
| 16 Production plan | Reviewed plan/cost/security/canary/rollback | Staging passed | Exact production apply authorization |
| 17 Production | Canary, promotion, post-deploy health | Exact apply and promotion approvals | Threshold breach; rollback/forward recovery |
| 18 Final | Evidence-linked score and recommendation | Every prior gate | Release authorization only at 100/100 |

## Current stop boundary

Only Phase 1 repository documentation is authorized. No AWS call, Terraform operation, Cloudflare
operation, deployment, provider invocation, or remediation may occur. After the baseline PR is
green, stop before merge and request explicit authorization.
