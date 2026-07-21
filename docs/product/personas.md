# Personas and Access Needs

## Purpose and audience

Product, design, security, and authorization implementers use these personas to design workflows without treating UI visibility as access control.

| Persona | Responsibilities and goals | Required permissions | Typical workflow | Security concerns |
|---|---|---|---|---|
| Organization Administrator | Manage tenant, members, roles, integrations, and AWS accounts | Organization administration; no implicit platform-wide access | Invite member, connect account, review approvals | Account takeover, privilege escalation, destructive configuration |
| Security Analyst | Triage findings, map risk, request action, review exceptions | Read assets; manage findings, recommendations, and bounded risk decisions | Filter findings, inspect evidence, draft Jira/remediation request | Evidence integrity, alert fatigue, unsafe AI advice |
| Cloud Engineer | Diagnose AWS configuration and perform remediation | Read assigned evidence; update assigned work; request/execute only approved playbooks | Validate context, remediate manually, trigger verification | Excess privilege, stale evidence, production impact |
| DevOps Engineer | Operate delivery and supported automation | Environment operations plus explicitly approved remediation execution | Deploy, monitor queue, handle a failed playbook | CI secrets, cross-tenant jobs, replay/duplicate execution |
| Auditor | Assess controls and trace decisions | Read reports, mappings, evidence, and audit history; export if approved | Sample finding lifecycle and exceptions | Audit tampering, incomplete provenance, oversharing |
| Read-only Stakeholder | Understand posture and business risk | Read curated dashboards/reports only | Review trend and executive summary | Misleading aggregation, exposure of technical details |

## Authorization notes

Roles are configurable permission bundles, scoped to one organization membership. Separation of duties should prevent a requester from being the sole approver of high-risk remediation. A platform administrator is an operational role, not a tenant persona, and access must be exceptional, logged, time-bound, and support-approved.

## Assumptions and future work

OIDC group mapping, custom roles, cross-organization users, and approval quorum need product approval. Least privilege and deny-by-default remain confirmed security requirements.
