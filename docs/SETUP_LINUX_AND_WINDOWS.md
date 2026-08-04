# AI-SPM — Complete Setup Guide (Linux & Windows)

Step-by-step instructions to run the **full platform** (backend, frontend, gateway) and the **endpoint agent** on Linux and Windows.

For architecture and coding rules, see [AGENTS.md](../AGENTS.md). For day-to-day backend/frontend development shortcuts, see [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md).

---

## Table of contents

1. [What you are setting up](#1-what-you-are-setting-up)
2. [Prerequisites](#2-prerequisites)
3. [Clone the repository](#3-clone-the-repository)
4. [Option A — Full stack with Docker (recommended)](#4-option-a--full-stack-with-docker-recommended)
5. [Option B — Native development (backend + frontend)](#5-option-b--native-development-backend--frontend)
6. [Create a tenant and log in](#6-create-a-tenant-and-log-in)
7. [Endpoint agent — Linux](#7-endpoint-agent--linux)
8. [Endpoint agent — Windows](#8-endpoint-agent--windows)
9. [Verify the installation](#9-verify-the-installation)
10. [Ports reference](#10-ports-reference)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. What you are setting up

AI-SPM has two layers:

| Layer | Purpose | Where it runs |
|-------|---------|---------------|
| **Platform** | FastAPI gateway, admin UI, Postgres, Redis, Kong | Your dev machine or server (Docker or native) |
| **Endpoint agent** | Intercepts AI traffic on employee PCs, masks PII, audits to gateway | Linux desktop / Windows workstation |

**Traffic paths (enterprise):**

- **LLM API hosts** (`api.openai.com`, `api.anthropic.com`, …) → Rust agent transparent MITM (`:9443`)
- **Web UIs** (`chatgpt.com`, `claude.ai`, `gemini.google.com`) → mitmproxy on `127.0.0.1:8800` + system HTTPS proxy

---

## 2. Prerequisites

### All platforms (platform stack)

| Tool | Version | Notes |
|------|---------|-------|
| Git | 2.40+ | Clone the repo |
| Docker | 24+ | Engine + Compose plugin |
| Docker Compose | v2 | `docker compose version` |

### Optional — native backend/frontend dev

| Tool | Version | Linux install hint | Windows install hint |
|------|---------|-------------------|---------------------|
| Python | 3.12+ | `sudo apt install python3.12 python3.12-venv` | [python.org](https://www.python.org/downloads/) — check “Add to PATH” |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) or `nvm` | [nodejs.org](https://nodejs.org/) or `nvm-windows` |
| Rust | 1.78+ | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` | [rustup.rs](https://rustup.rs/) — MSVC toolchain |
| Make | any | Usually preinstalled | Use WSL2, Git Bash, or run commands manually |

### Linux only — endpoint agent (full install)

| Package | Purpose |
|---------|---------|
| `build-essential`, `pkg-config`, `libssl-dev` | Build Rust agent |
| `iptables`, `ip6tables` | Transparent API MITM |
| `libnss3-tools` | Trust MITM CA in Firefox/Chrome (NSS) |
| `python3`, `python3-venv` | mitmproxy web UI service |
| `curl`, `ca-certificates` | Installer dependencies |

Ubuntu/Debian one-liner:

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin \
  build-essential pkg-config libssl-dev libnss3-tools \
  python3 python3-venv curl ca-certificates iptables ip6tables
sudo usermod -aG docker "$USER"
# Log out and back in so the docker group applies
```

### Windows only — endpoint agent build

| Tool | Purpose |
|------|---------|
| [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/) | C++ workload (MSVC) |
| Rust (MSVC toolchain) | `rustup default stable-msvc` |
| [WiX Toolset v4+](https://wixtoolset.org/) | Optional — build MSI installer |

**Recommended on Windows:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with **WSL2 backend** for the platform stack. Use PowerShell or Windows Terminal for commands below.

---

## 3. Clone the repository

### Linux

```bash
git clone <your-repo-url> AI-SPM
cd AI-SPM
```

### Windows (PowerShell)

```powershell
git clone <your-repo-url> AI-SPM
cd AI-SPM
```

---

## 4. Option A — Full stack with Docker (recommended)

This starts Postgres, Redis, FastAPI, Kong, Prometheus, Grafana, and the production-built admin dashboard.

### Step 1 — Start services

**Linux (with Make):**

```bash
cd AI-SPM
make up
```

**Linux / Windows (without Make):**

```bash
cd AI-SPM
docker compose -f deploy/docker-compose.yml up -d
```

First boot runs migrations and seeds:

- Platform admin: `platform-admin@aispm.io` / `PlatformAdmin123!`
- Dev tenant admin: `admin@devcorp.io` / `DevAdminPass123!`
- Dev org token (for agent): `dev-org-token-please-change-32chars-minimum`

To rebuild images after code changes:

```bash
docker compose -f deploy/docker-compose.yml build --network=host
docker compose -f deploy/docker-compose.yml up -d
```

### Step 2 — Wait for health

```bash
curl -s http://localhost:8090/health
curl -s http://localhost:8090/ready
```

Both should return HTTP 200.

### Step 3 — Open the UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| Admin dashboard (Docker) | http://localhost:3000 | Dev tenant or your signup user |
| Kong API gateway | http://localhost:8090 | — |
| API docs (via Kong) | http://localhost:8090/docs | — |
| Grafana | http://localhost:3001 | `admin` / `admin` |
| Prometheus | http://localhost:9090 | — |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |

### Step 4 — Stop the stack

```bash
make down
# or
docker compose -f deploy/docker-compose.yml down
```

### View logs

```bash
docker compose -f deploy/docker-compose.yml logs -f api
```

---

## 5. Option B — Native development (backend + frontend)

Use this when you want hot reload on API and Vite dev server. You still need Postgres and Redis (from Docker or installed locally).

### Step 1 — Start infrastructure only

```bash
cd AI-SPM
docker compose -f deploy/docker-compose.yml up -d postgres redis
```

> **Redis port:** Compose maps Redis to host **6380** (not 6379). Use that in your local `.env`.

### Step 2 — Backend setup

**Linux:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Edit `backend/.env` — minimum for local dev with Docker infra:

```ini
DATABASE_URL=postgresql+asyncpg://aispm:aispm@localhost:5432/aispm
REDIS_URL=redis://localhost:6380/0
AISPM_PUBLIC_GATEWAY_URL=http://localhost:8090
APP_BASE_URL=http://localhost:5173
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

Optional ML scanners (Presidio, Guardrails):

```bash
pip install -e ".[dev,ml]"
python -m spacy download en_core_web_sm
```

### Step 3 — Migrate and seed

```bash
cd backend
# activate venv first
alembic upgrade head
python scripts/seed_platform_admin.py
python scripts/seed_dev_tenant.py
```

`seed_dev_tenant.py` prints `AISPM_ORG_ID` and `AISPM_ORG_TOKEN` — save these for the agent.

### Step 4 — Run the API

```bash
uvicorn ai_spm.main:app --reload --app-dir src --port 8000
```

- Direct API: http://localhost:8000/docs  
- For Kong routing, also start the `kong` service from Compose and point the frontend at `:8090`.

**Linux shortcut:**

```bash
make migrate && make seed && make backend-dev
```

### Step 5 — Frontend setup

**Linux:**

```bash
cd frontend
npm install
cp .env.example .env
```

**Windows:**

```powershell
cd frontend
npm install
copy .env.example .env
```

Edit `frontend/.env`:

```ini
VITE_API_URL=http://localhost:8090
```

Use `http://localhost:8000` only if you are **not** using Kong.

**Run dev server:**

```bash
npm run dev
```

Open http://localhost:5173

### Step 6 — Run tests

```bash
cd backend
pytest tests/security/ -v    # mandatory cross-tenant tests
pytest -v                    # full unit/integration suite
```

```bash
cd frontend
npm run build
```

```bash
cd agent
cargo test --workspace
```

---

## 6. Create a tenant and log in

### Option 1 — Use the seeded dev tenant (fastest)

After `make up` or `make seed`:

| Field | Value |
|-------|-------|
| Admin email | `admin@devcorp.io` |
| Admin password | `DevAdminPass123!` |
| Org token | `dev-org-token-please-change-32chars-minimum` |

Org UUID is printed by `seed_dev_tenant.py` (installer default: `2117eef6-a519-47d5-bd6b-8a7357dafbb7` when using dev seed).

### Option 2 — Self-service signup

```bash
curl -X POST http://localhost:8090/public/v1/signup \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corporation",
    "admin_email": "admin@acme.com",
    "admin_password": "SecurePass123!",
    "admin_full_name": "Jane Security"
  }'
```

In development, the response may include a `verification_token`. Verify:

```bash
curl "http://localhost:8090/public/v1/verify-email?token=<verification_token>"
```

The verify response includes **`org_token` once** — store it securely.

### Platform admin console

1. Go to http://localhost:5173/platform/login (or `:3000` if using Docker dashboard).
2. Log in as `platform-admin@aispm.io` / `PlatformAdmin123!`
3. View tenant metadata (platform users cannot read audit bodies).

### Tenant admin console

1. Go to http://localhost:5173/login
2. Log in with your tenant admin credentials
3. Use **Agents → Download Agent** to get a sealed Linux `.run` installer bound to your org (production path)

---

## 7. Endpoint agent — Linux

The installer configures:

- Rust agent as `ai-spm-agent` systemd service
- Transparent MITM for LLM API hosts (iptables → `:9443`)
- mitmproxy for ChatGPT / Claude / Gemini web UIs (`127.0.0.1:8800`)
- MITM CA trust in system + browser stores
- Desktop HTTPS proxy (GNOME; Firefox policies for snap/classic)

### Step 1 — Ensure the gateway is running

```bash
curl -s http://localhost:8090/health
```

### Step 2 — One-shot install (recommended)

Run from your **normal user** via `sudo` (not as root login):

```bash
cd AI-SPM
sudo ./scripts/install-agent.sh
```

Override defaults if needed:

```bash
sudo AISPM_GATEWAY_URL="http://localhost:8090" \
     AISPM_ORG_ID="<your-org-uuid>" \
     AISPM_ORG_TOKEN="<your-org-token>" \
     ./scripts/install-agent.sh
```

If you have an enrollment package from the admin console:

```bash
chmod +x aispm-agent-linux-*.run
./aispm-agent-linux-*.run
```

### Step 3 — Restart browsers

Fully quit Chrome, Firefox, and Edge, then reopen so they pick up the new CA and proxy settings.

### Step 4 — Check agent status

```bash
sudo systemctl status ai-spm-agent
sudo systemctl status ai-spm-web-mitm
sudo journalctl -u ai-spm-agent -f
```

Config: `/etc/ai-spm/agent.env`  
Logs: `/var/log/ai-spm/agent.log`

### Step 5 — Test masking

1. Open https://chatgpt.com (or claude.ai / gemini.google.com)
2. Send a message containing an email address
3. In the admin UI, check **Threats** or **Audit** for the event

### Agent management commands

```bash
sudo ./scripts/install-agent.sh stop        # stop agent + reset proxy
sudo ./scripts/install-agent.sh uninstall   # full removal
sudo systemctl restart ai-spm-agent
```

### Manual run (advanced, no systemd)

```bash
export AISPM_GATEWAY_URL="http://localhost:8090"
export AISPM_ORG_ID="<org-uuid>"
export AISPM_ORG_TOKEN="<org-token>"
cd agent && cargo run --release -p agent-service
```

---

## 8. Endpoint agent — Windows

Windows agent support is **build-and-deploy** today (systemd installer is Linux-only). Sprint backlog items cover full MSI/GPO distribution.

### Step 1 — Install build tools

1. Install **Visual Studio Build Tools** with “Desktop development with C++”
2. Install Rust: https://rustup.rs/ — select **MSVC** toolchain
3. Restart your terminal

### Step 2 — Build the agent

**PowerShell:**

```powershell
cd AI-SPM\agent
cargo build -p agent-service --release --features windows-service
```

Binary output: `agent\target\release\agent-service.exe`

### Step 3 — Configure environment

Create `C:\ProgramData\AISPM\agent.env`:

```ini
AISPM_GATEWAY_URL=http://localhost:8090
AISPM_ORG_TOKEN=dev-org-token-please-change-32chars-minimum
AISPM_ORG_ID=2117eef6-a519-47d5-bd6b-8a7357dafbb7
AISPM_LOG_JSON=false
```

Replace org ID/token with values from signup or `seed_dev_tenant.py`.

### Step 4 — Run the agent (development)

```powershell
cd AI-SPM\agent
$env:AISPM_GATEWAY_URL="http://localhost:8090"
$env:AISPM_ORG_ID="<org-uuid>"
$env:AISPM_ORG_TOKEN="<org-token>"
$env:AISPM_LOG_JSON="false"
.\target\release\agent-service.exe
```

On first start, the agent registers and writes mTLS certs to:

```text
C:\ProgramData\AISPM\certs\agent.crt
C:\ProgramData\AISPM\certs\agent.key
C:\ProgramData\AISPM\certs\ca.crt
```

### Step 5 — Install as Windows Service (optional)

**Administrator PowerShell:**

```powershell
sc.exe create AiSpmAgent binPath= "C:\Path\To\agent-service.exe" start= auto DisplayName= "AI-SPM Endpoint Agent"
sc.exe start AiSpmAgent
sc.exe query AiSpmAgent
```

For production packaging, see [agent/installer/wix/README.md](../agent/installer/wix/README.md).

### Step 6 — Trust MITM CA and proxy (manual for now)

The Linux installer automates CA trust and proxy. On Windows, until MSI automation ships:

1. Run the agent once so it generates a MITM CA (or use mitmproxy for web UI path)
2. Import the root CA into **Trusted Root Certification Authorities** (certmgr.msc or Group Policy)
3. Set system proxy to `127.0.0.1:8800` if using mitmproxy for web UIs, or configure per the agent’s proxy listen setting

> **Note:** Transparent iptables-style interception is Linux-only today. Windows WFP interception is on the roadmap (see `docs/ENTERPRISE_SPRINT_BACKLOG.md`).

### Web UI masking on Windows (mitmproxy)

If you need ChatGPT/Claude/Gemini web masking before the Windows MSI path is complete:

```powershell
pip install mitmproxy
cd AI-SPM\scripts\mitmproxy
# Set AISPM_WEB_MITM_PORT=8800 and run start-web-mitm.sh via Git Bash/WSL
```

Trust `mitmproxy-ca-cert` from the mitmproxy conf dir and set Windows proxy to `127.0.0.1:8800`.

---

## 9. Verify the installation

### Platform health

```bash
curl http://localhost:8090/health
curl http://localhost:8090/ready
```

### End-to-end demo script

```bash
make demo-sprint1
# or
AISPM_BASE_URL=http://localhost:8090 ./scripts/demo-sprint1.sh
```

### Agent registration

```bash
curl -X POST http://localhost:8090/agent/v1/register \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: <org-uuid>" \
  -d '{"hostname":"test-pc","org_token":"<org-token>","os":"linux","version":"0.1.0"}'
```

### Prompt inspect (inspect_only)

After registration, use `agent_id` from the register response:

```bash
curl -X POST "http://localhost:8090/agent/v1/prompt?inspect_only=true" \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: <org-uuid>" \
  -H "X-Agent-ID: <agent-uuid>" \
  -d '{
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "My email is test@example.com"}]
  }'
```

Expect masked content in the response and an audit row in the admin UI.

### Security tests (before merging changes)

```bash
make test-security
```

---

## 10. Ports reference

| Port | Service | Notes |
|------|---------|-------|
| **8090** | Kong API gateway | **Use this** for `VITE_API_URL` and `AISPM_GATEWAY_URL` |
| 8000 | FastAPI (direct / in-container) | Native `backend-dev` |
| 5173 | Vite dev server | Frontend hot reload |
| 3000 | Docker dashboard (nginx) | Production-built SPA |
| 3001 | Grafana | `admin` / `admin` |
| 9090 | Prometheus | Metrics |
| 5432 | PostgreSQL | `aispm` / `aispm` |
| **6380** | Redis (host) | Maps to container 6379 |
| 9443 | Agent transparent MITM | Linux enterprise |
| 8800 | Web UI mitmproxy | ChatGPT / Claude / Gemini |
| 8092 | Agent local API | mitmproxy web-audit bridge (`POST /web-audit`) |

---

## 11. Troubleshooting

### Kong returns 502

- Wait 30–60s after `docker compose up` for migrations/seeds
- Check API logs: `docker compose -f deploy/docker-compose.yml logs api`
- Verify API health: `curl http://localhost:8000/health` (from inside the compose network)

### Redis connection errors (native backend)

- If using Compose Redis from the host, set `REDIS_URL=redis://localhost:6380/0`
- Ensure Redis container is up: `docker compose -f deploy/docker-compose.yml ps redis`

### Frontend cannot reach API

- Confirm `VITE_API_URL=http://localhost:8090` in `frontend/.env`
- Restart Vite after changing `.env`
- Check browser devtools for CORS errors — `CORS_ORIGINS` must include your frontend origin

### RLS / security tests fail

```bash
cd backend && alembic upgrade head
make test-security
```

### Linux agent: permission / sudo errors

- Run `sudo ./scripts/install-agent.sh` from your **desktop user**, not `sudo -i` root shell
- Ensure `iptables` is available: `which iptables`

### Linux agent: ChatGPT shows certificate errors

- Re-run installer to trust CA: `sudo ./scripts/install-agent.sh`
- Fully quit and reopen browsers
- Check web MITM: `sudo systemctl status ai-spm-web-mitm`

### Linux agent: browsing broken outside AI sites

- mitmproxy uses `allow_hosts` — only AI domains are decrypted; other traffic is tunneled
- If proxy was left on after uninstall: `sudo ./scripts/install-agent.sh stop`

### Windows: agent cannot reach gateway

- Use `http://localhost:8090` (not 8080) when Kong is from this repo’s Compose file
- Allow `agent-service.exe` through Windows Firewall for outbound HTTP

### Docker Desktop on Windows: volume / path issues

- Enable WSL2 integration for your distro
- Clone the repo inside the WSL filesystem (`~/AI-SPM`) for best performance with `make` and the Linux agent installer

### Get dev org credentials again

```bash
cd backend && . .venv/bin/activate && python scripts/seed_dev_tenant.py
```

---

## Quick reference — copy/paste workflows

### Linux — full local demo in ~10 minutes

```bash
git clone <repo> AI-SPM && cd AI-SPM
make up
# wait for health
curl http://localhost:8090/health
# Admin UI: http://localhost:5173 or http://localhost:3000
# Login: admin@devcorp.io / DevAdminPass123!
sudo ./scripts/install-agent.sh
# reopen browsers, test ChatGPT with an email in the prompt
```

### Windows — platform only (no Linux agent installer)

```powershell
git clone <repo> AI-SPM
cd AI-SPM
docker compose -f deploy/docker-compose.yml up -d
curl http://localhost:8090/health
cd frontend
npm install
copy .env.example .env
# set VITE_API_URL=http://localhost:8090
npm run dev
# open http://localhost:5173 — login admin@devcorp.io / DevAdminPass123!
```

---

## Related docs

- [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md) — backend/frontend/agent dev details
- [SPRINT1_DEMO.md](SPRINT1_DEMO.md) — signup → audit demo flow
- [agent/README.md](../agent/README.md) — agent configuration reference
- [AGENTS.md](../AGENTS.md) — architecture and security rules
