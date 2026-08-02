# Demonstration speaker script

## Opening

“CloudOps inventories supported AWS evidence through short-lived role assumption. Deterministic
rules produce findings and a versioned deterministic policy computes risk. The application does not
store AWS credentials, and AI is advisory rather than an authority.”

## Product walkthrough

1. **Identity:** The organization and capability determine every tenant-owned query.
2. **Onboarding:** Discovery role/External ID are separate from remediation trust.
3. **Discovery:** Collectors normalize bounded read-only responses; automated tests use fakes/Stubber.
4. **Findings:** Rule keys and severities are deterministic.
5. **Risk:** The score is `CLOUDOPS_RISK_V1`, not AI and not CVSS.
6. **Compliance:** Mappings provide evidence, not certification.
7. **AI:** One compatible persisted source is minimized and sanitized; output is a draft.
8. **Remediation:** Preview, approval, live preparation, execution, and rollback are separate.
9. **Administration:** Only an owner can configure same-account trust or sandbox approval; the
   External ID is one-time and never shown broadly.
10. **Audit:** Correlation and sanitized evidence connect the workflow.

## Accurate live-remediation answer

“The default-disabled executor supports only S3 Public Access Block and exact EC2 ingress-rule
revocation on approved, tagged sandbox resources. Automated tests pass, but no live AWS mutation or
rollback has been operationally performed in this documented workflow.”

## Likely questions

| Question | Accurate answer |
|---|---|
| Does AI find vulnerabilities or score risk? | No. Rules and the versioned local risk policy are authoritative. |
| Are AWS keys stored? | No. Workload identity and in-memory temporary STS credentials are used. |
| Can an analyst enable remediation? | No. Owner-only administration and separate human approval apply. |
| Can CloudOps call any AWS API? | No. Live dispatch is static and limited to two actions. |
| Is it deployed in AWS? | Not through the controlled sandbox workflow; identity, plan, apply, and deployment are pending. |
| Is rollback proven? | Exact rollback state is captured in tests; live restoration is not yet verified. |
