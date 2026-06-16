"""CUSIP -> ticker normalizer.

Real CUSIP resolution requires a paid service (e.g. Refinitiv, Bloomberg)
or a manually curated dataset. This module ships a small static table
covering the most common 13F holdings so the pipeline is end-to-end
testable; unresolvable CUSIPs are returned as None and the caller decides
whether to skip the holding or store it as unparseable.
"""

from __future__ import annotations

from functools import lru_cache

# Subset of CUSIP-9 -> ticker mappings for the most-held names in 13F filings.
# This is intentionally tiny; production should swap this for a real data
# source (SEC's quarterly `company_tickers.json` covers tickers but not
# CUSIPs, so a paid feed or a curated spreadsheet is the realistic path).
_STATIC_CUSIP_TO_TICKER: dict[str, str] = {
    "037833100": "AAPL",
    "594918104": "MSFT",
    "02079K305": "GOOGL",
    "02079K101": "GOOG",
    "023135106": "AMZN",
    "30303M102": "META",
    "67066G104": "NVDA",
    "88160R101": "TSLA",
    "46625H100": "JPM",
    "06051GHF9": "BAC",
    "92826C839": "VISA",
    "57636Q104": "MA",
    "30231G102": "XOM",
    "68389X105": "ORCL",
    "928563TM1": "WMT",
    "17275R102": "CSCO",
    "191216100": "KO",
    "22160K105": "COST",
    "302490109": "F",
    "928563BG6": "WFC",
}


@lru_cache(maxsize=1)
def _static_table() -> dict[str, str]:
    return dict(_STATIC_CUSIP_TO_TICKER)


def cusip_to_ticker(cusip: str) -> str | None:
    if not cusip:
        return None
    return _static_table().get(cusip.strip().upper())


def is_resolvable(cusip: str) -> bool:
    return cusip_to_ticker(cusip) is not None
