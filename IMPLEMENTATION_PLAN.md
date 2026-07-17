# AI-SPM SaaS Multi-Tenant — Implementation Plan

**Source of truth:** `IMPLEMENTATION_ROADMAP.md` (base product) + `IMPLEMENTATION_ROADMAP_SAAS_MULTI_TENANT.md` (SaaS architecture)  
**Timeline:** 16 weeks (SaaS MVP)  
**Architecture:** Modular monolith → microservices; K8s production; Docker Compose dev

---

## Current Status (Phase 1 In Progress)

| Component | Status |
|-----------|--------|
| TenantContext middleware | Done |
| PostgreSQL RLS + Alembic migration | Done (session role fix in progress) |
| Cross-tenant security test suite | Done (blocking CI) |
| Signup + tenant provisioning | Done |
| Platform admin API (no audit access) | Done |
| Quota middleware + Stripe webhook stub | Done |
| Agent registration + prompt pipeline (stubs) | Done |
| Docker Compose (PG, Redis, MinIO, API) | Done |
| K8s manifests + CI pipeline | Partial |
| Kong API gateway | In progress |
| Frontend admin + platform console | In progress |
| Rust endpoint agent (Windows + Linux) | In progress |
| Presidio PII / Guardrails threat engines | Phase 2–4 |
| mTLS cert provisioning | Phase 1–2 |

---

## Phase 1: Foundation + Tenant Core (Weeks 1–4)

**Goal:** Shared gateway, tenant isolation, signup, agent registration, audit logging, dev deployable stack.

### Tasks

| ID | Task | Module | Acceptance |
|----|------|--------|------------|
| P1-01 | Monorepo structure (backend, frontend, agent, deploy, docs) | All | All packages build |
| P1-02 | Docker Compose dev stack | deploy | `make up` → healthy services |
| P1-03 | PostgreSQL schema + RLS policies | backend | Alembic migrate; RLS tests pass |
| P1-04 | TenantContext middleware (JWT + mTLS headers) | backend/tenant | Every tenant route scoped |
| P1-05 | DB session hook (`SET ROLE` + `app.current_org_id`) | backend/tenant | Raw SQL cannot cross tenants |
| P1-06 | Cross-tenant security test suite (CI blocking) | backend/tests | 100% pass on every PR |
| P1-07 | POST /public/v1/signup + email verification | backend/public | Tenant live in <5 min |
| P1-08 | Admin JWT auth + RBAC permissions | backend/admin | Login returns org-scoped JWT |
| P1-09 | Agent registration + heartbeat APIs | backend/agent | Org token + mTLS headers |
| P1-10 | Prompt pipeline (policy → PII stub → audit) | backend/services | End-to-end prompt logged |
| P1-11 | OpenAI LLM adapter (org-scoped keys) | backend/infrastructure/llm | Proxy to OpenAI when key configured |
| P1-12 | Kong gateway (TLS, routing, rate limit, mTLS headers) | deploy/kong | Agent/admin routes to FastAPI |
| P1-13 | Correlation ID middleware + structured logging | backend | IDs propagate agent→gateway→core |
| P1-14 | mTLS CA + cert generation scripts | scripts | Dev certs for agent testing |
| P1-15 | Rust agent workspace scaffold (proxy + connector) | agent | Builds on Linux; Windows service stub |
| P1-16 | React admin dashboard scaffold (login, layout) | frontend | Enterprise SaaS UI shell |
| P1-17 | Platform admin console UI shell | frontend/platform | Tenant list, suspend |
| P1-18 | GitHub Actions CI (lint, security tests, build) | .github | Green on main |
| P1-19 | Developer setup documentation | docs | New dev productive in 30 min |

### Phase 1 Demo Criteria

- Self-service signup → verify email → admin login
- Agent registers with org token → appears in fleet API
- Prompt submitted → PII masked (regex stub) → audit event created
- Tenant A cannot see Tenant B data (API + RLS tests)
- Platform admin lists tenants, suspends tenant, cannot read audit

---

## Phase 2: Security Pipeline + Quotas (Weeks 5–8)

**Goal:** Production-grade PII masking, mTLS agent, Windows/Linux agents, quotas, suspension.

| ID | Task | Acceptance |
|----|------|------------|
| P2-01 | Presidio integration + CNIC custom recognizer | CNIC/SSN/card masked ≥0.7 confidence |
| P2-02 | Response PII leakage scan | Outbound scan before agent return |
| P2-03 | Guardrails threat engine (inbound) | Injection/jailbreak blocked |
| P2-04 | mTLS agent ↔ Kong (rustls + cert SAN org_id) | Only registered agents connect |
| P2-05 | Windows Service + Tauri tray (3 states) | Protected/Disconnected/Blocked |
| P2-06 | Linux agent daemon + systemd unit | Same proxy logic as Windows |
| P2-07 | ChatGPT + Claude domain interception | Test traffic captured |
| P2-08 | Block tray notifications | User notified on block |
| P2-09 | Redis tenant-prefixed policy cache | `tenant:{org_id}:policy:*` |
| P2-10 | Tenant suspension blocks agents + admins | 403 on all tenant routes |
| P2-11 | Quota enforcement (agents, prompts/day) | 429 when plan limit hit |
| P2-12 | PII + policy + auth integration tests | Full matrix in CI |

