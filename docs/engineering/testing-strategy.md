# Testing Strategy

## Purpose and audience

Engineering, QA, security, and product use this staged strategy to verify behavior without claiming tests already exist or pass.

Unit tests cover state machines, redaction, normalization, deterministic rules, permission policy, fingerprinting, and retry decisions. Integration tests use PostgreSQL and provider adapters for repository tenancy, transactions, STS/Jira/notification contracts, queue leases, and audit outbox. Contract tests pin OpenAPI/provider assumptions. End-to-end tests cover onboarding, scan, finding, Jira/manual/approved sandbox remediation, verification, acceptance expiry, and audit.

Security testing includes cross-tenant negatives, IDOR/mass assignment, session/CSRF, injection/XSS/SSRF, rate/replay/idempotency, IAM policy review, prompt injection, secret/log leakage, webhook forgery, dependency/secret/static scans, dynamic tests, and authorized manual penetration testing in sandbox/UAT. Performance tests establish baselines for representative assets and queue load; no target is asserted before measurement.

Use deterministic fixtures with no customer data or credentials. Automated remediation is tested only in a dedicated sandbox with explicit approval and cleanup/rollback documentation. Restore drills verify backups. Accessibility includes automated, keyboard, and screen-reader checks.

Release gates, coverage thresholds, supported matrix, performance targets, and test-data lifecycle require team approval in later stages.
