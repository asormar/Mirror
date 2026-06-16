import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPKMixin


class Subscription(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "uq_subscription_user_entity_active",
            "user_id",
            "target_entity_id",
            unique=True,
            postgresql_where=text("is_active = TRUE"),
        ),
        CheckConstraint(
            "allocation_pct > 0 AND allocation_pct <= 100",
            name="ck_subscription_allocation_pct",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("target_entities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    allocation_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("100.00")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="subscriptions")
    target_entity = relationship("TargetEntity", back_populates="subscriptions")
