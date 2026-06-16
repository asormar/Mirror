"""13F-HR primary document parser.

Handles the classic informationTable format. Newer (2024+) EDGAR format
returns ParsingStatus-equivalent error so the pipeline can flag and skip
rather than silently dropping the filing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from lxml import etree

logger = logging.getLogger(__name__)


class ThirteenFParseError(Exception):
    """Raised when the 13F primary document cannot be parsed."""


@dataclass(frozen=True)
class ParsedHolding:
    cusip: str
    issuer_name: str
    title_of_class: str | None
    value_usd: Decimal
    shares: Decimal | None
    put_call: str | None
    voting_authority_sole: Decimal | None
    voting_authority_shared: Decimal | None
    voting_authority_none: Decimal | None


@dataclass(frozen=True)
class ParsedThirteenF:
    period_of_report: date | None
    total_value_usd: Decimal | None
    holdings: list[ParsedHolding]


def _xpath_text(node: Any, expr: str) -> str | None:
    found = node.xpath(expr)
    if not found:
        return None
    value = found[0]
    if hasattr(value, "text") and value.text is not None:
        result: str | None = value.text.strip()
    else:
        raw = str(value).strip()
        result = raw or None
    return result


def _parse_decimal(text: str | None) -> Decimal | None:
    if text is None:
        return None
    cleaned = text.replace(",", "").strip()
    if not cleaned:
        return None
    return Decimal(cleaned)


def _parse_shares(node: Any) -> Decimal | None:
    raw = _xpath_text(node, ".//shrsOrPrnAmt/sshPrnamt/text()")
    return _parse_decimal(raw)


def _parse_holding(node: Any) -> ParsedHolding:
    cusip = _xpath_text(node, "./cusip/text()")
    if not cusip:
        raise ThirteenFParseError("holding without cusip")
    name = _xpath_text(node, "./nameOfIssuer/text()") or ""
    title = _xpath_text(node, "./titleOfClass/text()")
    value_thousands = _parse_decimal(_xpath_text(node, "./value/text()")) or Decimal("0")
    value_usd = value_thousands * Decimal("1000")
    shares = _parse_shares(node)
    put_call = _xpath_text(node, "./putCall/text()")
    sole = _parse_decimal(_xpath_text(node, "./votingAuthority/Sole/text()"))
    shared = _parse_decimal(_xpath_text(node, "./votingAuthority/Shared/text()"))
    none_v = _parse_decimal(_xpath_text(node, "./votingAuthority/None/text()"))
    return ParsedHolding(
        cusip=cusip,
        issuer_name=name,
        title_of_class=title,
        value_usd=value_usd,
        shares=shares,
        put_call=put_call,
        voting_authority_sole=sole,
        voting_authority_shared=shared,
        voting_authority_none=none_v,
    )


def parse_13f_text(text: str) -> ParsedThirteenF:
    """Parse a 13F-HR primary document in the classic informationTable format.

    Raises ThirteenFParseError if the document uses the newer EDGAR format
    or otherwise cannot be interpreted.
    """
    try:
        root = etree.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except etree.XMLSyntaxError as e:
        raise ThirteenFParseError(f"invalid XML: {e}") from e

    info_tables_raw = root.xpath("//*[local-name()='infoTable']")
    info_tables: list[Any] = list(info_tables_raw) if isinstance(info_tables_raw, list) else []
    if not info_tables:
        if root.xpath("//*[local-name()='edgarSubmission']"):
            raise ThirteenFParseError(
                "13F in newer EDGAR format (edgarSubmission) is not supported yet"
            )
        raise ThirteenFParseError("no infoTable elements found")

    period_text = _xpath_text(root, "//*[local-name()='periodOfReport']/text()") or _xpath_text(
        root, "//*[local-name()='reportCalendarOrQuarter']/text()"
    )
    period: date | None = None
    if period_text:
        try:
            period = date.fromisoformat(period_text)
        except ValueError:
            period = None

    holdings: list[ParsedHolding] = []
    for node in info_tables:
        try:
            holdings.append(_parse_holding(node))
        except ThirteenFParseError as e:
            logger.warning("skipping malformed holding: %s", e)

    total_value = sum((h.value_usd for h in holdings), Decimal("0"))
    return ParsedThirteenF(
        period_of_report=period,
        total_value_usd=total_value if total_value > 0 else None,
        holdings=holdings,
    )
