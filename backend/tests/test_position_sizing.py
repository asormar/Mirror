"""Unit tests for the position-sizing math.

Pure-function tests; no DB, no network. The proportional formula is the
contract every other component (executor, P&L, future simulator) reads
from, so the cases here cover the boundaries the executor hits at runtime.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.position_sizing import (
    BuySize,
    compute_buy_size,
    compute_new_target_shares,
    compute_sell_size,
)

HUNDRED = Decimal("100")


def test_buy_size_basic_proportionality() -> None:
    size = compute_buy_size(
        user_total_equity=Decimal("100000.00"),
        subscription_allocation_pct=Decimal("50"),
        holding_weight_pct=Decimal("5"),
        price_per_share=Decimal("100.00"),
    )
    assert isinstance(size, BuySize)
    assert size.usd_amount == Decimal("2500.00")
    assert size.shares == Decimal("25.000000")


def test_buy_size_rounds_shares_down_to_micro_share() -> None:
    size = compute_buy_size(
        user_total_equity=Decimal("333.33"),
        subscription_allocation_pct=Decimal("33.33"),
        holding_weight_pct=Decimal("10"),
        price_per_share=Decimal("7.89"),
    )
    assert size.usd_amount.copy_abs() == size.usd_amount
    assert size.shares.as_tuple().exponent == -6


def test_buy_size_zero_when_holding_weight_zero() -> None:
    size = compute_buy_size(
        user_total_equity=Decimal("100000.00"),
        subscription_allocation_pct=Decimal("100"),
        holding_weight_pct=Decimal("0"),
        price_per_share=Decimal("100.00"),
    )
    assert size.usd_amount == Decimal("0.00")
    assert size.shares == Decimal("0")


def test_buy_size_rejects_invalid_percentages() -> None:
    with pytest.raises(ValueError):
        compute_buy_size(Decimal("1000"), Decimal("0"), Decimal("5"), Decimal("10"))
    with pytest.raises(ValueError):
        compute_buy_size(Decimal("1000"), Decimal("101"), Decimal("5"), Decimal("10"))
    with pytest.raises(ValueError):
        compute_buy_size(Decimal("1000"), Decimal("50"), Decimal("-1"), Decimal("10"))
    with pytest.raises(ValueError):
        compute_buy_size(Decimal("1000"), Decimal("50"), Decimal("101"), Decimal("10"))


def test_buy_size_rejects_invalid_price() -> None:
    with pytest.raises(ValueError):
        compute_buy_size(Decimal("1000"), Decimal("50"), Decimal("5"), Decimal("0"))


def test_sell_size_full_exit_when_target_is_none() -> None:
    sell = compute_sell_size(
        current_shares=Decimal("10"),
        current_price_per_share=Decimal("50.00"),
        new_target_shares=None,
    )
    assert sell.shares == Decimal("10.000000")
    assert sell.usd_amount == Decimal("500.00")


def test_sell_size_partial_trim() -> None:
    sell = compute_sell_size(
        current_shares=Decimal("20"),
        current_price_per_share=Decimal("100.00"),
        new_target_shares=Decimal("5"),
    )
    assert sell.shares == Decimal("15.000000")
    assert sell.usd_amount == Decimal("1500.00")


def test_sell_size_clamps_at_zero() -> None:
    sell = compute_sell_size(
        current_shares=Decimal("5"),
        current_price_per_share=Decimal("10.00"),
        new_target_shares=Decimal("10"),
    )
    assert sell.shares == Decimal("0")
    assert sell.usd_amount == Decimal("0.00")


def test_sell_size_rejects_negative_inputs() -> None:
    with pytest.raises(ValueError):
        compute_sell_size(Decimal("-1"), Decimal("10"), Decimal("5"))
    with pytest.raises(ValueError):
        compute_sell_size(Decimal("5"), Decimal("0"), Decimal("5"))
    with pytest.raises(ValueError):
        compute_sell_size(Decimal("5"), Decimal("10"), Decimal("-1"))


def test_compute_new_target_shares_zero_weight_is_zero() -> None:
    target = compute_new_target_shares(
        user_total_equity=Decimal("100000.00"),
        subscription_allocation_pct=HUNDRED,
        new_holding_weight_pct=Decimal("0"),
        price_per_share=Decimal("50.00"),
    )
    assert target == Decimal("0")


def test_compute_new_target_shares_full_weight_matches_buy() -> None:
    target = compute_new_target_shares(
        user_total_equity=Decimal("100000.00"),
        subscription_allocation_pct=Decimal("100"),
        new_holding_weight_pct=Decimal("100"),
        price_per_share=Decimal("200.00"),
    )
    assert target == Decimal("500.000000")
