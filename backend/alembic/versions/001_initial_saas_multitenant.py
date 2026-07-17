"""Initial schema with PostgreSQL Row-Level Security for tenant isolation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_saas_multitenant"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = [
    "users",
    "agents",
    "policies",
    "audit_events",
    "departments",
    "llm_provider_configs",
    "subscriptions",
    "usage_daily",
    "tenant_invitations",
    "email_verification_tokens",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    for name, values in [
        ("organization_status", ["pending", "active", "suspended", "deleted"]),
        ("subscription_plan", ["free", "pro", "enterprise"]),
        ("subscription_status", ["trialing", "active", "past_due", "canceled", "suspended"]),
        ("user_role", ["super_admin", "security_admin", "auditor", "viewer"]),
        ("platform_role", ["platform_super", "platform_support", "platform_billing"]),
        ("agent_status", ["pending", "online", "offline", "revoked"]),
        ("audit_event_type", [
            "prompt_submitted", "prompt_blocked", "policy_violation",
            "pii_detected", "threat_detected", "agent_registered",
            "agent_heartbeat", "admin_login", "config_changed",
        ]),
        ("policy_action", ["allow", "block", "alert"]),
    ]:
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({vals})")

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("org_token_hash", sa.String(255), nullable=True),
        sa.Column("status", postgresql.ENUM(create_type=False, name="organization_status"), nullable=False),
        sa.Column("settings", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "platform_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM(create_type=False, name="platform_role"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", postgresql.ENUM(create_type=False, name="subscription_plan"), nullable=False),
        sa.Column("status", postgresql.ENUM(create_type=False, name="subscription_status"), nullable=False),
        sa.Column("max_agents", sa.Integer, nullable=False),
        sa.Column("max_prompts_per_day", sa.Integer, nullable=False),
        sa.Column("audit_retention_days", sa.Integer, nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM(create_type=False, name="user_role"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("email_verified", sa.Boolean, server_default="false"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )
    op.create_index("ix_users_org_id_email", "users", ["org_id", "email"])

    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("org_id", "name", name="uq_departments_org_name"),
    )

    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("os_version", sa.String(100), nullable=True),
        sa.Column("agent_version", sa.String(50), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", postgresql.ENUM(create_type=False, name="agent_status"), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cert_fingerprint", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_agents_org_id_status", "agents", ["org_id", "status"])

    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("rules", postgresql.JSONB, server_default="{}"),
        sa.Column("is_default", sa.Boolean, server_default="false"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", postgresql.ENUM(create_type=False, name="audit_event_type"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("masked_content", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("policy_action", postgresql.ENUM(create_type=False, name="policy_action"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_events_org_id_created_at", "audit_events", ["org_id", "created_at"])

    op.create_table(
        "llm_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("api_key_encrypted", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("settings", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("org_id", "provider", name="uq_llm_provider_org"),
    )

    op.create_table(
        "usage_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prompts_count", sa.Integer, server_default="0"),
        sa.Column("active_agents", sa.Integer, server_default="0"),
        sa.UniqueConstraint("org_id", "usage_date", name="uq_usage_daily_org_date"),
    )

    op.create_table(
        "tenant_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM(create_type=False, name="user_role"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "platform_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stripe_event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, server_default="{}"),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_select ON {table}
                FOR SELECT
                USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """)
        op.execute(f"""
            CREATE POLICY tenant_isolation_insert ON {table}
                FOR INSERT
                WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """)
        op.execute(f"""
            CREATE POLICY tenant_isolation_update ON {table}
                FOR UPDATE
                USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
                WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """)
        op.execute(f"""
            CREATE POLICY tenant_isolation_delete ON {table}
                FOR DELETE
                USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """)

    op.execute("""
        DO $$ BEGIN
            CREATE ROLE aispm_app NOINHERIT LOGIN PASSWORD 'aispm_app';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO aispm_app")
    op.execute("GRANT aispm_app TO aispm")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aispm_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aispm_app")


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_select ON {table}")

    op.drop_table("billing_events")
    op.drop_table("platform_audit_logs")
    op.drop_table("email_verification_tokens")
    op.drop_table("tenant_invitations")
    op.drop_table("usage_daily")
    op.drop_table("llm_provider_configs")
    op.drop_table("audit_events")
    op.drop_table("policies")
    op.drop_table("agents")
    op.drop_table("departments")
    op.drop_table("users")
    op.drop_table("subscriptions")
    op.drop_table("platform_users")
    op.drop_table("organizations")

    for enum in [
        "policy_action", "audit_event_type", "agent_status", "platform_role",
        "user_role", "subscription_status", "subscription_plan", "organization_status",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
