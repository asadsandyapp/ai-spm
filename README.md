# AI-SPM — SaaS Multi-Tenant Platform

Enterprise AI Security Posture Management platform with strict tenant isolation, self-service provisioning, platform admin console, and subscription billing.

## Architecture

Defense-in-depth tenant isolation:

1. **Auth layer** — JWT `org_id` (admin) or mTLS SAN `org_id` (agent)
2. **Middleware** — `TenantContext` on every request
3. **API validation** — Reject `org_id` body mismatch (IDOR prevention)
4. **Repository** — All queries scoped by `org_id`
5. **PostgreSQL RLS** — `app.current_org_id` session variable

## Quick Start

```bash
# Start infrastructure + API
cd deploy
docker compose up -d

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Default Platform Admin

After first boot: `platform-admin@aispm.io` / `PlatformAdmin123!`

## API Namespaces

| Namespace | Auth | Purpose |
|-----------|------|---------|
| `/public/v1/*` | None | Signup, email verification |
| `/admin/v1/*` | JWT with `org_id` | Tenant admin dashboard |
| `/agent/v1/*` | mTLS headers (`X-Org-ID`) | Endpoint agent |
| `/platform/v1/*` | Platform JWT | Vendor ops (no audit content) |

## Self-Service Signup

```bash
curl -X POST http://localhost:8000/public/v1/signup \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corporation",
    "admin_email": "admin@acme.com",
    "admin_password": "SecurePass123!",
    "admin_full_name": "Jane Security"
  }'
```

## Development

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env

# Run migrations
alembic upgrade head
python scripts/seed_platform_admin.py

# Start API
uvicorn ai_spm.main:app --reload --app-dir src

# Run security test suite (blocking CI)
pytest tests/security/ -v
```

## Project Structure

```
backend/src/ai_spm/
├── tenant/          # TenantContext, middleware, RLS, quotas
├── platform/        # Platform admin API + provisioning
├── billing/         # Stripe webhooks + subscriptions
├── admin/           # Tenant-scoped admin API
├── agent/           # Agent registration + prompt pipeline
├── public/          # Signup + verification
└── services/        # Policy, PII, threat engines

deploy/
├── docker-compose.yml
└── k8s/             # Production K8s manifests with HPA
```

## Security Test Suite

Mandatory CI tests per `REQ-SaaS-004`:

- `test_cross_tenant_api.py` — API-level isolation
- `test_cross_tenant_rls.py` — PostgreSQL RLS enforcement
- `test_platform_admin_boundaries.py` — Platform admin cannot read audit

## Production Deployment

Kubernetes manifests in `deploy/k8s/` with HPA (3–20 replicas). Configure secrets via `aispm-secrets` Secret.

## Roadmap Alignment

See `IMPLEMENTATION_PLAN.md` for the full 16-week phased delivery plan.

**Phase 1:** ✅ Complete  
**Phase 2:** ✅ Security pipeline (Presidio, Guardrails, mTLS, agent, policy cache)  
**Phase 3:** ✅ Dashboard, platform admin, billing, full admin API + UI  
**Phase 4:** ✅ GDPR, agent updater, monitoring, test suite  

See `docs/PHASES_2_4.md` for component map.

## Endpoint Agent + HTTPS MITM

The Rust agent registers with the gateway and runs a local MITM proxy for AI provider traffic (ChatGPT, OpenAI API, Claude, Gemini). See [Developer Setup — HTTPS MITM](docs/DEVELOPER_SETUP.md#https-mitm-chatgpt--openai-pii-masking) for full instructions.

**One-shot install (Linux desktop):** builds the agent, installs dependencies, trusts the MITM CA in the system + browser stores, configures the desktop proxy, and starts the agent — no manual browser setup.

```bash
sudo ./scripts/install-agent.sh          # install + trust CA + set proxy + start
sudo ./scripts/install-agent.sh stop     # stop agent and reset system proxy
```

Config via env vars (dev defaults shown): `AISPM_GATEWAY_URL=http://localhost:8090`, `AISPM_ORG_ID`, `AISPM_ORG_TOKEN`, `AISPM_PROXY_LISTEN=127.0.0.1:8081`.

Manual run (advanced):

```bash
export AISPM_GATEWAY_URL="http://localhost:8090"
export AISPM_ORG_ID="<org-uuid>"
export AISPM_ORG_TOKEN="<org-token>"
cd agent && cargo run --release -p agent-service
```

## License

Proprietary — AI-SPM Platform
