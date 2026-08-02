# AI privacy, minimization, and safety

AI is advisory. It never detects a finding, sets severity or compliance status, calculates the
authoritative risk score, determines eligibility, grants approval, chooses an AWS operation, or
executes remediation.

## Supported sources and tasks

Exactly one persisted source is required. Compatibility is enforced:

- **Finding:** finding explanation, business impact, remediation wording, Jira draft, email summary.
- **Risk assessment:** executive summary or email summary.
- **Compliance assessment:** executive summary or email summary.

## Input controls

- Unicode NFKC normalization and unsafe-control removal.
- Redaction of secret-shaped values including access keys, bearer/password/token forms, private
  keys, JWTs, database URIs, API keys, and signed URLs.
- Prompt-injection phrases are neutralized before provider submission.
- Maximum string length 1,000 characters, collection size 50, dictionary keys 100, and nesting depth
  five; over-limit content is truncated deterministically.
- Canonical sorted compact JSON produces a SHA-256 context hash.
- A request fingerprint binds tenant, task, source version/hash, options, template, and schema for
  idempotency conflict detection.

CloudOps does **not** send the full AWS environment to AI. It sends the bounded compatible persisted
source context. As a further security improvement, rule-specific allowlisted evidence payloads are
preferred over generic sanitized evidence objects; this recommendation is not yet implemented for
every rule.

## Provider and output controls

- Organization rate limit: 100 requests per hour.
- Service provider attempts: at most two; provider timeout: 10 seconds.
- The Bedrock client additionally uses bounded connect/read timeouts and retry configuration,
  request/response byte limits, maximum 1,200 output tokens, and temperature `0.1`.
- Provider output must satisfy the task schema, is sanitized again, canonicalized, and hashed.
- Stored source version/hash supports `current`, `stale`, or `missing` status.
- Requests, responses, usage, correlation, and sanitized outcomes are audited.

Bedrock automated tests use synthetic clients or Botocore Stubber. Live Bedrock invocation is
**Not yet verified**.
