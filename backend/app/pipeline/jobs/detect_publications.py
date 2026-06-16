"""Periodic job: detect newly published 13F-HR filings for active targets.

Pipeline:
  1. List active TargetEntity rows that file 13F-HR.
  2. For each, GET submissions JSON from SEC EDGAR.
  3. For each 13F-HR accession not already in DB:
       a. Create PublicationEvent (idempotent via uq_publication_dedup).
       b. Download primary_doc.xml, parse it.
       c. Persist PortfolioSnapshot + Holdings.
       d. For each active Subscription to the target, run trade_executor
          for every holding.
  4. Return counts of (events_created, trades_executed, errors).

Errors are caught per entity and persisted on the PublicationEvent so
one bad filing does not poison the rest of the run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.enums import (
    EntityType,
    HoldingAction,
    ParsingStatus,
    SourceType,
)
from app.models.publication import Holding, PortfolioSnapshot, PublicationEvent
from app.models.subscription import Subscription
from app.models.target_entity import TargetEntity
from app.pipeline.clients.sec_edgar import SecEdgarClient
from app.pipeline.normalizers.cusip_to_ticker import cusip_to_ticker
from app.pipeline.parsers.parser_13f import (
    ParsedHolding,
    ParsedThirteenF,
    ThirteenFParseError,
    parse_13f_text,
)
from app.services.pricing_service import get_current_prices
from app.services.trade_executor import SkipTradeError, execute_trade

logger = logging.getLogger(__name__)


@dataclass
class DetectionReport:
    entities_scanned: int
    events_created: int
    events_skipped_duplicate: int
    events_failed_parse: int
    trades_executed: int
    trades_skipped: int

    def to_log(self) -> str:
        return (
            f"entities={self.entities_scanned} events_created={self.events_created} "
            f"events_dup={self.events_skipped_duplicate} events_failed={self.events_failed_parse} "
            f"trades={self.trades_executed} skipped={self.trades_skipped}"
        )


def _previous_shares_for_holding(
    parsed: ParsedHolding,
    snapshot_holdings: list[Holding],
) -> HoldingAction:
    if parsed.shares is None:
        return HoldingAction.UNCHANGED
    return HoldingAction.NEW


def _compute_position_pct(value: float, total: float | None) -> float:
    if not total or total <= 0:
        return 0.0
    return (value / total) * 100.0


async def _persist_parsed_filing(
    db: AsyncSession,
    *,
    publication_event: PublicationEvent,
    parsed: ParsedThirteenF,
) -> list[Holding]:
    snapshot = PortfolioSnapshot(
        publication_event_id=publication_event.id,
        target_entity_id=publication_event.target_entity_id,
        captured_at=publication_event.published_at,
        total_value_usd=parsed.total_value_usd,
    )
    db.add(snapshot)
    await db.flush()

    holdings: list[Holding] = []
    total = float(parsed.total_value_usd) if parsed.total_value_usd is not None else 0.0
    for ph in parsed.holdings:
        ticker = cusip_to_ticker(ph.cusip)
        if ticker is None:
            logger.info("skipping unresolvable CUSIP %s (%s)", ph.cusip, ph.issuer_name)
            continue
        position_pct = _compute_position_pct(float(ph.value_usd), total)
        holding = Holding(
            portfolio_snapshot_id=snapshot.id,
            ticker=ticker,
            cusip=ph.cusip,
            issuer_name=ph.issuer_name,
            shares=ph.shares if ph.shares is not None else 0,
            value_usd=ph.value_usd,
            position_pct=position_pct,
            action=_previous_shares_for_holding(ph, []),
            previous_shares=None,
        )
        db.add(holding)
        holdings.append(holding)
    publication_event.holdings_count = len(holdings)
    await db.commit()
    return holdings


async def _execute_trades_for_event(
    db: AsyncSession,
    *,
    publication_event: PublicationEvent,
    holdings: list[Holding],
) -> tuple[int, int]:
    tickers = sorted({h.ticker for h in holdings})
    quotes = await get_current_prices(tickers)
    if not quotes:
        return 0, 0

    subs_result = await db.execute(
        select(Subscription).where(
            Subscription.target_entity_id == publication_event.target_entity_id,
            Subscription.is_active.is_(True),
        )
    )
    subscriptions = subs_result.scalars().all()
    if not subscriptions:
        return 0, 0

    executed = 0
    skipped = 0
    for sub in subscriptions:
        from app.models.user import User

        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one()
        for holding in holdings:
            quote = quotes.get(holding.ticker)
            if quote is None:
                skipped += 1
                continue
            try:
                await execute_trade(
                    db,
                    user=user,
                    subscription=sub,
                    publication_event=publication_event,
                    holding=holding,
                    price_quote=quote,
                )
                executed += 1
            except SkipTradeError as e:
                logger.info("trade skipped: %s", e)
                skipped += 1
    return executed, skipped


async def _known_accessions(db: AsyncSession, target_entity_id: str) -> set[str]:
    result = await db.execute(
        select(PublicationEvent.source_filing_id).where(
            PublicationEvent.target_entity_id == target_entity_id
        )
    )
    return {row[0] for row in result.all()}


async def _process_entity(
    db: AsyncSession,
    sec: SecEdgarClient,
    entity: TargetEntity,
) -> tuple[int, int, int, int, int]:
    events_created = 0
    events_dup = 0
    events_failed = 0
    trades = 0
    skipped = 0

    try:
        submissions = await sec.get_submissions(entity.external_id)
    except Exception as e:
        logger.error("submissions fetch failed for %s (%s): %s", entity.slug, entity.external_id, e)
        return 0, 0, 0, 0, 0

    known = await _known_accessions(db, str(entity.id))
    new_filings = sec.find_new_13f_filings(submissions, known_accession_numbers=known)

    for filing in new_filings:
        source_type = (
            SourceType.FORM_13F_HR if filing["form"] == "13F-HR" else SourceType.FORM_13F_HR_A
        )
        accession = filing["accession_number"]
        primary_doc = filing["primary_document"]
        source_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(entity.external_id)}/"
            f"{accession.replace('-', '')}/{primary_doc}"
        )
        event = PublicationEvent(
            target_entity_id=entity.id,
            source_type=source_type,
            source_filing_id=accession,
            source_url=source_url,
            period_of_report=_parse_iso_date(filing["report_date"]),
            published_at=_parse_iso_datetime(filing["filing_date"]),
            detected_at=_now_utc(),
            raw_payload=dict(filing),
            parsing_status=ParsingStatus.PENDING,
        )
        db.add(event)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            events_dup += 1
            continue
        events_created += 1

        try:
            text = await sec.get_filing_text(entity.external_id, accession, primary_doc)
            parsed = parse_13f_text(text)
        except (ThirteenFParseError, Exception) as e:
            logger.warning("parse failed for %s: %s", accession, e)
            event.parsing_status = ParsingStatus.FAILED
            event.parsing_error = str(e)[:1000]
            event.raw_payload = {**(event.raw_payload or {}), "raw_excerpt": (text or "")[:2000]}
            await db.commit()
            events_failed += 1
            continue

        event.parsing_status = ParsingStatus.PARSED
        event.raw_payload = {**(event.raw_payload or {}), "raw_excerpt": text[:2000]}
        await db.commit()

        holdings = await _persist_parsed_filing(db, publication_event=event, parsed=parsed)
        ex, sk = await _execute_trades_for_event(db, publication_event=event, holdings=holdings)
        trades += ex
        skipped += sk

    return events_created, events_dup, events_failed, trades, skipped


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _parse_iso_datetime(s: str | None) -> datetime:
    if not s:
        return _now_utc()
    try:
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return _now_utc()


def _now_utc() -> datetime:
    return datetime.now(UTC)


async def detect_publications(
    sec: SecEdgarClient | None = None,
    *,
    db_factory: Callable[[], Any] = AsyncSessionLocal,
) -> DetectionReport:
    own_client = sec is None
    client = sec or SecEdgarClient()
    if own_client:
        await client.__aenter__()

    report = DetectionReport(0, 0, 0, 0, 0, 0)
    try:
        async with db_factory() as db:
            result = await db.execute(
                select(TargetEntity).where(
                    TargetEntity.is_active.is_(True),
                    TargetEntity.entity_type.in_(
                        [EntityType.HEDGE_FUND, EntityType.MUTUAL_FUND, EntityType.PENSION_FUND]
                    ),
                )
            )
            entities = result.scalars().all()
            report.entities_scanned = len(entities)
            for entity in entities:
                created, dup, failed, trades, skipped = await _process_entity(db, client, entity)
                report.events_created += created
                report.events_skipped_duplicate += dup
                report.events_failed_parse += failed
                report.trades_executed += trades
                report.trades_skipped += skipped
    finally:
        if own_client:
            await client.__aexit__(None, None, None)

    logger.info("detect_publications: %s", report.to_log())
    return report
