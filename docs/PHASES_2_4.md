# AI-SPM Phases 2–4 Implementation Notes

## Phase 2: Security Pipeline ✅

| Component | Location |
|-----------|----------|
| Presidio PII engine (CNIC, SSN, card, email, phone) | `backend/src/ai_spm/infrastructure/presidio/adapter.py` |
| Guardrails threat engine (inbound + outbound) | `backend/src/ai_spm/infrastructure/guardrails/adapter.py` |
| Response PII leakage scan | `backend/src/ai_spm/services/prompt_pipeline.py` |
| Policy engine + Redis cache | `backend/src/ai_spm/services/policy_engine.py` |
| mTLS cert issuance | `backend/src/ai_spm/services/cert_service.py` |
| Agent offline detector job | `backend/src/ai_spm/jobs/scheduler.py` |
| Agent mTLS (rustls) | `agent/crates/agent-core/src/gateway/client.rs` |
| Linux systemd unit | `deploy/systemd/aispm-agent.service` |
| WiX MSI guide | `agent/installer/wix/README.md` |

Install ML dependencies (optional, uses regex fallback without):
```bash
pip install -e ".[ml]"
python -m spacy download en_core_web_sm
```

## Phase 3: Dashboard + Billing ✅

| Component | Location |
|-----------|----------|
| Dashboard metrics API | `GET /admin/v1/dashboard/metrics` |
| Threat feed API | `GET /admin/v1/dashboard/threats` |
| Policy CRUD | `POST/PUT/DELETE /admin/v1/policies` |
| Agent revoke | `POST /admin/v1/agents/{id}/revoke` |
| Audit export | `POST /admin/v1/audit/export` |
| User management | `GET/POST /admin/v1/users` |
| LLM config | `GET/POST /admin/v1/llm-configs` |
| WebSocket live feed | `WS /admin/v1/ws/dashboard?token=JWT` |
| Stripe webhooks | `POST /billing/webhooks/stripe` |
| Frontend pages | `frontend/src/pages/` (Dashboard, Threats, Settings, Policies) |

## Phase 4: Go-Live ✅

| Component | Location |
|-----------|----------|
| GDPR tenant export | `POST /admin/v1/gdpr/export` |
| GDPR tenant delete | `POST /admin/v1/gdpr/delete` |
| Agent auto-updater API | `GET /agent/v1/updates/check`, `GET /agent/v1/updates/{version}/download` |
| Prometheus metrics | `/metrics` |
| Grafana dashboard | `deploy/grafana/dashboards/ai-spm-overview.json` |
| Security test suite | `backend/tests/security/` (18 tests) |
| PII/threat/policy tests | `backend/tests/unit/`, `backend/tests/integration/` |

## Test Suite

```bash
cd backend && pytest tests/ -v   # 32+ tests
cd agent && cargo test --workspace
cd frontend && npm run build
```

## Production Checklist

- [ ] Set `JWT_SECRET_KEY`, `PLATFORM_JWT_SECRET_KEY` via Vault
- [ ] Enable Stripe: `STRIPE_ENABLED=true`
- [ ] Install Presidio + spaCy models on gateway nodes
- [ ] Configure Kong mTLS with platform CA
- [ ] Code-sign MSI with Authenticode certificate
- [ ] Run cross-tenant pen test before go-live
