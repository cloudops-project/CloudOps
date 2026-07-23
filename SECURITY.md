# Security Policy

## Purpose and audience

This policy tells researchers, contributors, and operators how to report suspected CloudOps vulnerabilities without exposing customers or credentials.

## Reporting

Do not open a public issue. Use the private security contact configured by the project owner (open Stage 0 action: designate an inbox and backup contact). Include affected area, reproduction conditions, impact, and safe evidence. Never include AWS credentials, session tokens, secrets, or customer data. Do not test against accounts or data without written authorization.

## Response targets

Acknowledgement and remediation timelines will be defined before UAT; no unsupported SLA is claimed in Stage 0. The security lead will triage severity, coordinate containment, preserve audit evidence, notify authorized stakeholders, and document corrective action under the [incident response plan](docs/operations/incident-response.md).

## Supported versions and disclosure

No software version exists yet. A supported-version table and coordinated-disclosure process are required before release. Security fixes require designated review and verification; secrets must be rotated through approved stores, never committed.
