# AI-SPM Developer Setup Guide

Enterprise SaaS multi-tenant AI Security Posture Management platform.

## Prerequisites

| Tool | Version |
|------|---------|
| Docker + Compose | 24+ |
| Python | 3.12+ |
| Node.js | 20+ |
| Rust | 1.78+ (for agent) |
| PostgreSQL | 16 (via Docker) |
| Redis | 7 (via Docker) |

## Quick Start (Full Stack)

```bash
# Clone and start infrastructure
cd AI-SPM
make up

# Services
# - Kong API Gateway:  http://localhost:8080
# - FastAPI (direct):  http://localhost:8000 (internal)
# - Admin Dashboard:   http://localhost:3000
# - Grafana:           http://localhost:3001 (admin/admin)
# - Prometheus:        http://localhost:9090
# - MinIO Console:     http://localhost:9001
```

### Default Credentials

| Console | Email | Password |
|---------|-------|----------|
| Platform Admin | `platform-admin@aispm.io` | `PlatformAdmin123!` |

Tenant admins are created via self-service signup.

## Backend Development

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# Start PostgreSQL + Redis (or use make up)
docker compose -f ../deploy/docker-compose.yml up -d postgres redis

# Migrate and seed
alembic upgrade head
python scripts/seed_platform_admin.py

# Run API
uvicorn ai_spm.main:app --reload --app-dir src --port 8000
```

API docs: http://localhost:8000/docs

### Security Test Suite (Mandatory CI)

```bash
pytest tests/security/ -v
```

All 18 cross-tenant isolation tests must pass before merge.

## Frontend Development

```bash
cd frontend
npm install
cp .env.example .env
npm run dev   # http://localhost:5173
```

Set `VITE_API_URL=http://localhost:8080` to route through Kong.

## Agent Development

```bash
cd agent
cargo build --workspace
cargo test --workspace

export AISPM_GATEWAY_URL="http://localhost:8080"
export AISPM_ORG_TOKEN="<org-token-from-signup>"
export AISPM_ORG_ID="<org-uuid>"

cargo run -p agent-service
```

Generate dev mTLS certificates:

```bash
make certs ORG_ID=<uuid> AGENT_ID=<uuid>
```

### HTTPS MITM (ChatGPT / OpenAI PII masking)

The agent runs a local HTTPS MITM proxy that decrypts traffic to AI providers, scans prompts via `/agent/v1/prompt?inspect_only`, and forwards masked or blocked requests upstream.

**1. Start the stack**

```bash
make up   # or docker compose -f deploy/docker-compose.yml up -d
```

**2. One-shot install (recommended)**

The installer handles everything with a single command: installs dependencies (`libnss3-tools`), builds the agent, installs the MITM CA into the system and browser (NSS) trust stores, configures the GNOME desktop proxy, and starts the agent.

```bash
sudo ./scripts/install-agent.sh          # install + trust CA + set proxy + start
sudo ./scripts/install-agent.sh stop     # stop agent and reset system proxy
```

Override config via env vars (dev defaults applied otherwise):

```bash
sudo AISPM_GATEWAY_URL="http://localhost:8090" \
     AISPM_ORG_ID="<your-org-uuid>" \
     AISPM_ORG_TOKEN="<your-org-token>" \
     AISPM_PROXY_LISTEN="127.0.0.1:8081" \
     ./scripts/install-agent.sh
```

The script must be run via `sudo` from your normal user (not as root directly) so per-user browser/proxy setup applies to your desktop session. Config is written to `/etc/ai-spm/agent.env`; logs go to `~/.local/share/ai-spm/agent.log`.

**Manual run (advanced)**

Startup auto-generates the MITM CA, attempts trust-store installation, and configures the GNOME proxy. Non-AI HTTPS traffic is tunneled unchanged so system-wide proxy mode does not break browsing. Running as a normal user cannot write the system trust store; use the installer above or run with privileges.

```bash
export AISPM_GATEWAY_URL="http://localhost:8090"
export AISPM_ORG_ID="<your-org-uuid>"
export AISPM_ORG_TOKEN="<your-org-token>"
export AISPM_PROXY_LISTEN="127.0.0.1:8081"

cd agent && cargo run --release -p agent-service
```

**3. Test**

Open ChatGPT and send a message containing an email address. The agent intercepts `CONNECT chat.openai.com:443`, terminates TLS, parses the conversation JSON, and sends masked content upstream (e.g. `***@***.com`).

Intercepted domains: `chat.openai.com`, `chatgpt.com`, `api.openai.com`, `claude.ai`, `api.anthropic.com`, `gemini.google.com`, `generativelanguage.googleapis.com`.

**Environment variables**

| Variable | Default | Purpose |
|----------|---------|---------|
| `AISPM_PROXY_LISTEN` | `127.0.0.1:8081` | MITM proxy bind address |
| `AISPM_MITM_CA_DIR` | `~/.local/share/ai-spm/mitm` | Root CA + leaf cert storage |
| `AISPM_AUTO_CONFIGURE_ENDPOINT` | `true` | Enable CA/proxy auto setup |
| `AISPM_AUTO_INSTALL_CA` | inherits endpoint setting | Install MITM CA into supported trust stores |
| `AISPM_AUTO_CONFIGURE_PROXY` | inherits endpoint setting | Configure supported OS proxy settings |

## Self-Service Signup Flow

```bash
curl -X POST http://localhost:8080/public/v1/signup \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corporation",
    "admin_email": "admin@acme.com",
    "admin_password": "SecurePass123!",
    "admin_full_name": "Jane Security"
  }'
```

Verify email via token from logs (dev mode prints verification link).

## Architecture

See `IMPLEMENTATION_PLAN.md` for phased delivery plan.

### Tenant Isolation (5 Layers)

1. JWT `org_id` (admin) / mTLS SAN `org_id` (agent)
2. `TenantContext` middleware
3. API body `org_id` validation (IDOR prevention)
4. Repository queries scoped by `org_id`
5. PostgreSQL RLS via `SET ROLE aispm_app` + `app.current_org_id`

## Project Structure

```
AI-SPM/
├── backend/     FastAPI security core
├── frontend/    React admin + platform console
├── agent/       Rust endpoint agent (Windows + Linux)
├── deploy/      Docker Compose, Kong, K8s, Prometheus
├── scripts/     Cert generation, utilities
└── docs/        Documentation
```

## CI/CD

GitHub Actions runs on every PR:
- Cross-tenant security test suite (blocking)
- Ruff lint
- Frontend type-check + build (when configured)
- Agent `cargo test`

## Troubleshooting

**RLS tests fail:** Ensure PostgreSQL 16 is running and `aispm_app` role exists (`alembic upgrade head`).

**Redis connection errors:** Start Redis or set `REDIS_URL=redis://localhost:6379/0`.

**Kong 502:** Wait for API health check; verify `docker compose logs api`.
