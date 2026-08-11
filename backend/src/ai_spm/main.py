from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from sqlalchemy import text

from ai_spm.admin.api.v1.routes import router as admin_router
from ai_spm.admin.api.v1.billing_routes import router as admin_billing_router
from ai_spm.agent.api.v1.routes import router as agent_router
from ai_spm.billing.access_gate import SubscriptionAccessMiddleware
from ai_spm.billing.stripe_webhook import router as billing_router
from ai_spm.config import get_settings
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.jobs.scheduler import start_scheduler, stop_scheduler
from ai_spm.platform.api.v1.tenants import router as platform_router
from ai_spm.presentation.middleware.correlation_id import CorrelationIdMiddleware
from ai_spm.presentation.websocket.dashboard_ws import router as ws_router
from ai_spm.public.api.v1.signup import router as public_router
from ai_spm.tenant.middleware import OrgIdBodyValidationMiddleware, TenantContextMiddleware
from ai_spm.tenant.quota import QuotaMiddleware

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_ai_spm", env=settings.app_env)
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("shutting_down_ai_spm")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI Security Posture Management — SaaS Multi-Tenant Platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(QuotaMiddleware)
    app.add_middleware(OrgIdBodyValidationMiddleware)
    app.add_middleware(SubscriptionAccessMiddleware)
    app.add_middleware(TenantContextMiddleware)

    app.include_router(public_router)
    app.include_router(admin_router)
    app.include_router(admin_billing_router, prefix="/admin/v1")
    app.include_router(agent_router)
    app.include_router(platform_router)
    app.include_router(billing_router)
    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "ai-spm-core"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        """Readiness: Postgres reachable (Sprint 1 ops gate)."""
        try:
            async with get_platform_session() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning("readiness_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="database unavailable") from exc
        return {"status": "ready", "service": "ai-spm-core"}

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


app = create_app()
