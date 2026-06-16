"""Unit tests for the CUSIP -> ticker normalizer."""

from __future__ import annotations

from app.pipeline.normalizers.cusip_to_ticker import cusip_to_ticker, is_resolvable


def test_known_cusip_resolves_to_ticker() -> None:
    assert cusip_to_ticker("037833100") == "AAPL"
    assert cusip_to_ticker("594918104") == "MSFT"


def test_unknown_cusip_returns_none() -> None:
    assert cusip_to_ticker("999999999") is None


def test_empty_cusip_returns_none() -> None:
    assert cusip_to_ticker("") is None


def test_lookup_is_case_insensitive() -> None:
    assert cusip_to_ticker("037833100") == cusip_to_ticker("037833100".upper())


def test_is_resolvable_reflects_lookup() -> None:
    assert is_resolvable("037833100") is True
    assert is_resolvable("999999999") is False


def test_whitespace_is_stripped() -> None:
    assert cusip_to_ticker("  037833100  ") == "AAPL"
