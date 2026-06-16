"""Unit tests for the 13F primary document parser."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pipeline.parsers.parser_13f import (
    ParsedHolding,
    ParsedThirteenF,
    ThirteenFParseError,
    parse_13f_text,
)

SAMPLE_13F = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>1234567</value>
    <shrsOrPrnAmt>
      <sshPrnamt>5000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <putCall></putCall>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>4500000</Sole>
      <Shared>0</Shared>
      <None>500000</None>
    </votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>765432</value>
    <shrsOrPrnAmt>
      <sshPrnamt>2000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_parse_sample_extracts_holdings() -> None:
    parsed = parse_13f_text(SAMPLE_13F)
    assert isinstance(parsed, ParsedThirteenF)
    assert len(parsed.holdings) == 2
    aapl, msft = parsed.holdings
    assert aapl.cusip == "037833100"
    assert aapl.issuer_name == "APPLE INC"
    assert aapl.value_usd == Decimal("1234567000")
    assert aapl.shares == Decimal("5000000")
    assert aapl.voting_authority_sole == Decimal("4500000")
    assert aapl.voting_authority_none == Decimal("500000")
    assert msft.cusip == "594918104"
    assert msft.shares == Decimal("2000000")


def test_parse_total_value_sums_holdings() -> None:
    parsed = parse_13f_text(SAMPLE_13F)
    expected = Decimal("1234567000") + Decimal("765432000")
    assert parsed.total_value_usd == expected


def test_parse_handles_missing_voting_authority() -> None:
    parsed = parse_13f_text(SAMPLE_13F)
    msft = parsed.holdings[1]
    assert msft.voting_authority_sole is None
    assert msft.voting_authority_shared is None


def test_parse_raises_on_empty_document() -> None:
    with pytest.raises(ThirteenFParseError):
        parse_13f_text("<?xml version='1.0'?><root></root>")


def test_parse_raises_on_new_edgar_format() -> None:
    new_format = """<?xml version='1.0'?>
    <edgarSubmission xmlns='http://www.sec.gov/edgar/thirteenffiler'>
      <headerData></headerData>
    </edgarSubmission>"""
    with pytest.raises(ThirteenFParseError, match="newer EDGAR format"):
        parse_13f_text(new_format)


def test_parse_skips_malformed_holding() -> None:
    mixed = """<?xml version='1.0'?>
    <informationTable>
      <infoTable>
        <nameOfIssuer>GOOD ONE</nameOfIssuer>
        <cusip>123456789</cusip>
        <value>100</value>
        <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt></shrsOrPrnAmt>
      </infoTable>
      <infoTable>
        <nameOfIssuer>NO CUSIP</nameOfIssuer>
        <value>200</value>
        <shrsOrPrnAmt><sshPrnamt>5</sshPrnamt></shrsOrPrnAmt>
      </infoTable>
    </informationTable>"""
    parsed = parse_13f_text(mixed)
    assert len(parsed.holdings) == 1
    assert parsed.holdings[0].cusip == "123456789"
    assert isinstance(parsed.holdings[0], ParsedHolding)
