import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.models.enums import TradeAction


class VirtualTrade(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "virtual_trades"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "publication_event_id",
            "ticker",
            "action",
            name="uq_trade_idempotency",
        ),
        Index("ix_trade_user_executed", "user_id", "executed_at"),
        Index("ix_trade_publication", "publication_event_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("target_entities.id", ondelete="RESTRICT"), nullable=False
    )
    publication_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publication_events.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False
    )

    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[TradeAction] = mapped_column(nullable=False)

    shares: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    price_per_share: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    total_amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fees_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )

    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    market_price_source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="yfinance:delayed"
    )
    note: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", back_populates="trades")
    ledger_entries = relationship("LedgerEntry", back_populates="virtual_trade")
