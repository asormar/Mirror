import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPKMixin
from app.models.enums import LedgerEntryType


class LedgerEntry(Base, UUIDPKMixin):
    __tablename__ = "ledger_entries"
    __table_args__ = (Index("ix_ledger_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    virtual_trade_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("virtual_trades.id", ondelete="SET NULL")
    )
    entry_type: Mapped[LedgerEntryType] = mapped_column(nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash_balance_after_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    position_shares_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="ledger_entries")
    virtual_trade = relationship("VirtualTrade", back_populates="ledger_entries")
