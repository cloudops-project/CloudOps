# Notification providers

Provider selection is server-only. Secrets use redacting settings injected by infrastructure and
are never stored in notification rows or job payloads.

| Provider | Status | Identity/secret | Validation state |
|---|---|---|---|
| Mock | Implemented; local/test default | None | Locally verified |
| SMTP | Implemented; local demo only in production policy | Password when configured | Synthetic transport/local Mailpit |
| SES v2 | Implemented adapter | AWS workload identity | Stubber verified; live delivery pending |
| Slack webhook | Implemented | Managed webhook secret | Synthetic transport; live pending |
| Teams workflow webhook | Implemented | Managed webhook secret | Synthetic transport; live pending |

Production settings reject SMTP. SES is the intended AWS email path. Every delivery reloads the
tenant event and approval, validates recipients/headers/size, bounds timeouts/retries, sanitizes
errors, and stores limited provider evidence. Webhook adapters restrict scheme and host before I/O.
No live provider validation is claimed. See
[provider setup](../operations/aws-provider-setup.md) and
[notification controls](../security/notification-delivery-controls.md).
