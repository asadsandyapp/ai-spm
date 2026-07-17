import structlog

from ai_spm.config import get_settings

logger = structlog.get_logger(__name__)


async def send_verification_email(email: str, token: str, org_name: str) -> None:
    """Send email verification — logs in dev; integrate SendGrid/SES in production."""
    settings = get_settings()
    base = settings.app_base_url.rstrip("/")
    verify_url = f"{base}/verify-email?token={token}"
    logger.info(
        "verification_email_sent",
        email=email,
        org_name=org_name,
        verify_url=verify_url,
        verification_token=token if settings.app_env != "production" else None,
    )


async def send_welcome_email(email: str, org_name: str, org_token: str) -> None:
    settings = get_settings()
    payload: dict = {
        "email": email,
        "org_name": org_name,
        "org_token_prefix": org_token[:8] + "...",
    }
    # Non-production: log full token once for agent install demos.
    if settings.app_env != "production":
        payload["org_token"] = org_token
    logger.info("welcome_email_sent", **payload)
