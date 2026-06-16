"""Sanity check: the SQLAlchemy metadata is populated and Alembic can load it."""

from app.db.base import Base
from app.models.enums import (
    EntityType,
    HoldingAction,
    LedgerEntryType,
    ParsingStatus,
    SourceType,
    TradeAction,
)
from app.models.ledger import LedgerEntry
from app.models.pnl import DailyPnlSnapshot
from app.models.position import Position
from app.models.publication import (
    Holding,
    PortfolioSnapshot,
    PublicationEvent,
)
from app.models.subscription import Subscription
from app.models.target_entity import TargetEntity
from app.models.trade import VirtualTrade
from app.models.user import User


def test_all_tables_registered() -> None:
    expected = {
        "users",
        "target_entities",
        "subscriptions",
        "publication_events",
        "portfolio_snapshots",
        "holdings",
        "virtual_trades",
        "positions",
        "ledger_entries",
        "daily_pnl_snapshots",
    }
    actual = set(Base.metadata.tables.keys())
    assert actual == expected, f"missing={expected - actual}, extra={actual - expected}"


def test_models_importable() -> None:
    assert User is not None
    assert TargetEntity is not None
    assert Subscription is not None
    assert PublicationEvent is not None
    assert PortfolioSnapshot is not None
    assert Holding is not None
    assert VirtualTrade is not None
    assert Position is not None
    assert LedgerEntry is not None
    assert DailyPnlSnapshot is not None


def test_enums_have_expected_values() -> None:
    assert EntityType.HEDGE_FUND.value == "HEDGE_FUND"
    assert SourceType.FORM_13F_HR.value == "FORM_13F_HR"
    assert ParsingStatus.PENDING.value == "PENDING"
    assert TradeAction.BUY.value == "BUY"
    assert HoldingAction.INCREASE.value == "INCREASE"
    assert LedgerEntryType.TRADE_BUY.value == "TRADE_BUY"
