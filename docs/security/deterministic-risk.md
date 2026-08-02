# Deterministic risk scoring

The authoritative policy is `CLOUDOPS_RISK_V1`, version 1. It is CVSS-inspired, but it is **not a
CVSS score**. Identical normalized inputs produce the same 0-100 result; AI does not participate.

## Finding components

| Component | Maximum points | Unknown points |
|---|---:|---:|
| Severity | 30 | Derived from deterministic finding severity |
| Exposure | 15 | 7 |
| Exploitability | 10 | 5 |
| Privilege | 10 | 5 |
| Asset criticality | 10 | 5 |
| Environment | 5 | 2 |
| Business impact | 10 | 5 |
| Data sensitivity | 5 | 2 |
| Age | 5 | Based on finding age |

Unknown context is deliberately nonzero. Age points are: under 7 days `0`; 7-29 `1`; 30-89 `3`;
90-179 `4`; 180 or more `5`. Compensating-control adjustment is bounded from `-15` to `0`; each
stored control contributes a bounded negative value from `-15` to `-1`. Final scores are clamped
to 0-100 and rounded half up.

Priority bands are Low `0-29`, Medium `30-59`, High `60-79`, and Critical `80-100`.

## Aggregation

- Account score = `50% highest finding + 30% top-ten finding mean + 20% all-finding mean`.
- Organization score = `60% highest account + 40% all-account mean`.

## Worked example

A deterministic **High** finding, 31 days old, with all contextual inputs unknown and no
compensating control scores `24 + 7 + 5 + 5 + 5 + 2 + 5 + 2 + 3 = 58`, which is **Medium**.
The example demonstrates that missing context does not automatically become zero risk.

## Auditability

Policies are versioned and used policy versions are immutable. Finding, account, and organization
risk snapshots preserve component breakdowns, source versions/cutoffs, and timestamps. PostgreSQL
triggers protect snapshot immutability, supporting later reproduction and audit.
