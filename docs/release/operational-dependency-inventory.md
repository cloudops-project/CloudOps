# Operational dependency inventory

| Dependency | Purpose | Required evidence/owner | Current state | Failure effect |
|---|---|---|---|---|
| PostgreSQL | System of record and durable jobs | Backups, restore, health, capacity, migration owner | Implemented/CI verified; not deployed | API/jobs unavailable |
| Docker/container runtime | API, web, workers, migration, self-host services | Pinned images, non-root, health, restart/reboot evidence | CI verified | Service outage |
| Nginx/reverse proxy | Same-origin web/API ingress | TLS/headers/health/cache validation | Container tested; deployment pending | User/API ingress failure |
| GitHub Actions | CI and immutable release workflow | Protected environments, OIDC, artifact retention | CI operational; release deployment unverified | Build/deploy blocked |
| Terraform 1.10.5 | Reviewed infrastructure changes | Lockfile, plan hash, state security, approval | Static validation only | Infrastructure changes blocked |
| AWS IAM/STS | Workload and tenant role identity | Non-root SSO, instance profile, External IDs, caller verification | Implemented/tests; live proof pending | Discovery/remediation unavailable |
| AWS EC2/EBS/VPC | Controlled host/sandbox networking | Plan/apply, IMDSv2, encryption, SG and cost evidence | Not created through current workflow | Sandbox unavailable |
| AWS S3 | State, backups, and synthetic finding | Encryption/versioning/access/log/restore evidence | Terraform source only | State/backup/lab unavailable |
| Bedrock | Advisory AI | Model access, privacy, timeout/rate/cost evidence | Stubber only | AI degrades; core detection remains |
| SES | Approved email | Identity, test recipient, failure/bounce evidence | Stubber only | Email delivery unavailable |
| Jira Cloud | Approved issue workflow | Test project, protected authentication storage, idempotency, and failure-path evidence | Mocked only | Jira workflow unavailable |
| Cloudflare named tunnel | Optional self-host exposure | Separate authorization, token handling, DNS/TLS evidence | Not authorized for AWS phase | External self-host access unavailable |
| DNS/ACM | Managed HTTPS | Ownership, certificate, renewal/expiry alerts | External prerequisite | Secure public ingress blocked |
| Alert destination/on-call | Incident delivery | Controlled alert/acknowledgement and escalation | Not configured/verified | Failures may go unnoticed |

Optional providers must fail closed or degrade only their feature; deterministic finding/risk and
tenant authorization must not depend on them.
