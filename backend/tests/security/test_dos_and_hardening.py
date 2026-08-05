"""Regression tests for the second hardening pass: oversized-body DoS,
world-readable key material, the quota lost-update race, /web-audit rate
limiting, and the topic-blocklist truncation bypass."""

import asyncio
import os
import stat
import uuid
from datetime import UTC, datetime

import pytest


def _agent_headers(tenant: dict) -> dict:
    return {
        "X-Org-ID": str(tenant["org"].id),
        "X-Agent-ID": str(tenant["agent"].id),
        "Authorization": f"Bearer {tenant['agent_session_token']}",
        "Content-Type": "application/json",
    }


async def test_oversized_prompt_body_rejected(client, tenant_a):
    big_content = "x" * (300 * 1024)  # over the 256 KiB limit
    response = await client.post(
        "/agent/v1/prompt",
        headers=_agent_headers(tenant_a),
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": big_content}],
        },
    )
    assert response.status_code == 413


async def test_prompt_body_within_limit_still_works(client, tenant_a):
    response = await client.post(
        "/agent/v1/prompt",
        headers=_agent_headers(tenant_a),
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200


async def test_padded_prefix_no_longer_bypasses_topic_blocklist(client, tenant_a):
    from ai_spm.domain.models import Policy
    from ai_spm.infrastructure.db.session import get_platform_session

    # tenant_a doesn't seed a Policy row by default - policy_engine.evaluate
    # returns (True, None) with no policies at all, so one must exist here
    # for the blocklist check to ever run. get_platform_session (not the
    # RLS-restricted db_session fixture) matches how test_suspended_tenant_blocked
    # already mutates a tenant-scoped row from outside a request's own RLS context.
    async with get_platform_session() as session:
        session.add(
            Policy(
                org_id=tenant_a["org"].id,
                name="Blocklist Test Policy",
                rules={"topics": {"blocked": ["project falcon"]}},
                is_default=True,
                is_active=True,
            )
        )
        await session.commit()

    padded = "x" * 250 + " project falcon details"
    response = await client.post(
        "/agent/v1/prompt",
        headers=_agent_headers(tenant_a),
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": padded}],
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "blocked"


async def test_web_audit_rate_limited_once_quota_exhausted(client, tenant_a):
    from ai_spm.domain.models import Subscription
    from ai_spm.infrastructure.db.session import get_platform_session
    from sqlalchemy import select

    async with get_platform_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.org_id == tenant_a["org"].id)
        )
        sub = result.scalar_one()
        sub.max_prompts_per_day = 0
        await session.commit()

    response = await client.post(
        "/agent/v1/web-audit",
        headers=_agent_headers(tenant_a),
        json={
            "provider": "openai",
            "masked_content": "hello",
            "pii_entities": [],
            "pii_hit_count": 0,
        },
    )
    assert response.status_code == 429


async def test_increment_prompt_usage_has_no_lost_update_under_concurrency(tenant_a):
    from ai_spm.domain.models import UsageDaily
    from ai_spm.infrastructure.db.session import get_platform_session
    from ai_spm.tenant.quota import increment_prompt_usage
    from sqlalchemy import select

    org_id = tenant_a["org"].id
    await asyncio.gather(*(increment_prompt_usage(org_id) for _ in range(10)))

    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_platform_session() as session:
        result = await session.execute(
            select(UsageDaily.prompts_count).where(
                UsageDaily.org_id == org_id, UsageDaily.usage_date == today
            )
        )
        assert result.scalar_one() == 10


def test_ca_and_issued_keys_are_owner_only(tmp_path):
    from ai_spm.services.cert_service import CertService

    if os.name == "nt":
        pytest.skip("POSIX file mode bits aren't meaningful on Windows")

    service = CertService(certs_dir=tmp_path)
    ca_crt, ca_key = service.ensure_ca()
    assert stat.S_IMODE(os.stat(ca_key).st_mode) == 0o600

    info = service.issue_agent_cert(uuid.uuid4(), uuid.uuid4())
    issued_key = tmp_path / "issued" / [
        p.name for p in (tmp_path / "issued").iterdir() if p.suffix == ".key"
    ][0]
    assert stat.S_IMODE(os.stat(issued_key).st_mode) == 0o600
    assert info["private_key_pem"]
