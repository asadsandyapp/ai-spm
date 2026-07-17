"""Platform admin boundary tests — no customer audit content access."""

from ai_spm.infrastructure.auth.password import create_platform_access_token


async def test_platform_admin_can_list_tenants(client, platform_admin, tenant_a, tenant_b):
    response = await client.get(
        "/platform/v1/tenants",
        headers={"Authorization": f"Bearer {platform_admin['token']}"},
    )
    assert response.status_code == 200
    tenants = response.json()
    slugs = {t["slug"] for t in tenants}
    assert "acme-corp" in slugs
    assert "beta-inc" in slugs


async def test_platform_admin_can_suspend_tenant(client, platform_admin, tenant_b, db_session):
    response = await client.post(
        f"/platform/v1/tenants/{tenant_b['org'].id}/suspend",
        headers={"Authorization": f"Bearer {platform_admin['token']}"},
        json={"reason": "Non-payment test"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"


async def test_platform_admin_can_activate_tenant(client, platform_admin, tenant_b):
    await client.post(
        f"/platform/v1/tenants/{tenant_b['org'].id}/suspend",
        headers={"Authorization": f"Bearer {platform_admin['token']}"},
        json={"reason": "Test suspend"},
    )
    response = await client.post(
        f"/platform/v1/tenants/{tenant_b['org'].id}/activate",
        headers={"Authorization": f"Bearer {platform_admin['token']}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"


async def test_platform_jwt_cannot_access_admin_audit(client, platform_admin, tenant_a):
    """Platform JWT must not work on tenant admin endpoints."""
    response = await client.get(
        "/admin/v1/audit",
        headers={"Authorization": f"Bearer {platform_admin['token']}"},
    )
    assert response.status_code == 401


async def test_tenant_admin_jwt_cannot_access_platform_api(client, tenant_a):
    response = await client.get(
        "/platform/v1/tenants",
        headers={"Authorization": f"Bearer {tenant_a['token']}"},
    )
    assert response.status_code == 401


async def test_platform_admin_usage_metadata_only(client, platform_admin, tenant_a):
    response = await client.get(
        f"/platform/v1/tenants/{tenant_a['org'].id}/usage",
        headers={"Authorization": f"Bearer {platform_admin['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "agent_count" in data
    assert "prompts_today" in data
    assert "masked_content" not in data
    assert "audit" not in data
