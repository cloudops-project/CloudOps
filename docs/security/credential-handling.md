# Credential handling

CloudOps uses workload identity and temporary credentials. Production and AWS sandbox hosts must not
contain `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, session-token files, or credentials in `.env`.

## AWS identities

1. The host receives a platform identity (ECS task role or EC2 instance profile).
2. The platform identity assumes the tenant discovery or remediation role with its distinct
   External ID.
3. STS returns temporary credentials, held only in process memory and isolated in the credential
   cache by tenant/account/role context.
4. `GetCallerIdentity` confirms the expected account before governed work.

Discovery External IDs and remediation External IDs are separate protected values. Neither is an
AWS access key. Broad account APIs expose only configuration status, never either full value.

## Other secrets

Database credentials, JWT signing material, provider tokens, webhook URLs, SMTP credentials, Jira
credentials, and Cloudflare tokens belong in approved managed-secret or ignored local-file paths.
They must not appear in source, frontend variables, logs, audit data, job payloads, test fixtures,
Terraform plans committed to Git, or documentation.

Use documentation-safe placeholders such as account `111122223333`, host
`cloudops.example.com`, and administrator CIDR `203.0.113.10/32`.
