import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.models.enums import HoldingAction, ParsingStatus, SourceType


class PublicationEvent(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "publication_events"
    __table_args__ = (
        UniqueConstraint(
            "target_entity_id",
            "source_type",
            "source_filing_id",
            name="uq_publication_dedup",
        ),
        Index(
            "ix_publication_target_published",
            "target_entity_id",
            "published_at",
        ),
        Index("ix_publication_parsing_status", "parsing_status"),
    )

    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("target_entities.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[SourceType] = mapped_column(nullable=False)
    source_filing_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    period_of_report: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parsing_status: Mapped[ParsingStatus] = mapped_column(
        nullable=False, default=ParsingStatus.PENDING
    )
    parsing_error: Mapped[str | None] = mapped_column(Text)
    holdings_count: Mapped[int | None] = mapped_column(Integer)

    target_entity = relationship("TargetEntity", back_populates="publications")
    portfolio_snapshot = relationship(
        "PortfolioSnapshot",
        back_populates="publication_event",
        uselist=False,
        cascade="all, delete-orphan",
    )


class PortfolioSnapshot(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "portfolio_snapshots"

    publication_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publication_events.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("target_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_value_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))

    publication_event = relationship("PublicationEvent", back_populates="portfolio_snapshot")
    holdings = relationship("Holding", back_populates="snapshot", cascade="all, delete-orphan")


class Holding(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_snapshot_id", "ticker", name="uq_holding_snapshot_ticker"),
        Index("ix_holding_ticker", "ticker"),
    )

    portfolio_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    cusip: Mapped[str | None] = mapped_column(String(9))
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)

    shares: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    value_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    position_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)

    action: Mapped[HoldingAction] = mapped_column(nullable=False)
    previous_shares: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))

    snapshot = relationship("PortfolioSnapshot", back_populates="holdings")
