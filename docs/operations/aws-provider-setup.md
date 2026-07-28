# Amazon Bedrock and SES setup

## Status

The Bedrock Converse and SES v2 adapters are implemented and verified with Botocore Stubber only. No live model invocation or email delivery has been performed.

## Bedrock

1. Approve one model and region through the cloud-security process.
2. Add only that model ARN to the API task role.
3. Set non-secret configuration:
   - `AI_PROVIDER=bedrock`
   - `AWS_BEDROCK_ENABLED=true`
   - `AWS_BEDROCK_REGION=<REGION>`
   - `AWS_BEDROCK_MODEL_ID=<APPROVED_MODEL_ID>`
4. Keep timeouts, retry attempts, and request/response byte limits bounded.
5. Run the opt-in sandbox test with synthetic evidence. Confirm logs and database rows contain no prompt secrets.

The adapter treats evidence as untrusted, uses the default credential chain, requires JSON matching the advisory schema, and cannot authorize remediation. Deterministic findings/compliance/risk remain authoritative.

## SES

1. Verify an SES domain identity and configure DKIM, SPF, and DMARC.
2. Move out of the SES sandbox only after abuse/bounce review.
3. Scope the worker task role to that identity.
4. Set:
   - `NOTIFICATION_PROVIDER=ses`
   - `AWS_SES_ENABLED=true`
   - `AWS_SES_REGION=<REGION>`
   - `AWS_SES_FROM_EMAIL=<VERIFIED_SENDER>`
   - optional from-name, reply-to, and configuration-set values.
5. Configure configuration-set event destinations for delivery, bounce, complaint, reject, and delay monitoring.
6. Send only a synthetic approved notification in staging.

The adapter rejects invalid/header-injected addresses, bounds recipients/body size, sanitizes provider errors, and stores only the provider message identifier as delivery evidence.

## Failure and rollback

Provider startup validation fails closed in production. To contain an incident, change the provider to `mock` or disable its feature flag, redeploy the same application digest with updated non-secret configuration, revoke task-role permission if compromised, rotate affected provider material, and preserve CloudTrail/log evidence.
