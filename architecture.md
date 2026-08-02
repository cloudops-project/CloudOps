# CloudOps architecture

The canonical architecture set is maintained under `docs/architecture/`:

- [System architecture](docs/architecture/system-architecture.md)
- [Data flow](docs/architecture/data-flow.md)
- [Trust boundaries](docs/architecture/trust-boundaries.md)
- [AWS role architecture](docs/architecture/aws-role-architecture.md)
- [Database design](docs/architecture/database-design.md)
- [Deployment topology](docs/architecture/deployment-topology.md)
- [Architecture decisions](docs/architecture/decisions/README.md)

CloudOps uses React/Vite, FastAPI, PostgreSQL-backed durable jobs, workload identity, deterministic
rules/risk, advisory AI, approval-gated providers, and governed allowlisted remediation. It does not
use Celery/Redis, store AWS credentials, let AI make authoritative decisions, or support arbitrary
AWS mutations.

The repository map in [system architecture](docs/architecture/system-architecture.md) explains how
the code is organized; [memory.md](memory.md) explains where work stopped. Deployment diagrams are
designs unless [current status](docs/product/current-status.md) records operational evidence.
