# Notification providers

Provider selection is server-only configuration. Secrets are redacting settings
injected by infrastructure and never stored in notification rows or queue
payloads.

| Provider | V1 status | Configuration | Retry behavior |
|---|---|---|---|
| Mock | Local/test only | none | deterministic faults |
| SMTP | Implemented | host, port, TLS mode, user, secret password | SMTP 4xx/transport retry; 5xx terminal |
| Slack webhook | Implemented contract | secret HTTPS URL on `hooks.slack.com` | 429/5xx retry |
| Teams workflow webhook | Verified contract | secret HTTPS URL on approved Microsoft hosts | 429/5xx retry |
| SES | Deferred | workload identity | adapter not implemented |

Production SMTP requires STARTTLS or implicit TLS with system certificate
validation. Headers and recipients reject CR/LF, messages are size bounded,
timeouts are bounded, and response bodies are discarded. Slack uses an incoming
webhook for V1. Teams uses an incoming Power Automate/workflow webhook; Microsoft
Graph is deferred due to consent and token lifecycle complexity.

The webhook adapters validate scheme, credentials, fragments and host suffix
before I/O. Tests inject a synthetic transport and never contact a provider.
Deployments must configure egress allowlists and retrieve endpoint secrets from
the managed secret source.
