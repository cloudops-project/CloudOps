# Logging Guidelines

## Purpose and audience

Developers and operators use these rules to produce useful operational telemetry without creating a sensitive-data leak.

Emit structured logs with UTC timestamp, level, service/component, environment, event name, correlation ID, organization pseudonymous identifier, job/run ID, safe target type, outcome, duration, and error class. Keep audit events separate from diagnostic logs, though they may share correlation IDs.

Never log passwords, access keys, STS tokens, authorization/cookie headers, external IDs, AI API keys, Jira/Teams secrets, database URLs, raw prompts/outputs, full IAM policies, customer application data, or unreviewed tags. Redaction occurs before serialization and is tested. Avoid free-form exception dumps in user-facing channels.

Define level semantics and sampling centrally; security denials and remediation outcomes are never sampled away. Access is least-privilege, encrypted, monitored, and retained per approved classes. Alerts use aggregates and safe identifiers.

Open questions: logging platform, pseudonymization method, retention, cross-region residency, trace standard, and security alert thresholds.
