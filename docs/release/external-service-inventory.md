# External-service inventory

| Service | Data sent | Credential model | Production scope | Live status |
|---|---|---|---|---|
| AWS STS/customer APIs | Account/resource metadata required for supported discovery | Platform workload identity assumes tenant role with External ID; temporary credentials in memory | Required | Not yet verified |
| Amazon Bedrock | One bounded, sanitized persisted finding/risk/compliance source | Workload identity and approved model | Advertised optional provider | Not yet verified |
| Amazon SES | Approved recipients and sanitized notification content | Workload identity and approved identity | Advertised optional provider | Not yet verified |
| Jira Cloud | Approved issue fields and tenant connection | Encrypted integration token | Advertised optional provider | Not yet verified |
| SMTP/Mailpit | Local/demo notification content | Local synthetic configuration | Local/demo only | Locally tested, not production provider |
| Slack/Teams webhooks | Approved bounded notification payload | Protected webhook URL | Optional adapter | Not live verified |
| GitHub | Source, CI metadata, build/release artifacts | User auth for development; OIDC for AWS publishing/deploy | Required delivery platform | CI verified; AWS release path unverified |
| Container/package registries | Package/image metadata and artifacts | Short-lived workflow/user authentication | Required build dependency | CI access verified |
| Cloudflare | Web tunnel traffic and tunnel credential | Protected named-tunnel token | Optional self-host ingress | Not authorized for AWS phase |
| DNS/ACM | Hostname and certificate metadata | AWS/provider workload/deployment identity | Required for managed HTTPS | Not configured/verified |

No provider may receive AWS credentials, External IDs, authorization headers, full customer
inventory, raw provider errors, or unapproved customer data. Removing an unqualified provider from
production scope is acceptable; advertising it without live evidence earns zero provider points.
