from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


class TZAwareDateTime(TypeDecorator[datetime]):
    """DateTime(timezone=True) that always returns a timezone-aware value.

    SQLite has no native timezone-aware storage: SQLAlchemy stores the value
    as a naive string and returns a naive datetime on read, while a
    freshly-assigned in-memory value (e.g. from ``utc_now()``) stays
    timezone-aware until flushed and reloaded in a new session. That
    divergence produces inconsistent serialization (with vs. without a UTC
    offset) for the same instant depending on whether the value was just set
    or read back via a separate query. This type normalizes reads to
    UTC-aware regardless of backend, so PostgreSQL (which already round-trips
    tzinfo correctly) is unaffected and SQLite-backed tests are corrected to
    match. Any model column using ``DateTime(timezone=True)`` should use this
    type instead, so timestamp semantics stay consistent repository-wide.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TZAwareDateTime(), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZAwareDateTime(),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )
