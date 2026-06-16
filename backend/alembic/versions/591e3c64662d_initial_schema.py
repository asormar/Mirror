"""initial schema

Revision ID: 591e3c64662d
Revises:
Create Date: 2026-06-15 19:29:33.623127

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "591e3c64662d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


entity_type_enum = sa.Enum(
    "HEDGE_FUND",
    "MUTUAL_FUND",
    "PENSION_FUND",
    "INSIDER",
    "POLITICIAN_US_HOUSE",
    "POLITICIAN_US_SENATE",
    name="entitytype",
)

source_type_enum = sa.Enum(
    "FORM_13F_HR",
    "FORM_13F_HR_A",
    "FORM_13G",
    "FORM_13D",
    "FORM_4",
    "HOUSE_PTR",
    "SENATE_PTR",
    name="sourcetype",
)

parsing_status_enum = sa.Enum("PENDING", "PARSED", "FAILED", name="parsingstatus")

trade_action_enum = sa.Enum("BUY", "SELL", name="tradeaction")

holding_action_enum = sa.Enum(
    "NEW", "INCREASE", "DECREASE", "UNCHANGED", "EXIT", name="holdingaction"
)

ledger_entry_type_enum = sa.Enum(
    "INITIAL_DEPOSIT",
    "TRADE_BUY",
    "TRADE_SELL",
    "FEE",
    "ADJUSTMENT",
    name="ledgerentrytype",
)


def upgrade() -> None:
    op.create_table(
        "target_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", entity_type_enum, nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False, server_default="US"),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("entity_type", "external_id", name="uq_entity_type_external_id"),
    )
    op.create_index("ix_target_entities_slug", "target_entities", ["slug"], unique=True)
    op.create_index("ix_target_entities_active", "target_entities", ["is_active", "entity_type"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("virtual_cash_balance", sa.Numeric(precision=18, scale=2), nullable=False, server_default=sa.text("100000.00")),
        sa.Column("initial_capital", sa.Numeric(precision=18, scale=2), nullable=False, server_default=sa.text("100000.00")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocation_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("100.00")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["target_entity_id"], ["target_entities.id"], ondelete="RESTRICT", name="fk_subscriptions_target_entity_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_subscriptions_user_id"),
        sa.UniqueConstraint("user_id", "target_entity_id", name="uq_subscription_user_entity"),
        sa.CheckConstraint("allocation_pct > 0 AND allocation_pct <= 100", name="ck_subscription_allocation_pct"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_target_entity_id", "subscriptions", ["target_entity_id"])

    op.create_table(
        "publication_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("source_filing_id", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("period_of_report", sa.Date(), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("detected_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
        sa.Column("parsing_status", parsing_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("parsing_error", sa.Text(), nullable=True),
        sa.Column("holdings_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["target_entity_id"], ["target_entities.id"], ondelete="CASCADE", name="fk_publication_events_target_entity_id"),
        sa.UniqueConstraint("target_entity_id", "source_type", "source_filing_id", name="uq_publication_dedup"),
    )
    op.create_index("ix_publication_target_published", "publication_events", ["target_entity_id", "published_at"])
    op.create_index("ix_publication_parsing_status", "publication_events", ["parsing_status"])

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("publication_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("total_value_usd", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["publication_event_id"], ["publication_events.id"], ondelete="CASCADE", name="fk_portfolio_snapshots_publication_event_id"),
        sa.ForeignKeyConstraint(["target_entity_id"], ["target_entities.id"], ondelete="CASCADE", name="fk_portfolio_snapshots_target_entity_id"),
        sa.UniqueConstraint("publication_event_id", name="uq_portfolio_snapshots_publication_event_id"),
    )
    op.create_index("ix_portfolio_snapshots_target_entity_id", "portfolio_snapshots", ["target_entity_id"])

    op.create_table(
        "holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("portfolio_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("cusip", sa.String(length=9), nullable=True),
        sa.Column("issuer_name", sa.String(length=255), nullable=False),
        sa.Column("shares", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("value_usd", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("position_pct", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("action", holding_action_enum, nullable=False),
        sa.Column("previous_shares", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["portfolio_snapshot_id"], ["portfolio_snapshots.id"], ondelete="CASCADE", name="fk_holdings_portfolio_snapshot_id"),
        sa.UniqueConstraint("portfolio_snapshot_id", "ticker", name="uq_holding_snapshot_ticker"),
    )
    op.create_index("ix_holdings_portfolio_snapshot_id", "holdings", ["portfolio_snapshot_id"])
    op.create_index("ix_holding_ticker", "holdings", ["ticker"])

    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("shares", sa.Numeric(precision=20, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_cost_basis", sa.Numeric(precision=18, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("total_invested_usd", sa.Numeric(precision=18, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("realized_pnl_usd", sa.Numeric(precision=18, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("first_acquired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_trade_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_positions_user_id"),
        sa.UniqueConstraint("user_id", "ticker", name="uq_position_user_ticker"),
    )
    op.create_index("ix_positions_user_id", "positions", ["user_id"])

    op.create_table(
        "virtual_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publication_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("action", trade_action_enum, nullable=False),
        sa.Column("shares", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("price_per_share", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("total_amount_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("fees_usd", sa.Numeric(precision=18, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("market_price_source", sa.String(length=64), nullable=False, server_default="yfinance:delayed"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["publication_event_id"], ["publication_events.id"], ondelete="CASCADE", name="fk_virtual_trades_publication_event_id"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="RESTRICT", name="fk_virtual_trades_subscription_id"),
        sa.ForeignKeyConstraint(["target_entity_id"], ["target_entities.id"], ondelete="RESTRICT", name="fk_virtual_trades_target_entity_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_virtual_trades_user_id"),
        sa.UniqueConstraint("user_id", "publication_event_id", "ticker", "action", name="uq_trade_idempotency"),
    )
    op.create_index("ix_virtual_trades_user_id", "virtual_trades", ["user_id"])
    op.create_index("ix_trade_user_executed", "virtual_trades", ["user_id", "executed_at"])
    op.create_index("ix_trade_publication", "virtual_trades", ["publication_event_id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("virtual_trade_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", ledger_entry_type_enum, nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("cash_balance_after_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("position_shares_after", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_ledger_entries_user_id"),
        sa.ForeignKeyConstraint(["virtual_trade_id"], ["virtual_trades.id"], ondelete="SET NULL", name="fk_ledger_entries_virtual_trade_id"),
    )
    op.create_index("ix_ledger_entries_user_id", "ledger_entries", ["user_id"])
    op.create_index("ix_ledger_user_created", "ledger_entries", ["user_id", "created_at"])

    op.create_table(
        "daily_pnl_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("cash_balance_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("positions_value_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("total_equity_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("realized_pnl_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("unrealized_pnl_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_daily_pnl_snapshots_user_id"),
        sa.UniqueConstraint("user_id", "date", name="uq_pnl_user_date"),
    )
    op.create_index("ix_daily_pnl_snapshots_user_id", "daily_pnl_snapshots", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_pnl_snapshots_user_id", table_name="daily_pnl_snapshots")
    op.drop_table("daily_pnl_snapshots")

    op.drop_index("ix_ledger_user_created", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_user_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_index("ix_trade_publication", table_name="virtual_trades")
    op.drop_index("ix_trade_user_executed", table_name="virtual_trades")
    op.drop_index("ix_virtual_trades_user_id", table_name="virtual_trades")
    op.drop_table("virtual_trades")

    op.drop_index("ix_positions_user_id", table_name="positions")
    op.drop_table("positions")

    op.drop_index("ix_holding_ticker", table_name="holdings")
    op.drop_index("ix_holdings_portfolio_snapshot_id", table_name="holdings")
    op.drop_table("holdings")

    op.drop_index("ix_portfolio_snapshots_target_entity_id", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")

    op.drop_index("ix_publication_parsing_status", table_name="publication_events")
    op.drop_index("ix_publication_target_published", table_name="publication_events")
    op.drop_table("publication_events")

    op.drop_index("ix_subscriptions_target_entity_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_target_entities_active", table_name="target_entities")
    op.drop_index("ix_target_entities_slug", table_name="target_entities")
    op.drop_table("target_entities")

    ledger_entry_type_enum.drop(op.get_bind(), checkfirst=True)
    holding_action_enum.drop(op.get_bind(), checkfirst=True)
    trade_action_enum.drop(op.get_bind(), checkfirst=True)
    parsing_status_enum.drop(op.get_bind(), checkfirst=True)
    source_type_enum.drop(op.get_bind(), checkfirst=True)
    entity_type_enum.drop(op.get_bind(), checkfirst=True)
