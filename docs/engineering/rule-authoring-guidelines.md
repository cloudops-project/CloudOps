# Deterministic Rule Authoring and Initial Catalogue

## Purpose and audience

AWS/security engineers, analysts, and QA use this specification to evolve the implemented Stage
4 typed rule pack. The executable source of truth is `apps/api/app/security_rules/`; the catalog
below includes historical planning entries and must not be mistaken for implemented scope.

## Rule contract

Every immutable version defines ID, title, AWS service/resource type, description, deterministic detection logic, minimal evidence fields, default severity, security impact, reviewed compliance mappings, false-positive/context considerations, manual guidance, automation eligibility, verification procedure, and version. Tests require positive, negative, missing-data, boundary, and permission-denied fixtures. Collectors normalize data; rules do not call AWS. Findings cite rule version and scan run.

Implemented rules use stable globally unique keys, positive integer versions, and a typed
`evaluate(asset, context)` contract. Evidence is bounded and secret-bearing keys are removed.
Missing evidence returns `ERROR` or `NOT_APPLICABLE`, never a misleading pass. Rules cannot use
boto3, network/filesystem access, `eval`, or untrusted dynamic imports.

Severities below are proposals. “Conditional” means organization policy must enable the check or supply context; absence is not automatically a universal vulnerability. Compliance references are **candidate mapping families** (CIS AWS Foundations, NIST CSF/800-53) requiring licensed-source and control-level reviewer validation; CloudOps does not certify compliance.

## Amazon EC2 catalogue

| ID / v1 | Title; resource | Detection and evidence | Severity / impact | Context and manual remediation | Automation / verification / candidate mapping |
|---|---|---|---|---|---|
| EC2-001 | SSH open to world; security-group rule | Ingress permits TCP/22 from `0.0.0.0/0` or `::/0`; SG/rule ID, protocol, ports, CIDR, attachments | High; remote attack surface | Approved bastion/VPN may alter policy; restrict source/remove rule | Conditional approved SG-rule playbook; rescan rule; CIS/NIST access control |
| EC2-002 | RDP open to world; security-group rule | TCP/3389 from world; same network evidence plus account/region | High; credential attack/exposure | Approved managed access exception; restrict source/use managed access | Conditional; rescan; CIS/NIST access control |
| EC2-003 | Sensitive ports publicly exposed; SG rule | Policy-configured sensitive port/range reachable from world; rule and policy baseline | High default; service exposure | Port criticality and load balancer path matter; remove/narrow ingress | Conditional; rescan; NIST boundary protection |
| EC2-004 | EBS volume unencrypted; volume | `Encrypted=false`; volume ID/type, attachment, snapshot origin | High; data-at-rest exposure | Legacy/ephemeral exceptions require owner; snapshot/copy/migrate safely | No generic auto MVP; verify replacement encrypted; CIS/NIST data protection |
| EC2-005 | IMDSv1 allowed; instance | Metadata options tokens not `required`; instance ID/state, HttpTokens, endpoint | High; credential theft via SSRF | Compatibility testing required; require IMDSv2 | Candidate with precheck/rollback; describe instances; CIS/NIST credential protection |
| EC2-006 | Unexpected public IP; instance/ENI | Public IPv4/EIP exists and policy says private-only; IDs, subnet, public DNS/IP class | Medium; internet exposure | Internet-facing approved workloads; remove/rearchitect after reachability review | No generic auto; verify address absent; NIST boundary protection |
| EC2-007 | Overly permissive ingress; security group | Policy threshold for wide CIDR/protocol/all ports exceeded; full normalized rule evidence | High; broad attack surface | Business ports and layered controls matter; narrow source/ports | Conditional per-rule removal; rescan; CIS/NIST network controls |
| EC2-008 | Unused security group; security group | Not default and unattached across complete scoped inventory for policy age; SG, attachments, last-observed | Low; clutter/misconfiguration risk | Cross-service references and recent creation can mislead; validate then delete | Not initially; verify absent; hygiene mapping only if approved |
| EC2-009 | Required tags missing; instance/volume/SG | Policy-required keys absent/invalid; resource ID, observed tags (redacted), baseline version | Low; ownership/governance gap | Organization-specific; add approved tags without sensitive values | Candidate tag playbook; rescan; governance mappings |
| EC2-010 | Backup policy missing; EBS/instance | Applicable resource lacks approved AWS Backup plan/tag assignment; backup relationship evidence | Medium; recovery risk | Applicability/RPO policy required; enroll in reviewed plan | No generic auto; verify plan coverage; NIST contingency planning |
| EC2-011 | Detailed monitoring required but disabled; instance | Policy applicability true and monitoring state not enabled; instance/state/baseline | Low; reduced operational visibility | Cost/workload policy matters; enable detailed monitoring | Candidate with approval; describe monitoring; NIST monitoring |
| EC2-012 | Excessive instance-profile permissions; profile/role | Attached role violates approved IAM analyzer patterns (wildcards/admin/escalation); instance/profile/role/policy hashes and matched clauses | High; workload credential blast radius | Permission context is complex; least-privilege policy review | Never generic auto; reevaluate policy and attachment; CIS/NIST least privilege |

