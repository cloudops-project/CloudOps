"""Stage 11 scheduler worker foundation.

This is a deterministic, synchronous entry point only. It does not run a
message queue or background daemon framework: `apps/worker/README.md`
explicitly defers that infrastructure choice (Celery/Redis vs. SQS) as an
unapproved future decision. Running this module performs one "tick": it
finds schedules whose next_run_at has elapsed and runs each one through the
existing DiscoveryOrchestrator/EvaluationService pipeline via
SchedulerService.run_due_schedules(). For a local demo, invoke it
repeatedly (e.g. cron, a simple loop, or a container command) rather than
treating it as a long-running process.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.scheduler import SchedulerService

logger = logging.getLogger("cloudops.scheduler")


def tick() -> int:
    """Run one scheduler tick against the configured database. Returns the
    number of scan runs started (including ones that failed deterministically
    inside the pipeline; a run only fails to start at all if another scan is
    already active for that account)."""
    settings = get_settings()
    db = SessionLocal()
    try:
        runs = SchedulerService(db, settings).run_due_schedules()
        for run in runs:
            logger.info(
                "scheduler tick started run %s for account %s (status=%s)",
                run.id,
                run.aws_account_id,
                run.status.value,
            )
        return len(runs)
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    started = tick()
    logger.info("scheduler tick complete: %d run(s) started", started)


if __name__ == "__main__":
    main()
