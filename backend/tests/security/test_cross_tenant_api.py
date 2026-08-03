"""Cross-tenant API isolation tests — blocking CI criterion per REQ-SaaS-004."""

import uuid


async def test_admin_audit_scoped_to_own_tenant(client, tenant_a, tenant_b):
    response = await client.get(
        "/admin/v1/audit",
        headers={"Authorization": f"Bearer {tenant_a['token']}"},
    )
    assert response.status_code == 200
    events = response.json()
    assert all("Beta" not in (e.get("masked_content") or "") for e in events)
    acme_contents = [e.get("masked_content") for e in events]
    assert any("Acme" in (c or "") for c in acme_contents)


async def test_tenant_b_cannot_see_tenant_a_audit(client, tenant_a, tenant_b):
    response = await client.get(
        "/admin/v1/audit",
        headers={"Authorization": f"Bearer {tenant_b['token']}"},
    )
    assert response.status_code == 200
    events = response.json()
    for event in events:
        content = event.get("masked_content") or ""
        assert "Acme" not in content


async def test_admin_cannot_access_other_org_agent(client, tenant_a, tenant_b):
    response = await client.get(
        "/admin/v1/agents",
        headers={"Authorization": f"Bearer {tenant_a['token']}"},
    )
    assert response.status_code == 200
    agents = response.json()
    agent_ids = {a["id"] for a in agents}
    assert str(tenant_b["agent"].id) not in agent_ids
    assert str(tenant_a["agent"].id) in agent_ids


async def test_org_id_body_mismatch_rejected(client, tenant_a, tenant_b):
    response = await client.post(
        "/agent/v1/prompt",
        headers={
            "X-Org-ID": str(tenant_a["org"].id),
            "X-Agent-ID": str(tenant_a["agent"].id),
            "Authorization": f"Bearer {tenant_a['agent_session_token']}",
            "Content-Type": "application/json",
        },
        json={
            "org_id": str(tenant_b["org"].id),
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 403
    assert "org_id mismatch" in response.json()["detail"]


async def test_agent_session_token_required(client, tenant_a):
    """Closes the header-forgery gap: X-Org-ID/X-Agent-ID alone, with no
    bearer token at all, must not be enough to authenticate."""
    response = await client.post(
        "/agent/v1/prompt",
        headers={
            "X-Org-ID": str(tenant_a["org"].id),
            "X-Agent-ID": str(tenant_a["agent"].id),
            "Content-Type": "application/json",
        },
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 401


async def test_agent_cannot_use_another_agents_session_token(client, tenant_a, tenant_b):
    """A stolen/guessed org+agent UUID pair is not enough on its own, and
    a *different* agent's real token doesn't transfer either - the token
    must actually hash-match the specific agent named in the headers."""
    response = await client.post(
        "/agent/v1/prompt",
        headers={
            "X-Org-ID": str(tenant_a["org"].id),
            "X-Agent-ID": str(tenant_a["agent"].id),
            "Authorization": f"Bearer {tenant_b['agent_session_token']}",
            "Content-Type": "application/json",
        },
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 401


async def test_revoked_agent_rejected(client, tenant_a, db_session):
    """A revoked agent must be rejected on every endpoint, not just
    heartbeat - even with its own genuinely-correct session token."""
    from ai_spm.domain.enums import AgentStatus
    from ai_spm.domain.models import Agent
    from ai_spm.infrastructure.db.session import get_platform_session
    from sqlalchemy import select

    async with get_platform_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == tenant_a["agent"].id))
        agent = result.scalar_one()
        agent.status = AgentStatus.REVOKED
        await session.commit()

    response = await client.post(
        "/agent/v1/prompt",
        headers={
            "X-Org-ID": str(tenant_a["org"].id),
            "X-Agent-ID": str(tenant_a["agent"].id),
            "Authorization": f"Bearer {tenant_a['agent_session_token']}",
            "Content-Type": "application/json",
        },
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 401


async def test_agent_wrong_org_token_rejected(client, tenant_a, tenant_b):
    response = await client.post(
        "/agent/v1/register",
        headers={
            "X-Org-ID": str(tenant_a["org"].id),
            "Content-Type": "application/json",
        },
        json={
            "hostname": "evil-host",
            "org_token": tenant_b["org_token"],
        },
    )
    assert response.status_code == 403


async def test_suspended_tenant_blocked(client, tenant_a, db_session):
    from ai_spm.domain.enums import OrganizationStatus
    from ai_spm.domain.models import Organization
    from ai_spm.infrastructure.db.session import get_platform_session
    from sqlalchemy import select

    async with get_platform_session() as session:
        result = await session.execute(
            select(Organization).where(Organization.id == tenant_a["org"].id)
        )
        org = result.scalar_one()
        org.status = OrganizationStatus.SUSPENDED
        await session.commit()

    response = await client.get(
        "/admin/v1/agents",
        headers={"Authorization": f"Bearer {tenant_a['token']}"},
    )
    assert response.status_code == 403
    assert "suspended" in response.json()["detail"].lower()


async def test_unauthenticated_admin_rejected(client):
    response = await client.get("/admin/v1/audit")
    assert response.status_code == 401


async def test_unauthenticated_agent_rejected(client):
    response = await client.post(
        "/agent/v1/prompt",
        json={"messages": [{"role": "user", "content": "test"}]},
    )
    assert response.status_code == 401