## Amazon S3 catalogue

| ID / v1 | Title; resource | Detection and evidence | Severity / impact | Context and manual remediation | Automation / verification / candidate mapping |
|---|---|---|---|---|---|
| S3-001 | Public access allowed; bucket/access surface | Effective reviewed public-access signals true; bucket, BPA, ACL/policy/access-point summary | Critical; data exposure | Static public sites require explicit exception and architecture review; remove public paths | No generic auto; recompute effective access; CIS/NIST access control |
| S3-002 | Block Public Access disabled; bucket/account | Any required BPA flag false under baseline; bucket/account flags | High; weakened preventive guardrail | Approved public design exception; enable all required flags | Candidate scoped configuration; get BPA; CIS/NIST access control |
| S3-003 | Public ACL present; bucket/object ACL scope | AllUsers/AuthenticatedUsers grant; bucket, grantee URI, permission (no object content) | Critical; public access | Ownership-controls context matters; remove grants/enable owner enforcement | Conditional; reread ACL; CIS/NIST access control |
| S3-004 | Unsafe wildcard principal; bucket policy | `Principal:"*"` Allow lacks approved restrictive conditions; bucket, statement SID/hash, actions/resources/condition summary | Critical; unintended access | Public service policies need semantic review; constrain principal/conditions | No generic auto; reparse policy; CIS/NIST least privilege |
| S3-005 | Default encryption disabled; bucket | Encryption configuration absent or violates approved key policy; bucket, algorithm/key-reference class | High; unencrypted new objects | AWS default behavior versus explicit governance baseline; configure SSE-S3/KMS | Candidate after key-impact review; get encryption; CIS/NIST data protection |
| S3-006 | Versioning disabled; bucket | Baseline requires enabled and status absent/suspended; bucket/status | Medium; weak recovery | Cost/data lifecycle context; enable and pair lifecycle | Candidate; get versioning; NIST contingency/integrity |
| S3-007 | Access logging required but disabled; bucket | Policy-applicable bucket lacks approved server-access/audit destination; bucket and destination metadata | Medium; weak investigation | CloudTrail/other logging and log-bucket recursion matter; configure approved destination | Conditional; reread logging; CIS/NIST audit |
| S3-008 | Excessive cross-account access; bucket policy | Allowed external account/principal not in organization allowlist or action scope too broad; statement hash and principal/action/resource summary | High; third-party exposure | Legitimate partner access requires owner/expiry; narrow/remove statement | No generic auto; policy reevaluation; NIST access control |
| S3-009 | Lifecycle policy required but absent; bucket | Policy applicability true and no compliant lifecycle configuration; bucket/classification/baseline | Low; excess retention/cost | Retention/legal hold context required; add reviewed lifecycle | Conditional; get lifecycle; governance/privacy mapping |
| S3-010 | Object Lock required but missing; bucket | Immutability policy applies and Object Lock not enabled/configured; bucket, status, retention mode | Medium; deletion/tampering risk | Cannot be retrofitted casually; legal/operational review and migration may be needed | No auto; verify target design/config; NIST integrity |
| S3-011 | Required tags missing; bucket | Required keys absent/invalid; bucket, redacted tag keys, baseline | Low; ownership gap | Organization-specific; add non-sensitive tags | Candidate; reread tags; governance mappings |
| S3-012 | Insecure transport allowed; bucket policy | No effective explicit Deny for `aws:SecureTransport=false` under approved semantic check | High; plaintext transport possible | Policy composition requires care; add reviewed deny statement | Candidate policy patch only after semantic review; reparse/simulate; CIS/NIST transmission protection |
| S3-013 | CloudTrail data events required but absent; bucket | Policy-applicable bucket not covered by enabled trail/event selector; bucket, trail/selector coverage | Medium; object-access visibility gap | High volume/cost and alternate telemetry matter; enable scoped data events | No bucket auto; reevaluate CloudTrail coverage; CIS/NIST audit |

## AWS IAM catalogue

