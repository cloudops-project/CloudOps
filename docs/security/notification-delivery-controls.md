# Notification delivery controls

Delivery requires the established approval capability before enqueue and an
`APPROVED` state plus unchanged approval fingerprint in the worker. Revocation
before execution blocks I/O. Approval and enqueue actors are separately audited;
provider evidence stores masked destination count, template version, content
hash, provider message identifier, classification, timestamps and sanitized
errors.

No credential, webhook URL, recipient address, notification body, raw headers or
provider response is stored in a queue payload or delivery-attempt record.
Webhook URLs and SMTP passwords use `SecretStr`; effective settings are never
logged. SSRF controls require HTTPS and an approved provider hostname. SMTP
rejects header injection. All APIs and parent relationships include organization
scope.

Residual risks:

- SMTP has no universal provider idempotency primitive. A process crash after
  remote acceptance but before the database commit can duplicate delivery.
- Teams is a verified workflow-webhook contract, not a live Microsoft
  certification.
- HTML/template customization is intentionally deferred.
- Production egress controls, managed secrets, dashboards, and autoscaling are
  deployment prerequisites and are not deployed by this change.

Incident response: pause workers, revoke the endpoint or SMTP credential,
rotate through the managed secret store, review sanitized attempts and audit
events, test with a synthetic destination, then selectively requeue. Never place
secret URLs or provider responses in logs or incident tickets.
