# Security Testing

Security, QA, and feature owners use the [threat model](../../docs/architecture/threat-model.md) and automated tests to evaluate tenant isolation, authorization, data handling, and provider boundaries.

Automated security coverage is implemented primarily under [../../apps/api/app/tests](../../apps/api/app/tests), including tenant isolation, authorization, secret redaction, workload identity, durable-job safety, remediation governance, notification safety, and mocked provider behavior.

Repository evidence does not prove live penetration testing, live AWS validation, or backup restoration. Testing outside explicitly authorized environments is prohibited.