| ID / v1 | Title; resource | Detection and evidence | Severity / impact | Context and manual remediation | Automation / verification / candidate mapping |
|---|---|---|---|---|---|
| IAM-001 | Root MFA not enabled; account summary | `AccountMFAEnabled != 1`; account ID and summary flag | Critical; root takeover | No routine exception; enable hardware/passkey-capable MFA and secure recovery | No CloudOps auto; reread summary; CIS/NIST authentication |
| IAM-002 | User MFA missing where required; IAM user | Console-enabled/in-scope user lacks MFA device; user, login-profile state, MFA count, baseline | High; account takeover | Service-only users should migrate from users/keys; enable MFA | No auto; list devices/profile; CIS/NIST authentication |
| IAM-003 | Active unused access key; IAM key | Active key last-used older than configured threshold or never used beyond grace; user, key ID suffix/hash, create/last-use/service/region | High; latent credential risk | Automation ownership and delayed telemetry matter; rotate then disable/delete | Only staged disable playbook considered; verify status; CIS/NIST credential management |
| IAM-004 | Old access key; IAM key | Age exceeds policy threshold; user, key ID suffix, create time, baseline | High; long exposure window | Rotation capability required; rotate consumers, disable old key | Staged only; list keys; CIS/NIST credential management |
| IAM-005 | Multiple active keys unjustified; IAM user | More active keys than baseline and no approved rotation grace; user, key suffixes/create times | Medium; credential sprawl | Two keys may be temporary rotation; complete rotation/remove old | Staged disable only; count active; governance mapping |
| IAM-006 | Wildcard actions; policy statement | Allow action contains `*` or policy-prohibited wildcard pattern; policy/version/statement hash, action/resource/conditions summary | High; excessive privilege | Some AWS-managed/service roles need context; replace with used actions | No generic auto; parse/simulate reviewed policy; CIS/NIST least privilege |
| IAM-007 | Wildcard resources; policy statement | Allow uses `Resource:"*"` for actions supporting resource scoping without compensating approved conditions | High; broad resource access | Some APIs require wildcard; constrain resources/conditions | No auto; reevaluate policy; CIS/NIST least privilege |
| IAM-008 | Unnecessary administrator access; principal/attachment | Administrator-equivalent policy attached and principal not approved; principal, attachment path, policy hash, allowlist | Critical; total account compromise | Break-glass/admin roles require governance; remove and replace least privilege | No auto; simulate/list attachments; CIS/NIST least privilege |
| IAM-009 | Excessive trust relationships; role trust policy | External/wildcard principal or weak conditions violate trust baseline; role, statement hash, principals/actions/condition summary | High; unauthorized assumption | Federated/service principals require context; narrow principal and conditions | No auto; reparse trust policy; CIS/NIST access control |
| IAM-010 | Unused user; IAM user | No console/key/service use beyond policy threshold with complete credential report; user, create/last-use/key/MFA summary | Medium; dormant identity | Emergency/service identities require owner; disable then remove after review | Staged deactivation only; regenerate report; CIS/NIST account management |
| IAM-011 | Unused role; IAM role | Last-used absent/older than threshold and role beyond grace, excluding approved service-linked roles; role/path/last-used/trust class | Low; dormant trust surface | AWS last-used limits and infrequent jobs matter; detach/delete after dependency search | No generic auto; get/list role; governance/least privilege |
| IAM-012 | Privilege-escalation policy path; policy/principal | Reviewed pattern set detects dangerous action combinations/resources/conditions; principal, policy/version, matched pattern IDs, statement hashes | Critical; escalation to broader control | Context and permissions boundaries/SCPs matter; expert review and restrict combination | Never generic auto; rerun analyzer/simulation; CIS/NIST least privilege |
| IAM-013 | Long-lived credentials; IAM user/key/certificate | Human/service user retains persistent key beyond approved model/threshold; type, age, last use, owner context | High; theft persistence | Migrate workloads to roles/federation; rotate/revoke key | Staged disable only; credential report; CIS/NIST credential management |
| IAM-014 | Password policy below baseline; account | Account password-policy fields fail configured baseline; min length, reuse, expiry, complexity flags | Medium; weak passwords | Federation may reduce usage but root/local recovery remains; update reviewed policy | Candidate account-level playbook with approval; get policy; CIS/NIST authentication |

## Lifecycle, review, and open questions

Rule changes create new versions; activation is explicit and historical findings keep their original version. A two-person security review validates detection, permissions, evidence minimization, severity, context, remediation, and candidate control mapping. Deprecation never reuses IDs. Automated remediation defaults to unsupported; “candidate” means a later threat-modeled playbook could be approved, never that it is safe universally.

Approve configurable policy baselines, exact sensitive-port list, unused/old thresholds, effective S3 public-access algorithm, IAM escalation pattern source, compliance content/licensing, initial enabled subset, and rule acceptance fixtures before Stage 5.

## Stage 5 mapping policy

Stage 5 stores official framework identifiers, versions, and reference URLs alongside short
original CloudOps summaries. It does not reproduce restricted framework prose and does not claim
certification. Mappings identify an inclusive rule-version range and a CloudOps rationale.
Overlapping ranges for the same rule/control use deterministic union semantics; matching more
than one range cannot improve a result. Catalog mappings are implementation candidates that
require human compliance review before external assurance use. Draft or uncertain mappings must
not be described as independently validated.
