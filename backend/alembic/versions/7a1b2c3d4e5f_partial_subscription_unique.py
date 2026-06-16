"""replace unconditional subscription unique constraint with partial index

Revision ID: 7a1b2c3d4e5f
Revises: 591e3c64662d
Create Date: 2026-06-16 09:30:00.000000

The original UniqueConstraint("user_id", "target_entity_id") blocks the
soft-delete + re-subscribe flow: a soft-deleted row (is_active=FALSE,
ended_at=...) still occupies the (user_id, target_entity_id) slot, so
inserting a new active subscription for the same target raises
UniqueViolationError.

We replace it with a partial unique index that only enforces uniqueness
when is_active = TRUE.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a1b2c3d4e5f"
down_revision: str | Sequence[str] | None = "591e3c64662d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_subscription_user_entity", "subscriptions", type_="unique")
    op.create_index(
        "uq_subscription_user_entity_active",
        "subscriptions",
        ["user_id", "target_entity_id"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_subscription_user_entity_active", table_name="subscriptions")
    op.create_unique_constraint(
        "uq_subscription_user_entity", "subscriptions", ["user_id", "target_entity_id"]
    )
