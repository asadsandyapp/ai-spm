import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://aispm:aispm@localhost:5432/aispm_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("PLATFORM_JWT_SECRET_KEY", "test-platform-secret-for-ci")

from ai_spm.config import get_settings
from ai_spm.domain.enums import (
    AgentStatus,
    AuditEventType,
    OrganizationStatus,
    PlatformRole,
    SubscriptionPlan,
    SubscriptionStatus,
    UserRole,
)
from ai_spm.domain.models import (
    Agent,
    AuditEvent,
    Base,
    Organization,
    PlatformUser,
    Subscription,
    User,
)
from ai_spm.infrastructure.auth.password import (
    create_admin_access_token,
    create_platform_access_token,
    hash_password,
    hash_token,
)
from ai_spm.main import create_app

get_settings.cache_clear()


TENANT_TABLES = [
    "users", "agents", "policies", "audit_events", "departments",
    "llm_provider_configs", "subscriptions", "usage_daily",
    "tenant_invitations", "email_verification_tokens",
]


async def _apply_rls_policies(conn) -> None:
    await conn.execute(text("""
        DO $$ BEGIN
            CREATE ROLE aispm_app NOINHERIT LOGIN PASSWORD 'aispm_app';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))
    await conn.execute(text("GRANT USAGE ON SCHEMA public TO aispm_app"))
    await conn.execute(text("GRANT aispm_app TO aispm"))
    await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aispm_app"))
    await conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aispm_app"))
    for table in TENANT_TABLES:
        await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        for policy_name, operation, using in [
            ("tenant_isolation_select", "SELECT", "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"),
            ("tenant_isolation_insert", "INSERT", "WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"),
            ("tenant_isolation_update", "UPDATE", "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"),
            ("tenant_isolation_delete", "DELETE", "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"),
        ]:
            await conn.execute(text(f"""
                DO $$ BEGIN
                    CREATE POLICY {policy_name} ON {table}
                        FOR {operation}
                        {using};
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;
            """))


@pytest_asyncio.fixture
async def engine():
    settings = get_settings()
    eng = create_async_engine(str(settings.database_url), echo=False, poolclass=NullPool)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    import ai_spm.infrastructure.db.session as session_module

    session_module.engine = eng
    session_module.async_session_factory = factory

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await _apply_rls_policies(conn)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def reset_redis_pool() -> AsyncGenerator[None, None]:
    """Reset Redis client between tests to avoid event loop reuse issues."""
    import ai_spm.infrastructure.cache.redis as redis_module

    if redis_module._redis is not None:
        try:
            await redis_module._redis.aclose()
        except Exception:
            pass
        redis_module._redis = None
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_db(engine) -> AsyncGenerator[None, None]:
    """Truncate tenant data between tests to avoid unique constraint collisions."""
    from ai_spm.infrastructure.db.session import get_platform_session

    tables = [
        "billing_events", "platform_audit_logs", "email_verification_tokens",
        "tenant_invitations", "usage_daily", "llm_provider_configs",
        "audit_events", "policies", "agents", "departments", "users",
        "subscriptions", "organizations", "platform_users",
    ]
    async with get_platform_session() as session:
        for table in tables:
            await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("SET ROLE aispm_app"))
        yield session
        await session.execute(text("RESET ROLE"))
        await session.rollback()


@pytest_asyncio.fixture
async def tenant_a(db_session: AsyncSession) -> dict:
    from ai_spm.infrastructure.db.session import get_platform_session

    async with get_platform_session() as session:
        org = Organization(
            id=uuid.uuid4(),
            slug="acme-corp",
            name="Acme Corp",
            org_token_hash=hash_token("acme-org-token-secret-key-32chars-min"),
            status=OrganizationStatus.ACTIVE,
        )
        user = User(
            id=uuid.uuid4(),
            org_id=org.id,
            email="admin@acme.com",
            password_hash=hash_password("AcmeAdmin123!"),
            full_name="Acme Admin",
            role=UserRole.SUPER_ADMIN,
            email_verified=True,
        )
        sub = Subscription(
            org_id=org.id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            max_agents=10,
            max_prompts_per_day=1000,
            audit_retention_days=90,
        )
        agent = Agent(
            id=uuid.uuid4(),
            org_id=org.id,
            hostname="acme-ws-01",
            status=AgentStatus.ONLINE,
        )
        audit = AuditEvent(
            id=uuid.uuid4(),
            org_id=org.id,
            event_type=AuditEventType.PROMPT_SUBMITTED,
            agent_id=agent.id,
            masked_content="Acme secret audit content",
        )
        session.add_all([org, user, sub, agent, audit])
        await session.commit()
    return {
        "org": org,
        "user": user,
        "agent": agent,
        "audit": audit,
        "token": create_admin_access_token(str(user.id), str(org.id), user.role.value),
        "org_token": "acme-org-token-secret-key-32chars-min",
    }


@pytest_asyncio.fixture
async def tenant_b(db_session: AsyncSession) -> dict:
    from ai_spm.infrastructure.db.session import get_platform_session

    async with get_platform_session() as session:
        org = Organization(
            id=uuid.uuid4(),
            slug="beta-inc",
            name="Beta Inc",
            org_token_hash=hash_token("beta-org-token-secret-key-32chars-min"),
            status=OrganizationStatus.ACTIVE,
        )
        user = User(
            id=uuid.uuid4(),
            org_id=org.id,
            email="admin@beta.com",
            password_hash=hash_password("BetaAdmin123!"),
            full_name="Beta Admin",
            role=UserRole.SUPER_ADMIN,
            email_verified=True,
        )
        sub = Subscription(
            org_id=org.id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            max_agents=10,
            max_prompts_per_day=1000,
            audit_retention_days=90,
        )
        agent = Agent(
            id=uuid.uuid4(),
            org_id=org.id,
            hostname="beta-ws-01",
            status=AgentStatus.ONLINE,
        )
        audit = AuditEvent(
            id=uuid.uuid4(),
            org_id=org.id,
            event_type=AuditEventType.PROMPT_SUBMITTED,
            agent_id=agent.id,
            masked_content="Beta secret audit content",
        )
        session.add_all([org, user, sub, agent, audit])
        await session.commit()
    return {
        "org": org,
        "user": user,
        "agent": agent,
        "audit": audit,
        "token": create_admin_access_token(str(user.id), str(org.id), user.role.value),
        "org_token": "beta-org-token-secret-key-32chars-min",
    }


@pytest_asyncio.fixture
async def platform_admin(db_session: AsyncSession) -> dict:
    from ai_spm.infrastructure.db.session import get_platform_session

    async with get_platform_session() as session:
        user = PlatformUser(
            id=uuid.uuid4(),
            email="platform@test.aispm.io",
            password_hash=hash_password("PlatformTest123!"),
            full_name="Test Platform Admin",
            role=PlatformRole.PLATFORM_SUPER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
    return {
        "user": user,
        "token": create_platform_access_token(str(user.id), user.role.value),
    }


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
