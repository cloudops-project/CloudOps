from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class AWSExternalIDReservation(Base):
    """Immutable history of every external ID issued by CloudOps."""

    __tablename__ = "aws_external_id_reservations"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_aws_external_id_reservation_external_id"),
        UniqueConstraint("aws_account_id", name="uq_aws_external_id_reservation_account"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    aws_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("aws_accounts.id", ondelete="SET NULL")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
