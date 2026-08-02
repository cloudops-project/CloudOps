# Demonstration checklist

## Before the guide arrives

- [ ] Use synthetic organizations, users, accounts, assets, and recipients only.
- [ ] Verify migration head `0019_live_remediation_data_model`.
- [ ] Verify API, web, PostgreSQL, scheduler, and job-worker health.
- [ ] Seed the approved deterministic demo dataset.
- [ ] Confirm AI and delivery providers are mock/local unless live use is separately authorized.
- [ ] Confirm remediation execution/live flags are false and emergency stop true.
- [ ] Prepare separate owner and analyst sessions; verify tenant and role isolation.
- [ ] Capture CI, architecture, finding, risk, compliance, AI, remediation, and audit screens.
- [ ] Remove tokens, External IDs, cookies, addresses, and connection strings from evidence.

## Evidence to show

- [ ] Deterministic finding key/evidence and unchanged rule result.
- [ ] Risk component breakdown and policy version.
- [ ] Compliance control mapping with no certification claim.
- [ ] AI request source, minimized context/hash, validated response, and advisory warning.
- [ ] Remediation preview, approval separation, allowlisted action, and dry-run result.
- [ ] Owner-only trust/sandbox status without External ID disclosure.
- [ ] Durable job state/heartbeat and audit correlation.
- [ ] Current status matrix with AWS deployment/live tests marked pending.

## Never demonstrate without separate authorization

Real customer data or account, real recipient, AWS/Cloudflare credentials, Terraform apply, live
provider call, live remediation, automatic rollback, production deployment, or direct database
approval edits.
