# Sprint 1 Demo — Core Gateway & SaaS

Exit criteria: **signup → verify → admin login → agent register → inspect prompt → audit**; cross-tenant isolation via `make test-security`.

## Prerequisites

```bash
make up          # Postgres, Redis, API, Kong (:8090), …
# API container runs alembic + seed_platform_admin + seed_dev_tenant
```

Or local API:

```bash
make migrate && make seed
make backend-dev   # :8000 — then AISPM_BASE_URL=http://localhost:8000 make demo-sprint1
```

## One-shot script

```bash
make demo-sprint1
# or: AISPM_BASE_URL=http://localhost:8090 ./scripts/demo-sprint1.sh
```

## Manual curl (Kong on 8090)

1. `POST /public/v1/signup` — response includes `verification_token` (non-production).
2. `GET /public/v1/verify-email?token=…` — response includes **`org_token` once**.
3. `POST /admin/v1/auth/login` — JWT.
4. `POST /agent/v1/register` with `X-Org-ID` + body `org_token` — response includes a **per-agent `session_token` once** (store it, like `org_token`).
5. `POST /agent/v1/prompt` with `inspect_only: true` + `X-Org-ID` / `X-Agent-ID` + `Authorization: Bearer <session_token>`. Every `/agent/v1/*` call other than `/register` requires the session token — bare `X-Org-ID`/`X-Agent-ID` alone is not sufficient (closes a header-forgery gap; see `tenant/middleware.py::_verify_agent_session_token`).
6. `GET /admin/v1/audit` with Bearer JWT.

## Dev tenant (no signup)

`make seed` / Compose start creates:

- Admin: `admin@devcorp.io` / `DevAdminPass123!`
- Fixed `AISPM_ORG_TOKEN` printed by `seed_dev_tenant.py`
- Platform: `platform-admin@aispm.io` (see README)

## Ops

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness |
| `GET /ready` | Postgres readiness (also via Kong) |
