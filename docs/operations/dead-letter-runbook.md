# Dead-letter runbook

Jobs exhaust bounded retry attempts into `dead_lettered`; permanent validation,
authorization, or ownership failures become `failed` immediately. Evidence is
limited to an error code and redacted 500-character summary.

1. Use tenant-scoped job APIs to filter `status=dead_lettered`.
2. Confirm job type, attempts, correlation chain, and sanitized audit evidence.
3. Resolve the dependency or configuration fault. Do not reveal queue payloads.
4. A user with `jobs:manage` may requeue; this clears stale lease/failure state,
   resets attempts, preserves tenant ownership, and writes an audit event.
5. Cancel permanently when replay is unsafe or the source resource is obsolete.
6. Verify one terminal result and no unexpected provider delivery.

Cross-tenant job IDs are non-disclosing. Database administrators must not
manually alter state except under an approved incident procedure.
