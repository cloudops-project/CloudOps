# Security Policy

## Scope

This policy covers the CloudFix repository and its CloudOps runtime components. Implemented code is locally verified, but no supported production release or live AWS deployment is proven.

## Reporting

Do not open a public issue for a suspected vulnerability. Use the private security contact configured by the project owner. Include the affected area, reproduction conditions, impact, and minimized safe evidence. Never include credentials, tokens, customer data, or other secret material. Do not test accounts, systems, or data without written authorization.

## Response

No public response-time SLA is asserted. The security lead triages severity, coordinates containment and safe evidence preservation, and records corrective action under the [incident response plan](docs/operations/incident-response.md). Security fixes require independent review and proportionate verification.

## Supported versions and disclosure

The integration branch is an unreleased V1 candidate, not a supported production version. A supported-version table, security contact, coordinated-disclosure process, and response targets must be approved before release. Secrets are rotated through approved stores and never committed.
