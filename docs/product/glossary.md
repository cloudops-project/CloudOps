# CloudOps Glossary

## Purpose and audience

All contributors use these definitions to keep product, UI, API, and audit terminology consistent.

- **Asset:** normalized configuration metadata for a supported EC2, S3, or IAM resource; not customer application data.
- **Finding:** tenant-owned record that deterministic rule evidence matched a rule version.
- **Evidence:** minimal, structured facts used to reproduce an evaluation; secrets are excluded/redacted.
- **Rule / rule version:** stable check identity and immutable revision of deterministic detection logic and metadata.
- **Scan job / scan run:** requested unit of work and one execution attempt, respectively.
- **Risk acceptance:** time-bound, justified decision by an authorized risk owner; it does not erase a finding.
- **Remediation request / execution:** proposed and approved change, and an individual attempt through a manual or scoped automated path.
- **Verification scan:** post-change deterministic re-evaluation; only this can support verified closure.
- **Organization / tenant:** primary CloudOps customer isolation boundary.
- **AWS account connection:** role ARN, external ID reference/secure value, validation state, and metadata used to obtain temporary credentials.
- **Compliance mapping:** reviewed relationship between a rule and a control; it is not certification.
- **AI interaction:** optional advisory request/response metadata with redaction and validation status.
- **Audit event:** append-oriented record of a security-relevant action and outcome.
- **Approved playbook:** versioned, reviewed, narrowly scoped remediation procedure requiring explicit authorization.

## Usage notes

Do not call policy deviations universal “vulnerabilities” without context. Do not call a finding “resolved” until verification criteria are met.
