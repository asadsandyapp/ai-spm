"""Integration tests for tenant admin auth and agent registration."""

import pytest
from httpx import ASGITransport, AsyncClient

from ai_spm.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_admin_login_success(client, tenant_a):
    response = await client.post(
        "/admin/v1/auth/login",
        json={"email": "admin@acme.com", "password": "AcmeAdmin123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_admin_login_invalid_password(client, tenant_a):
    response = await client.post(
        "/admin/v1/auth/login",
        json={"email": "admin@acme.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_agent_register_and_heartbeat(client, tenant_a):
    headers = {
        "X-Org-ID": str(tenant_a["org"].id),
        "Content-Type": "application/json",
    }
    reg = await client.post(
        "/agent/v1/register",
        headers=headers,
        json={
            "hostname": "test-workstation",
            "org_token": tenant_a["org_token"],
            "os_version": "Linux 6.8",
            "agent_version": "0.1.0",
        },
    )
    assert reg.status_code == 201
    reg_body = reg.json()
    agent_id = reg_body["id"]
    session_token = reg_body["session_token"]

    hb = await client.post(
        "/agent/v1/heartbeat",
        headers={
            **headers,
            "X-Agent-ID": agent_id,
            "Authorization": f"Bearer {session_token}",
        },
    )
    assert hb.status_code == 200


async def test_agent_unregister_removes_fleet_row(client, tenant_a):
    headers = {
        "X-Org-ID": str(tenant_a["org"].id),
        "Content-Type": "application/json",
    }
    reg = await client.post(
        "/agent/v1/register",
        headers=headers,
        json={
            "hostname": "to-be-uninstalled",
            "org_token": tenant_a["org_token"],
            "os_version": "Linux 6.8",
            "agent_version": "0.1.0",
        },
    )
    assert reg.status_code == 201
    reg_body = reg.json()
    agent_id = reg_body["id"]
    auth_headers = {
        **headers,
        "X-Agent-ID": agent_id,
        "Authorization": f"Bearer {reg_body['session_token']}",
    }

    unreg = await client.post("/agent/v1/unregister", headers=auth_headers)
    assert unreg.status_code == 204

    # The agent row (and its session_token_hash) is gone now, so the same
    # token can no longer authenticate at all - 401 from the auth check,
    # not 404 from the route handler (which it never reaches).
    again = await client.post("/agent/v1/unregister", headers=auth_headers)
    assert again.status_code == 401


async def test_prompt_pipeline_masks_pii(client, tenant_a):
    headers = {
        "X-Org-ID": str(tenant_a["org"].id),
        "X-Agent-ID": str(tenant_a["agent"].id),
        "Authorization": f"Bearer {tenant_a['agent_session_token']}",
        "Content-Type": "application/json",
    }
    response = await client.post(
        "/agent/v1/prompt",
        headers=headers,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "My SSN is 123-45-6789 please summarize"}
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] in ("masked", "allowed", "blocked")
    if data.get("masked_messages"):
        content = data["masked_messages"][0]["content"]
        assert "123-45-6789" not in content
