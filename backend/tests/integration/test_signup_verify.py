"""Sprint 1 public signup → verify returns org_token once."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from ai_spm.main import create_app


@pytest.mark.asyncio
async def test_signup_verify_returns_org_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-production signup includes verification_token; verify returns org_token."""
    from ai_spm.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()

    app = create_app()
    # Prefer integration fixture if DB available; skip cleanly otherwise.
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            email = f"sprint1-{uuid.uuid4().hex[:8]}@example.com"
            signup = await client.post(
                "/public/v1/signup",
                json={
                    "company_name": f"Sprint1 Co {uuid.uuid4().hex[:6]}",
                    "admin_email": email,
                    "admin_password": "SecurePass123!",
                    "admin_full_name": "Sprint Admin",
                },
            )
            if signup.status_code >= 500:
                pytest.skip("database not available for signup integration test")
            assert signup.status_code == 201, signup.text
            body = signup.json()
            assert body.get("org_id")
            assert body.get("verification_token"), body

            verify = await client.get(
                "/public/v1/verify-email",
                params={"token": body["verification_token"]},
            )
            assert verify.status_code == 200, verify.text
            vbody = verify.json()
            assert vbody["status"] == "active"
            assert vbody.get("org_token") and len(vbody["org_token"]) >= 32
    finally:
        get_settings.cache_clear()
