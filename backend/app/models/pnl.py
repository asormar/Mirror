import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPKMixin


class DailyPnlSnapshot(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "daily_pnl_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_pnl_user_date"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    cash_balance_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    positions_value_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_equity_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    realized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unrealized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    user = relationship("User", back_populates="pnl_snapshots")
