# Test and evidence index

## Retained repository/CI evidence

| Evidence | Source | Commit | Result | Limit |
|---|---|---|---|---|
| PR #30 review and documentation audit | [PR #30](https://github.com/cloudops-project/CloudOps/pull/30) | `c2abb3efbd4657b8f750dac46702d390e710e71c` | Merged | Documentation-only |
| Main CI after PR #30 | [run 30769052611](https://github.com/cloudops-project/CloudOps/actions/runs/30769052611) | `7926ab0f81daeca4234a13b5d92218b67f09defa` | Seven jobs passed | CI, not operational deployment |
| Backend | CI job in run 30769052611 | same | Ruff, Mypy, dependency checks, tests, PostgreSQL migration gates passed | No live provider/AWS claim |
| Frontend | CI job in run 30769052611 | same | install, lint, typecheck, tests, build, audit passed | No browser UAT claim |
| Containers | CI jobs in run 30769052611 | same | images, Compose, self-host migration/health passed | No clean-host or production claim |
| Secret scan | CI job in run 30769052611 | same | Gitleaks passed | Does not replace external secret-store review |
| Terraform and IaC security | CI job in run 30769052611 | same | format, validation, sandbox tests, Checkov passed | No plan/apply or live account claim |

## External evidence registry

External evidence belongs under `D:\CloudOps-Secure\evidence\<timestamp>\`. Repository entries
contain only a sanitized description and SHA-256.

| Evidence ID | Environment | Action | External SHA-256 | Status | Risks |
|---|---|---|---|---|---|
| `PQ-P1-BASELINE` | repository/CI | Phase 1 baseline audit; external record `D:\CloudOps-Secure\evidence\20260803-034204\phase1-baseline-summary.md` | `56A8EF4E539B5B1BDEBF15FC024E905C47CDB4F6004B77EEFB9EA6964BF94A95` | Generated; PR review pending | Operational evidence remains absent |

## Evidence still required

Identity, saved plans, apply, resource inventory, deployment, live discovery/providers/remediation,
restore, rollback, load/resilience, dashboards, alert delivery, UAT, staging, production canary and
post-deployment evidence have not been generated.
