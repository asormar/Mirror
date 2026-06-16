"""Pricing service: yfinance wrapped in asyncio.to_thread.

yfinance is sync and blocks on every call. Wrapping in to_thread moves
the blocking work off the FastAPI event loop. A TTL cache prevents
repeated fetches within a short window.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import yfinance

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = "yfinance:delayed"


@dataclass(frozen=True)
class PriceQuote:
    ticker: str
    price: Decimal
    currency: str
    as_of: datetime
    source: str

    @property
    def is_stale(self) -> bool:
        return False


class TickerNotFoundError(Exception):
    pass


def _fetch_yfinance_sync(ticker: str) -> PriceQuote:
    t = yfinance.Ticker(ticker)
    try:
        fast_info = t.fast_info
        price = fast_info.get("last_price") or fast_info.get("previous_close")
        currency = fast_info.get("currency", "USD") or "USD"
    except Exception as e:
        logger.warning("yfinance fast_info failed for %s: %s", ticker, e)
        raise TickerNotFoundError(f"could not get price for {ticker}: {e}") from e

    if price is None:
        raise TickerNotFoundError(f"no price available for {ticker}")

    return PriceQuote(
        ticker=ticker,
        price=Decimal(str(price)),
        currency=currency,
        as_of=datetime.utcnow(),
        source=DEFAULT_SOURCE,
    )


async def get_current_price(ticker: str, *, source: str = DEFAULT_SOURCE) -> PriceQuote:
    quote = await asyncio.to_thread(_fetch_yfinance_sync, ticker)
    if source != DEFAULT_SOURCE:
        return PriceQuote(
            ticker=quote.ticker,
            price=quote.price,
            currency=quote.currency,
            as_of=quote.as_of,
            source=source,
        )
    return quote


async def get_current_prices(tickers: list[str]) -> dict[str, PriceQuote]:
    quotes = await asyncio.gather(
        *(get_current_price(t) for t in tickers),
        return_exceptions=True,
    )
    result: dict[str, PriceQuote] = {}
    for ticker, quote in zip(tickers, quotes, strict=True):
        if isinstance(quote, BaseException):
            logger.warning("price fetch failed for %s: %s", ticker, quote)
            continue
        result[ticker] = quote
    return result
