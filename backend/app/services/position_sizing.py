"""Position sizing math.

Single source of truth for the proportionality formula. The P&L chart,
the trade executor, and any future simulator read from here.

Formula (per AGENTS.md):
    usd_amount = user.total_equity * subscription.allocation_pct * holding_weight_pct
    shares     = floor(usd_amount / price_per_share)

The user.total_equity for the MVP is the User.virtual_cash_balance; a
later step will swap in a function that adds mark-to-market of open
positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

HUNDRED = Decimal("100")
ONE_CENT = Decimal("0.01")
ONE_SHARE = Decimal("0.000001")


@dataclass(frozen=True)
class BuySize:
    usd_amount: Decimal
    shares: Decimal


@dataclass(frozen=True)
class SellSize:
    shares: Decimal
    usd_amount: Decimal


def compute_buy_size(
    user_total_equity: Decimal,
    subscription_allocation_pct: Decimal,
    holding_weight_pct: Decimal,
    price_per_share: Decimal,
) -> BuySize:
    if user_total_equity < 0:
        raise ValueError("user_total_equity must be >= 0")
    if subscription_allocation_pct <= 0 or subscription_allocation_pct > HUNDRED:
        raise ValueError("subscription_allocation_pct must be in (0, 100]")
    if holding_weight_pct < 0 or holding_weight_pct > HUNDRED:
        raise ValueError("holding_weight_pct must be in [0, 100]")
    if price_per_share <= 0:
        raise ValueError("price_per_share must be > 0")

    usd_amount = (
        user_total_equity * subscription_allocation_pct / HUNDRED * holding_weight_pct / HUNDRED
    ).quantize(ONE_CENT, rounding=ROUND_HALF_UP)

    if usd_amount == 0:
        return BuySize(usd_amount=Decimal("0.00"), shares=Decimal("0"))

    shares = (usd_amount / price_per_share).quantize(ONE_SHARE, rounding=ROUND_DOWN)
    return BuySize(usd_amount=usd_amount, shares=shares)


def compute_sell_size(
    current_shares: Decimal,
    current_price_per_share: Decimal,
    new_target_shares: Decimal | None,
) -> SellSize:
    if current_shares < 0:
        raise ValueError("current_shares must be >= 0")
    if current_price_per_share <= 0:
        raise ValueError("current_price_per_share must be > 0")

    if new_target_shares is None:
        target = Decimal("0")
    else:
        if new_target_shares < 0:
            raise ValueError("new_target_shares must be >= 0")
        target = new_target_shares

    shares_to_sell = max(Decimal("0"), current_shares - target)
    shares_to_sell = shares_to_sell.quantize(ONE_SHARE, rounding=ROUND_DOWN)
    usd_amount = (shares_to_sell * current_price_per_share).quantize(
        ONE_CENT, rounding=ROUND_HALF_UP
    )
    return SellSize(shares=shares_to_sell, usd_amount=usd_amount)


def compute_new_target_shares(
    user_total_equity: Decimal,
    subscription_allocation_pct: Decimal,
    new_holding_weight_pct: Decimal,
    price_per_share: Decimal,
) -> Decimal:
    if new_holding_weight_pct == 0:
        return Decimal("0")
    size = compute_buy_size(
        user_total_equity=user_total_equity,
        subscription_allocation_pct=subscription_allocation_pct,
        holding_weight_pct=new_holding_weight_pct,
        price_per_share=price_per_share,
    )
    return size.shares
