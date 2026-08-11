"""Add subscriptions.current_period_end if missing.

003 may already be applied on DBs that lack this column; keep upgrade idempotent.

Revision ID: 004_subscription_period_end
Revises: 003_sales_leads_schema
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "004_subscription_period_end"
down_revision = "003_sales_leads_schema"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "subscriptions" not in inspect(bind).get_table_names():
        return
    if "current_period_end" not in _columns("subscriptions"):
        op.add_column(
            "subscriptions",
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "subscriptions" not in inspect(bind).get_table_names():
        return
    if "current_period_end" in _columns("subscriptions"):
        op.drop_column("subscriptions", "current_period_end")
