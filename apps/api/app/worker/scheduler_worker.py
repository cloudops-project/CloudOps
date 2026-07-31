"""Replica-safe scheduler process.

Each short tick locks due rows with ``SKIP LOCKED`` and only enqueues durable
PostgreSQL jobs. Signal handling stops future ticks without interrupting an
in-flight transaction.
"""

from __future__ import annotations

import logging
import signal
import threading

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.scheduler import SchedulerService
from app.worker.heartbeat import touch as touch_heartbeat

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
                "scheduler.run.enqueued",
                extra={
                    "event_name": "scheduler.run.enqueued",
                    "result": run.status.value,
                },
            )
        return len(runs)
    finally:
        db.close()


def run_forever(stop_event: threading.Event) -> None:
    settings = get_settings()
    while not stop_event.is_set():
        touch_heartbeat()
        started = tick()
        logger.info(
            "scheduler.tick.completed",
            extra={
                "event_name": "scheduler.tick.completed",
                "enqueued_count": started,
            },
        )
        stop_event.wait(settings.scheduler_poll_interval_seconds)
    touch_heartbeat()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop_event = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    run_forever(stop_event)


if __name__ == "__main__":
    main()
