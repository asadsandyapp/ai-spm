"""Align sales_leads columns with SalesLead ORM model.

Old table used contact_email / estimated_seats; app expects email / estimated_agents / phone.
002 only created sales_leads when missing, so existing DBs kept the old shape.

Revision ID: 003_sales_leads_schema
Revises: 002_commercial_saas_plans
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "003_sales_leads_schema"
down_revision = "002_commercial_saas_plans"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    if not _table_exists("sales_leads"):
        op.create_table(
            "sales_leads",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("company_name", sa.String(255), nullable=False),
            sa.Column("contact_name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(64), nullable=True),
            sa.Column("estimated_agents", sa.Integer(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="new"),
            sa.Column("org_id", sa.UUID(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_sales_leads_status_created", "sales_leads", ["status", "created_at"])
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE sales_leads TO aispm_app")
        return

    cols = _columns("sales_leads")

    if "contact_email" in cols and "email" not in cols:
        op.alter_column("sales_leads", "contact_email", new_column_name="email")
        cols.discard("contact_email")
        cols.add("email")

    if "estimated_seats" in cols and "estimated_agents" not in cols:
        op.alter_column("sales_leads", "estimated_seats", new_column_name="estimated_agents")
        cols.discard("estimated_seats")
        cols.add("estimated_agents")

    if "phone" not in cols:
        op.add_column("sales_leads", sa.Column("phone", sa.String(64), nullable=True))

    if "email" not in _columns("sales_leads"):
        op.add_column("sales_leads", sa.Column("email", sa.String(255), nullable=True))
        op.execute("UPDATE sales_leads SET email = COALESCE(email, 'unknown@example.com')")
        op.alter_column("sales_leads", "email", nullable=False)

    # contact_name was nullable on the legacy table; model requires NOT NULL.
    op.execute(
        "UPDATE sales_leads SET contact_name = COALESCE(NULLIF(TRIM(contact_name), ''), 'Unknown')"
    )
    op.alter_column("sales_leads", "contact_name", nullable=False)

    # Model field used by Stripe/billing; never created in 001/002.
    if _table_exists("subscriptions") and "current_period_end" not in _columns("subscriptions"):
        op.add_column(
            "subscriptions",
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _table_exists("subscriptions") and "current_period_end" in _columns("subscriptions"):
        op.drop_column("subscriptions", "current_period_end")
    if not _table_exists("sales_leads"):
        return
    cols = _columns("sales_leads")
    if "email" in cols and "contact_email" not in cols:
        op.alter_column("sales_leads", "email", new_column_name="contact_email")
    if "estimated_agents" in cols and "estimated_seats" not in cols:
        op.alter_column("sales_leads", "estimated_agents", new_column_name="estimated_seats")
    if "phone" in _columns("sales_leads"):
        op.drop_column("sales_leads", "phone")
