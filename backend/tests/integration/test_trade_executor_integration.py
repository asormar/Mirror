"""End-to-end tests for the trade executor against real PostgreSQL.

The executor is the only component that mutates four tables at once
(VirtualTrade, Position, LedgerEntry, User.virtual_cash_balance). These
tests exercise the BUY and SELL paths, the idempotency guarantee, and
the DECREASE / EXIT branches.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    HoldingAction,
    LedgerEntryType,
    SourceType,
    TradeAction,
)
from app.models.ledger import LedgerEntry
from app.models.position import Position
from app.models.publication import Holding, PortfolioSnapshot, PublicationEvent
from app.models.subscription import Subscription
from app.models.target_entity import TargetEntity
from app.models.trade import VirtualTrade
from app.models.user import User
from app.services.pricing_service import PriceQuote
from app.services.trade_executor import SkipTradeError, execute_trade

pytestmark = pytest.mark.integration


def _quote(ticker: str, price: Decimal) -> PriceQuote:
    return PriceQuote(
        ticker=ticker,
        price=price,
        currency="USD",
        as_of=datetime.now(UTC),
        source="test:unit",
    )


async def _make_user(db: AsyncSession, email: str, cash: Decimal) -> User:
    user = User(
        email=email,
        password_hash="x" * 60,
        full_name="Test User",
        virtual_cash_balance=cash,
        initial_capital=cash,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_event_with_holding(
    db: AsyncSession,
    *,
    target: TargetEntity,
    subscription: Subscription,
    ticker: str,
    cusip: str,
    issuer: str,
    action: HoldingAction,
    position_pct: Decimal,
    shares: Decimal,
) -> tuple[PublicationEvent, Holding]:
    event = PublicationEvent(
        target_entity_id=target.id,
        source_type=SourceType.FORM_13F_HR,
        source_filing_id=uuid.uuid4().hex,
        source_url="https://example.com/13f.xml",
        period_of_report=datetime.now(UTC).date(),
        published_at=datetime.now(UTC),
        detected_at=datetime.now(UTC),
        raw_payload={},
        parsing_status="PARSED",
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    snapshot = PortfolioSnapshot(
        publication_event_id=event.id,
        target_entity_id=target.id,
        captured_at=event.published_at,
        total_value_usd=Decimal("100000000.00"),
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    holding = Holding(
        portfolio_snapshot_id=snapshot.id,
        ticker=ticker,
        cusip=cusip,
        issuer_name=issuer,
        shares=shares,
        value_usd=Decimal("1000000.00"),
        position_pct=position_pct,
        action=action,
        previous_shares=None,
    )
    db.add(holding)
    await db.commit()
    await db.refresh(holding)
    return event, holding


async def test_new_holding_triggers_buy(
    client: AsyncClient,
    db_session: AsyncSession,
    target_entity: TargetEntity,
    second_target_entity: TargetEntity,
) -> None:
    user = await _make_user(db_session, "exec-new@example.com", Decimal("100000.00"))
    sub = Subscription(
        user_id=user.id,
        target_entity_id=target_entity.id,
        allocation_pct=Decimal("50.00"),
        started_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    event, holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.NEW,
        position_pct=Decimal("5.000"),
        shares=Decimal("1000"),
    )

    result = await execute_trade(
        db_session,
        user=user,
        subscription=sub,
        publication_event=event,
        holding=holding,
        price_quote=_quote("AAPL", Decimal("200.00")),
    )

    assert result.action == TradeAction.BUY
    expected_usd = Decimal("100000.00") * Decimal("0.50") * Decimal("0.05")
    assert result.total_amount_usd == expected_usd.quantize(Decimal("0.01"))
    assert result.shares == (result.total_amount_usd / Decimal("200.00")).quantize(
        Decimal("0.000001"), rounding=__import__("decimal").ROUND_DOWN
    )

    await db_session.refresh(user)
    assert user.virtual_cash_balance == Decimal("100000.00") - result.total_amount_usd

    pos_result = await db_session.execute(
        select(Position).where(Position.user_id == user.id, Position.ticker == "AAPL")
    )
    pos = pos_result.scalar_one()
    assert pos.shares == result.shares
    assert pos.avg_cost_basis == Decimal("200.00")

    ledger_result = await db_session.execute(
        select(LedgerEntry).where(LedgerEntry.virtual_trade_id == result.virtual_trade_id)
    )
    ledger = ledger_result.scalar_one()
    assert ledger.entry_type == LedgerEntryType.TRADE_BUY
    assert ledger.amount_usd == -result.total_amount_usd
    assert ledger.cash_balance_after_usd == user.virtual_cash_balance


async def test_idempotent_re_execution_returns_existing_trade(
    client: AsyncClient, db_session: AsyncSession, target_entity: TargetEntity
) -> None:
    user = await _make_user(db_session, "exec-idem@example.com", Decimal("100000.00"))
    sub = Subscription(
        user_id=user.id,
        target_entity_id=target_entity.id,
        allocation_pct=Decimal("100.00"),
        started_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    event, holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.NEW,
        position_pct=Decimal("10.000"),
        shares=Decimal("1000"),
    )
    quote = _quote("AAPL", Decimal("200.00"))

    first = await execute_trade(
        db_session,
        user=user,
        subscription=sub,
        publication_event=event,
        holding=holding,
        price_quote=quote,
    )
    second = await execute_trade(
        db_session,
        user=user,
        subscription=sub,
        publication_event=event,
        holding=holding,
        price_quote=quote,
    )
    assert first.virtual_trade_id == second.virtual_trade_id
    assert first.shares == second.shares
    assert first.total_amount_usd == second.total_amount_usd

    count_result = await db_session.execute(
        select(VirtualTrade).where(VirtualTrade.id == first.virtual_trade_id)
    )
    assert len(count_result.scalars().all()) == 1


async def test_exit_holding_triggers_full_sell(
    client: AsyncClient, db_session: AsyncSession, target_entity: TargetEntity
) -> None:
    user = await _make_user(db_session, "exec-exit@example.com", Decimal("100000.00"))
    sub = Subscription(
        user_id=user.id,
        target_entity_id=target_entity.id,
        allocation_pct=Decimal("100.00"),
        started_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    event, holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.NEW,
        position_pct=Decimal("20.000"),
        shares=Decimal("1000"),
    )
    await execute_trade(
        db_session,
        user=user,
        subscription=sub,
        publication_event=event,
        holding=holding,
        price_quote=_quote("AAPL", Decimal("200.00")),
    )

    exit_event, exit_holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.EXIT,
        position_pct=Decimal("0"),
        shares=Decimal("0"),
    )
    result = await execute_trade(
        db_session,
        user=user,
        subscription=sub,
        publication_event=exit_event,
        holding=exit_holding,
        price_quote=_quote("AAPL", Decimal("250.00")),
    )
    assert result.action == TradeAction.SELL

    pos_result = await db_session.execute(
        select(Position).where(Position.user_id == user.id, Position.ticker == "AAPL")
    )
    pos = pos_result.scalar_one()
    assert pos.shares == Decimal("0")
    assert pos.realized_pnl_usd == Decimal("5000.00")


async def test_decrease_holding_triggers_partial_sell(
    client: AsyncClient, db_session: AsyncSession, target_entity: TargetEntity
) -> None:
    user = await _make_user(db_session, "exec-dec@example.com", Decimal("100000.00"))
    sub = Subscription(
        user_id=user.id,
        target_entity_id=target_entity.id,
        allocation_pct=Decimal("100.00"),
        started_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    event, holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.NEW,
        position_pct=Decimal("20.000"),
        shares=Decimal("1000"),
    )
    await execute_trade(
        db_session,
        user=user,
        subscription=sub,
        publication_event=event,
        holding=holding,
        price_quote=_quote("AAPL", Decimal("200.00")),
    )

    dec_event, dec_holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.DECREASE,
        position_pct=Decimal("10.000"),
        shares=Decimal("500"),
    )
    result = await execute_trade(
        db_session,
        user=user,
        subscription=sub,
        publication_event=dec_event,
        holding=dec_holding,
        price_quote=_quote("AAPL", Decimal("200.00")),
    )
    assert result.action == TradeAction.SELL
    assert result.shares == Decimal("60.000000")

    pos_result = await db_session.execute(
        select(Position).where(Position.user_id == user.id, Position.ticker == "AAPL")
    )
    pos = pos_result.scalar_one()
    assert pos.shares == Decimal("40.000000")


async def test_sell_with_no_position_raises_skip(
    client: AsyncClient, db_session: AsyncSession, target_entity: TargetEntity
) -> None:
    user = await _make_user(db_session, "exec-nosell@example.com", Decimal("100000.00"))
    sub = Subscription(
        user_id=user.id,
        target_entity_id=target_entity.id,
        allocation_pct=Decimal("100.00"),
        started_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    event, holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.EXIT,
        position_pct=Decimal("0"),
        shares=Decimal("0"),
    )
    with pytest.raises(SkipTradeError):
        await execute_trade(
            db_session,
            user=user,
            subscription=sub,
            publication_event=event,
            holding=holding,
            price_quote=_quote("AAPL", Decimal("200.00")),
        )


async def test_unchanged_holding_is_skipped(
    client: AsyncClient, db_session: AsyncSession, target_entity: TargetEntity
) -> None:
    user = await _make_user(db_session, "exec-unchanged@example.com", Decimal("100000.00"))
    sub = Subscription(
        user_id=user.id,
        target_entity_id=target_entity.id,
        allocation_pct=Decimal("100.00"),
        started_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    event, holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.UNCHANGED,
        position_pct=Decimal("5.000"),
        shares=Decimal("100"),
    )
    with pytest.raises(SkipTradeError):
        await execute_trade(
            db_session,
            user=user,
            subscription=sub,
            publication_event=event,
            holding=holding,
            price_quote=_quote("AAPL", Decimal("200.00")),
        )


async def test_buy_with_tiny_weight_rounds_to_zero_shares_raises_skip(
    client: AsyncClient, db_session: AsyncSession, target_entity: TargetEntity
) -> None:
    user = await _make_user(db_session, "exec-poor@example.com", Decimal("1.00"))
    sub = Subscription(
        user_id=user.id,
        target_entity_id=target_entity.id,
        allocation_pct=Decimal("100.00"),
        started_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    event, holding = await _make_event_with_holding(
        db_session,
        target=target_entity,
        subscription=sub,
        ticker="AAPL",
        cusip="037833100",
        issuer="APPLE INC",
        action=HoldingAction.NEW,
        position_pct=Decimal("0.100"),
        shares=Decimal("1"),
    )
    with pytest.raises(SkipTradeError):
        await execute_trade(
            db_session,
            user=user,
            subscription=sub,
            publication_event=event,
            holding=holding,
            price_quote=_quote("AAPL", Decimal("200.00")),
        )
