"""Alembic: Starter/Professional plans, onboarding, sales leads, billing columns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_commercial_saas_plans"
down_revision: str | None = "002_saas_plans_entitlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).first()
    return row is not None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :table
            """
        ),
        {"table": table},
    ).first()
    return row is not None


def _enum_type_exists(name: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": name},
    ).first()
    return row is not None


def _enum_has_value(enum_name: str, value: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = :enum_name AND e.enumlabel = :value
            """
        ),
        {"enum_name": enum_name, "value": value},
    ).first()
    return row is not None


def upgrade() -> None:
    # Plan renames (skip when already migrated on patched dev DBs).
    if _enum_has_value("subscription_plan", "free"):
        op.execute("ALTER TYPE subscription_plan RENAME VALUE 'free' TO 'starter'")
    if _enum_has_value("subscription_plan", "pro"):
        op.execute("ALTER TYPE subscription_plan RENAME VALUE 'pro' TO 'professional'")

    # PG requires new enum labels to be committed before use in UPDATE (Alembic txn).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'incomplete'")
        op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'expired'")

    if not _enum_type_exists("onboarding_step"):
        op.execute(
            "CREATE TYPE onboarding_step AS ENUM "
            "('registered', 'email_verified', 'plan_selected', 'checkout_pending', 'complete')"
        )

    if _enum_has_value("subscription_status", "trialing") and _enum_has_value(
        "subscription_status", "incomplete"
    ):
        op.execute(
            """
            UPDATE subscriptions
            SET status = 'incomplete'
            WHERE status::text = 'trialing'
            """
        )

    if not _column_exists("subscriptions", "onboarding_step"):
        op.add_column(
            "subscriptions",
            sa.Column(
                "onboarding_step",
                postgresql.ENUM(
                    "registered",
                    "email_verified",
                    "plan_selected",
                    "checkout_pending",
                    "complete",
                    name="onboarding_step",
                    create_type=False,
                ),
                nullable=False,
                server_default="registered",
            ),
        )
    if not _column_exists("subscriptions", "max_prompts_per_month"):
        op.add_column(
            "subscriptions",
            sa.Column("max_prompts_per_month", sa.Integer(), nullable=False, server_default="50000"),
        )
    if not _column_exists("subscriptions", "stripe_checkout_session_id"):
        op.add_column(
            "subscriptions",
            sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        )
    if not _column_exists("subscriptions", "past_due_since"):
        op.add_column(
            "subscriptions",
            sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True),
        )

    op.execute(
        """
        UPDATE subscriptions SET
          max_agents = CASE plan::text
            WHEN 'starter' THEN 25
            WHEN 'professional' THEN 150
            WHEN 'enterprise' THEN 0
            ELSE max_agents END,
          max_prompts_per_month = CASE plan::text
            WHEN 'starter' THEN 50000
            WHEN 'professional' THEN 500000
            WHEN 'enterprise' THEN 0
            ELSE COALESCE(max_prompts_per_month, 50000) END,
          max_prompts_per_day = CASE plan::text
            WHEN 'starter' THEN 1667
            WHEN 'professional' THEN 16667
            WHEN 'enterprise' THEN 0
            ELSE max_prompts_per_day END,
          audit_retention_days = CASE plan::text
            WHEN 'starter' THEN 7
            WHEN 'professional' THEN 30
            WHEN 'enterprise' THEN 365
            ELSE audit_retention_days END,
          onboarding_step = CASE
            WHEN status::text = 'active' THEN 'complete'::onboarding_step
            ELSE COALESCE(onboarding_step, 'registered'::onboarding_step) END
        """
    )

    if not _table_exists("sales_leads"):
        op.create_table(
            "sales_leads",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("company_name", sa.String(255), nullable=False),
            sa.Column("contact_name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("phone", sa.String(64), nullable=True),
            sa.Column("estimated_agents", sa.Integer(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="new"),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_sales_leads_status_created", "sales_leads", ["status", "created_at"])
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE sales_leads TO aispm_app")
        op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aispm_app")


def downgrade() -> None:
    if _table_exists("sales_leads"):
        op.drop_index("ix_sales_leads_status_created", table_name="sales_leads")
        op.drop_table("sales_leads")
    if _column_exists("subscriptions", "past_due_since"):
        op.drop_column("subscriptions", "past_due_since")
    if _column_exists("subscriptions", "stripe_checkout_session_id"):
        op.drop_column("subscriptions", "stripe_checkout_session_id")
    if _column_exists("subscriptions", "max_prompts_per_month"):
        op.drop_column("subscriptions", "max_prompts_per_month")
    if _column_exists("subscriptions", "onboarding_step"):
        op.drop_column("subscriptions", "onboarding_step")
    if _enum_type_exists("onboarding_step"):
        op.execute("DROP TYPE onboarding_step")
    if _enum_has_value("subscription_plan", "starter"):
        op.execute("ALTER TYPE subscription_plan RENAME VALUE 'starter' TO 'free'")
    if _enum_has_value("subscription_plan", "professional"):
        op.execute("ALTER TYPE subscription_plan RENAME VALUE 'professional' TO 'pro'")
