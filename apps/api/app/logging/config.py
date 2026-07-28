from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)

SAFE_LOG_FIELDS = (
    "correlation_id",
    "job_id",
    "job_type",
    "worker_id",
    "attempt",
    "duration_ms",
    "status_code",
    "provider_key",
    "error_code",
    "retryable",
    "terminal_status",
    "enqueued_count",
    "queue_available",
    "queue_running",
    "queue_retry_wait",
    "queue_dead_lettered",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event_name": getattr(record, "event_name", record.getMessage()),
            "request_id": request_id_context.get(),
            "user_id": getattr(record, "user_id", None),
            "organization_id": getattr(record, "organization_id", None),
            "result": getattr(record, "result", None),
        }
        if hasattr(record, "error_type"):
            payload["error_type"] = record.error_type
        for field in SAFE_LOG_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