---

## Phase 3: Dashboard + Platform Admin + Billing (Weeks 9–12)

**Goal:** Full tenant admin UI, platform console, MSI installer, Stripe billing.

| ID | Task | Acceptance |
|----|------|------------|
| P3-01 | Dashboard metrics + security score API/UI | Real-time cards + charts |
| P3-02 | Agent fleet panel (online/offline/revoke) | WebSocket status updates |
| P3-03 | Policy CRUD UI + department rules | Policies enforced per dept |
| P3-04 | Audit log search + export (CSV) | Cursor pagination, tsvector search |
| P3-05 | Threat feed + WebSocket live updates | Real-time block/threat events |
| P3-06 | User/role management UI | RBAC-gated components |
| P3-07 | Platform admin console (full) | Suspend, usage, reset admin |
| P3-08 | Stripe subscriptions + webhooks | Plan upgrades change quotas |
| P3-09 | WiX MSI + universal org token install | Silent GPO deployment |
| P3-10 | Playwright E2E tests (all screens) | CI E2E green |

---

## Phase 4: Threat Detection + Go-Live (Weeks 13–16)

**Goal:** Production hardening, monitoring, GDPR, pen test, go-live.

| ID | Task | Acceptance |
|----|------|------------|
| P4-01 | Guardrails outbound response scan | Leakage blocked |
| P4-02 | Agent auto-updater (MSI via MinIO) | Silent update + rollback |
| P4-03 | Prometheus + Grafana dashboards | p95 latency, blocks, fleet |
| P4-04 | Production Docker Compose + K8s HPA | Multi-AZ deploy |
| P4-05 | k6 load test (50 tenants, 1000 agents) | p95 <300ms excl. LLM |
| P4-06 | OWASP ZAP + cross-tenant pen test | Zero isolation findings |
| P4-07 | GDPR tenant export + delete jobs | Data portability verified |
| P4-08 | Architecture + API + admin + GPO docs | Client review sign-off |
| P4-09 | MSI Authenticode signing | Code-signed agent |
| P4-10 | UAT + production go-live | All success criteria met |

---

## Architecture Summary

```
┌─────────────┐     mTLS      ┌──────────┐     ┌─────────────────────────────┐
│ Endpoint    │──────────────▶│ Kong     │────▶│ FastAPI Security Core       │
│ Agent       │               │ Gateway  │     │ TenantContext → RLS → PG    │
│ Win/Linux   │               └──────────┘     └─────────────────────────────┘
└─────────────┘                                        │
┌─────────────┐     JWT       ┌──────────┐            ├── Presidio (PII)
│ Admin SPA   │──────────────▶│ Kong     │────────────├── Guardrails (threat)
│ Platform UI │               └──────────┘            ├── Policy/RBAC engine
└─────────────┘                                        └── Audit (append-only)
```

### Tenant Isolation (Defense in Depth)

1. Auth: JWT `org_id` (admin) | mTLS SAN `org_id` (agent)
2. Middleware: `TenantContext` required on all tenant routes
3. API: Reject body `org_id` ≠ context (IDOR prevention)
4. Repository: All queries `WHERE org_id = context`
5. PostgreSQL RLS: `app.current_org_id` session variable

### API Namespaces

| Prefix | Auth | Scope |
|--------|------|-------|
| `/public/v1/*` | None | Signup, health |
| `/admin/v1/*` | Tenant JWT | Single org |
| `/agent/v1/*` | mTLS headers | Single org |
| `/platform/v1/*` | Platform JWT | Metadata only — no audit content |

---

## Test Strategy (Mandatory CI)

| Suite | Path | Blocks Release |
|-------|------|----------------|
| Cross-tenant API | `tests/security/test_cross_tenant_api.py` | Yes |
| PostgreSQL RLS | `tests/security/test_cross_tenant_rls.py` | Yes |
| Platform admin boundaries | `tests/security/test_platform_admin_boundaries.py` | Yes |
| Auth + RBAC | `tests/integration/test_auth.py` | Phase 2 |
| PII masking | `tests/unit/test_pii_engine.py` | Phase 2 |
| Policy enforcement | `tests/integration/test_policy.py` | Phase 3 |
| Agent registration | `tests/integration/test_agent.py` | Phase 1 |

---

## Repository Structure

```
AI-SPM/
├── backend/           # FastAPI security core
├── frontend/          # React tenant admin dashboard
├── frontend-platform/ # Platform admin console (or shared SPA routes)
├── agent/             # Rust endpoint agent workspace
├── deploy/            # Docker Compose, Kong, K8s, Prometheus
├── infrastructure/    # Kong plugins, postgres init, terraform
├── scripts/           # Certs, seed, benchmark
├── docs/              # Architecture, API, admin, GPO guides
└── .github/workflows/ # CI/CD
```

---

## Next Actions (Immediate)

1. Fix RLS session role (`SET ROLE aispm_app`) + NullPool in tests
2. Add Kong to Docker Compose with mTLS header forwarding
3. Scaffold React enterprise admin UI + platform console
4. Scaffold Rust agent workspace (Windows + Linux targets)
5. Add correlation ID middleware + OpenAI adapter
6. Expand CI to build frontend + agent
7. Complete developer setup guide
