"""Trade executor: turns a 13F holding into a VirtualTrade for a subscriber.

Transaction rules:
  - One DB transaction per trade.
  - VirtualTrade is the join point; Position and LedgerEntry are derived
    from it and must be consistent (fix the executor, not the cache).
  - Idempotency is enforced by the UniqueConstraint
    (user_id, publication_event_id, ticker, action) on VirtualTrade.
    The executor checks first and short-circuits if the row already
    exists, so concurrent jobs cannot double-execute.

Action mapping (13F -> executor):
  - NEW         -> BUY  (open a position)
  - INCREASE    -> BUY  (top up an existing position)
  - UNCHANGED   -> skip (no trade)
  - DECREASE    -> SELL (trim the position; never below zero)
  - EXIT        -> SELL (close the position entirely)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    HoldingAction,
    LedgerEntryType,
    TradeAction,
)
from app.models.ledger import LedgerEntry
from app.models.position import Position
from app.models.publication import Holding, PublicationEvent
from app.models.subscription import Subscription
from app.models.trade import VirtualTrade
from app.models.user import User
from app.services.position_sizing import (
    compute_buy_size,
    compute_new_target_shares,
    compute_sell_size,
)
from app.services.pricing_service import PriceQuote

logger = logging.getLogger(__name__)


class SkipTradeError(Exception):
    """Raised when a trade is intentionally not executed (e.g. UNCHANGED)."""


@dataclass(frozen=True)
class TradeResult:
    virtual_trade_id: uuid.UUID
    user_id: uuid.UUID
    ticker: str
    action: TradeAction
    shares: Decimal
    price_per_share: Decimal
    total_amount_usd: Decimal


def map_holding_action_to_trade(action: HoldingAction) -> TradeAction | None:
    if action in (HoldingAction.NEW, HoldingAction.INCREASE):
        return TradeAction.BUY
    if action in (HoldingAction.DECREASE, HoldingAction.EXIT):
        return TradeAction.SELL
    return None


async def _existing_idempotent_trade(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    publication_event_id: uuid.UUID,
    ticker: str,
    action: TradeAction,
) -> VirtualTrade | None:
    result = await db.execute(
        select(VirtualTrade).where(
            VirtualTrade.user_id == user_id,
            VirtualTrade.publication_event_id == publication_event_id,
            VirtualTrade.ticker == ticker,
            VirtualTrade.action == action,
        )
    )
    return result.scalar_one_or_none()


async def _load_position(db: AsyncSession, *, user_id: uuid.UUID, ticker: str) -> Position | None:
    result = await db.execute(
        select(Position).where(Position.user_id == user_id, Position.ticker == ticker)
    )
    return result.scalar_one_or_none()


async def _upsert_position_after_buy(
    db: AsyncSession,
    *,
    user: User,
    ticker: str,
    shares: Decimal,
    price: Decimal,
    total_amount: Decimal,
    when: datetime,
) -> Position:
    position = await _load_position(db, user_id=user.id, ticker=ticker)
    if position is None:
        position = Position(
            user_id=user.id,
            ticker=ticker,
            shares=Decimal("0"),
            avg_cost_basis=Decimal("0"),
            total_invested_usd=Decimal("0"),
            realized_pnl_usd=Decimal("0"),
            first_acquired_at=when,
        )
        db.add(position)
        await db.flush()

    new_shares = position.shares + shares
    new_invested = position.total_invested_usd + total_amount
    new_avg = new_invested / new_shares if new_shares > 0 else Decimal("0")
    position.shares = new_shares
    position.avg_cost_basis = new_avg
    position.total_invested_usd = new_invested
    position.last_trade_at = when
    return position


async def _upsert_position_after_sell(
    db: AsyncSession,
    *,
    user: User,
    ticker: str,
    shares: Decimal,
    price: Decimal,
    total_amount: Decimal,
    realized_pnl: Decimal,
    when: datetime,
) -> Position:
    position = await _load_position(db, user_id=user.id, ticker=ticker)
    if position is None:
        raise SkipTradeError(f"cannot SELL {ticker}: user has no position")

    new_shares = position.shares - shares
    if new_shares < 0:
        logger.warning(
            "SELL %s for user %s would oversell: current=%s, sell=%s, clamping to 0",
            ticker,
            user.id,
            position.shares,
            shares,
        )
        new_shares = Decimal("0")

    position.shares = new_shares
    position.realized_pnl_usd = position.realized_pnl_usd + realized_pnl
    position.last_trade_at = when
    return position


async def execute_trade(
    db: AsyncSession,
    *,
    user: User,
    subscription: Subscription,
    publication_event: PublicationEvent,
    holding: Holding,
    price_quote: PriceQuote,
    market_price_source: str | None = None,
) -> TradeResult:
    trade_action = map_holding_action_to_trade(holding.action)
    if trade_action is None:
        raise SkipTradeError(f"holding action {holding.action} does not produce a trade")

    existing = await _existing_idempotent_trade(
        db,
        user_id=user.id,
        publication_event_id=publication_event.id,
        ticker=holding.ticker,
        action=trade_action,
    )
    if existing is not None:
        return TradeResult(
            virtual_trade_id=existing.id,
            user_id=existing.user_id,
            ticker=existing.ticker,
            action=existing.action,
            shares=existing.shares,
            price_per_share=existing.price_per_share,
            total_amount_usd=existing.total_amount_usd,
        )

    user_total_equity = user.virtual_cash_balance
    price = price_quote.price
    now = datetime.now(UTC)

    if trade_action == TradeAction.BUY:
        size = compute_buy_size(
            user_total_equity=user_total_equity,
            subscription_allocation_pct=subscription.allocation_pct,
            holding_weight_pct=holding.position_pct,
            price_per_share=price,
        )
        if size.shares <= 0:
            raise SkipTradeError(
                f"buy size rounds to zero shares (usd={size.usd_amount}, price={price})"
            )
        if size.usd_amount > user.virtual_cash_balance:
            raise SkipTradeError(
                f"insufficient cash: need {size.usd_amount}, have {user.virtual_cash_balance}"
            )
        shares = size.shares
        total_amount = size.usd_amount
        new_cash = user.virtual_cash_balance - total_amount
        position = await _upsert_position_after_buy(
            db,
            user=user,
            ticker=holding.ticker,
            shares=shares,
            price=price,
            total_amount=total_amount,
            when=now,
        )
        ledger_entry_type = LedgerEntryType.TRADE_BUY
        ledger_amount = -total_amount
        realized_pnl = Decimal("0")
    else:
        existing_position = await _load_position(db, user_id=user.id, ticker=holding.ticker)
        current_shares = existing_position.shares if existing_position else Decimal("0")
        if current_shares <= 0:
            raise SkipTradeError(f"cannot SELL {holding.ticker}: no open position")
        new_target_shares = compute_new_target_shares(
            user_total_equity=user_total_equity,
            subscription_allocation_pct=subscription.allocation_pct,
            new_holding_weight_pct=holding.position_pct,
            price_per_share=price,
        )
        sell = compute_sell_size(
            current_shares=current_shares,
            current_price_per_share=price,
            new_target_shares=new_target_shares,
        )
        if sell.shares <= 0:
            raise SkipTradeError(f"sell size rounds to zero shares (current={current_shares})")
        shares = sell.shares
        total_amount = sell.usd_amount
        new_cash = user.virtual_cash_balance + total_amount
        avg_cost = existing_position.avg_cost_basis if existing_position else Decimal("0")
        realized_pnl = (price - avg_cost) * shares
        position = await _upsert_position_after_sell(
            db,
            user=user,
            ticker=holding.ticker,
            shares=shares,
            price=price,
            total_amount=total_amount,
            realized_pnl=realized_pnl,
            when=now,
        )
        ledger_entry_type = LedgerEntryType.TRADE_SELL
        ledger_amount = total_amount

    trade = VirtualTrade(
        user_id=user.id,
        target_entity_id=publication_event.target_entity_id,
        publication_event_id=publication_event.id,
        subscription_id=subscription.id,
        ticker=holding.ticker,
        action=trade_action,
        shares=shares,
        price_per_share=price,
        total_amount_usd=total_amount,
        fees_usd=Decimal("0.00"),
        executed_at=now,
        market_price_source=market_price_source or price_quote.source,
        note=None,
    )
    db.add(trade)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise SkipTradeError(f"idempotency hit on insert: {e.orig}") from e

    ledger = LedgerEntry(
        user_id=user.id,
        virtual_trade_id=trade.id,
        entry_type=ledger_entry_type,
        amount_usd=ledger_amount,
        cash_balance_after_usd=new_cash,
        position_shares_after=position.shares,
        description=f"{ledger_entry_type.value} {shares} {holding.ticker} @ {price}",
        created_at=now,
    )
    db.add(ledger)

    user.virtual_cash_balance = new_cash
    await db.commit()
    await db.refresh(trade)

    return TradeResult(
        virtual_trade_id=trade.id,
        user_id=trade.user_id,
        ticker=trade.ticker,
        action=trade.action,
        shares=trade.shares,
        price_per_share=trade.price_per_share,
        total_amount_usd=trade.total_amount_usd,
    )
