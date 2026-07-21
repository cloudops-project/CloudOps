# Error Handling

## Purpose and audience

Frontend, backend, worker, and integration developers use this standard to make failures safe, diagnosable, and recoverable.

Define typed domain/application errors and map them once at boundaries to stable codes and correct HTTP/job states. User messages explain a safe next step; internal details remain in redacted structured logs linked by correlation ID. Cross-tenant denial never confirms resource existence.

Classify validation, authentication, authorization, conflict, dependency unavailable, throttling, timeout, partial scan, and permanent provider failures. Retries apply only to known transient/idempotent operations with bounded exponential backoff and jitter. Remediation retries require the same idempotency key and verified action semantics.

Do not catch broad exceptions silently. A top-level boundary may catch `Exception` to record a redacted failure and translate/rethrow an application error; it must not convert partial work into success. Frontend states distinguish empty, loading, partial, permission denied, recoverable, and terminal errors.

Open questions: retry budgets, dead-letter policy, partial-result UX, error-code registry ownership, and incident escalation thresholds.
