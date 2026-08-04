# AI-SPM Endpoint Agent (Rust)

Lightweight endpoint agent for the AI-SPM platform. Intercepts AI provider traffic on employee workstations and forwards prompts through the central security gateway.

**Design targets:** &lt;30 MB idle RAM, modular crates, mTLS-ready architecture.

## CI

`.github/workflows/agent-ci.yml` runs on every push/PR to `proxy` that
touches `agent/**`, three jobs deep:

1. **`test`** — builds and unit-tests this workspace on both
   `windows-latest` and `ubuntu-latest`. Installs the system deps the
   BoringSSL-based TLS stack (`boring`/`tokio-boring`/`hyper-boring`) needs
   to build from source (`libclang` for bindgen, `cmake`, `go`, `nasm`).
   On Windows, also builds `agent-service` with `--features windows-service`
   specifically — the plain workspace build never enables optional
   features, which is exactly how a real compile error in that path
   (`service_dispatcher::start` called without the required
   `define_windows_service!` FFI wrapper) went undetected until someone
   built a release MSI by hand.
2. **`e2e-against-backend`** (`needs: test`, `ubuntu-latest` only) — brings
   up the real AI-SPM backend (`deploy/docker-compose.yml`: postgres,
   redis, api, kong) and runs the actual built `agent-service` binary
   against it: registration with a real org token + mTLS cert issuance, a
   live heartbeat, a PII-bearing prompt through the agent's own
   `local_api`, confirms the masked (never raw) event lands in the
   backend's audit log, then restarts the binary and confirms
   re-registration doesn't create a duplicate fleet entry. See
   [`scripts/e2e-smoke-test.py`](scripts/e2e-smoke-test.py) for exactly
   what's asserted — this is the same manual flow that used to be
   validated by hand before a release, now gated on every `agent/**`
   change instead of relying on someone remembering to run it.
3. **`installer-test-windows`** (no `needs:` — runs in parallel with
   `test`, same reasoning as rust-ci.yml's installer jobs: a flake here
   shouldn't block the fast unit-test feedback loop) — builds the real
   Windows MSI ([`installer/wix/Product.wxs`](installer/wix/Product.wxs)),
   installs it for real, confirms the service is running, confirms the
   crash-recovery config actually works (kills the process and asserts SCM
   restarts it with a **new PID**, not just that the config exists),
   confirms the tray autostart registry key, then uninstalls and confirms
   clean removal.

## Workspace Crates

| Crate | Type | Purpose |
|-------|------|---------|
| `agent-core` | Library | Config, gateway HTTP client, local proxy, heartbeat |
| `agent-service` | Binary | Always-on daemon (systemd / Windows Service) |
| `agent-tray` | Binary | Tauri 2 tray UI placeholder |

## Prerequisites

- [Rust](https://rustup.rs/) 1.75+ (2021 edition)
- Linux: `build-essential`, `pkg-config`, `libssl-dev` (for rustls native roots)
- Windows: Visual Studio Build Tools, WiX Toolset (for MSI — see [`installer/wix/README.md`](installer/wix/README.md))

## Quick Start (Linux)

```bash
cd agent

# Build all crates
cargo build --release

# Run tests
cargo test --workspace

# Configure (minimum required)
export AISPM_GATEWAY_URL="http://localhost:8000"
export AISPM_ORG_TOKEN="your-org-token-at-least-32-chars-long"
export AISPM_ORG_ID="00000000-0000-0000-0000-000000000001"
export AISPM_PROXY_LISTEN="127.0.0.1:8080"

# Optional: JSON config file (overridden by env vars)
# export AISPM_CONFIG_FILE="/etc/ai-spm/agent.json"

# Run the daemon (structured JSON logs to stdout)
cargo run -p agent-service --release
```

Set `AISPM_LOG_JSON=false` for human-readable log lines during local development.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `AISPM_GATEWAY_URL` | No (default `http://localhost:8000`) | Gateway base URL |
| `AISPM_ORG_TOKEN` | Yes | Organization registration token |
| `AISPM_ORG_ID` | Yes | Organization UUID |
| `AISPM_AGENT_ID` | No | Agent UUID (set after registration) |
| `AISPM_PROXY_LISTEN` | No (default `127.0.0.1:8080`) | Local proxy bind address |
| `AISPM_CONFIG_FILE` | No | Path to JSON config file |
| `AISPM_MTLS_CERT` | No | Client certificate PEM path |
| `AISPM_MTLS_KEY` | No | Client private key PEM path |
| `AISPM_MTLS_CA` | No | Platform CA certificate PEM path |
| `AISPM_MITM_CA_DIR` | No | MITM root CA and leaf cert directory |
| `AISPM_AUTO_CONFIGURE_ENDPOINT` | No (default `true`) | Enable automatic CA/proxy endpoint setup |
| `AISPM_AUTO_INSTALL_CA` | No (inherits endpoint setting) | Install MITM CA into supported trust stores |
| `AISPM_AUTO_CONFIGURE_PROXY` | No (inherits endpoint setting) | Configure supported OS proxy settings |
| `AISPM_LOG_JSON` | No (default `true`) | Emit JSON structured logs |

### Example `agent.json`

```json
{
  "gateway_url": "https://gateway.example.com",
  "org_token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "org_id": "00000000-0000-0000-0000-000000000001",
  "proxy_listen": "127.0.0.1:8080",
  "mtls_cert_path": "/etc/ai-spm/certs/agent.crt",
  "mtls_key_path": "/etc/ai-spm/certs/agent.key",
  "ca_cert_path": "/etc/ai-spm/certs/ca.crt"
}
```

## mTLS Setup

Production deployments authenticate to the gateway with a client certificate issued at registration.

### Automatic provisioning (recommended)

On first launch, the agent calls `POST /agent/v1/register`. When the gateway returns certificate material, the agent writes:

| File | Default Linux path | Default Windows path |
|------|-------------------|---------------------|
| Client cert | `/etc/ai-spm/certs/agent.crt` | `C:\ProgramData\AISPM\certs\agent.crt` |
| Private key | `/etc/ai-spm/certs/agent.key` | `C:\ProgramData\AISPM\certs\agent.key` |
| Platform CA | `/etc/ai-spm/certs/ca.crt` | `C:\ProgramData\AISPM\certs\ca.crt` |

Override paths with `AISPM_MTLS_CERT`, `AISPM_MTLS_KEY`, and `AISPM_MTLS_CA` (or the matching fields in `agent.json`).

After saving, the gateway client reloads with a `rustls::ClientConfig` identity attached via reqwest.

### Manual provisioning

If certificates are pre-distributed (e.g. via GPO or MDM), place PEM files at the configured paths before starting the agent. The client loads them on startup when all three files exist.

### Example Linux env file (`/etc/ai-spm/agent.env`)

```bash
AISPM_GATEWAY_URL=https://gateway.example.com
AISPM_ORG_TOKEN=your-org-token-at-least-32-chars-long
AISPM_ORG_ID=00000000-0000-0000-0000-000000000001
AISPM_MTLS_CERT=/etc/ai-spm/certs/agent.crt
AISPM_MTLS_KEY=/etc/ai-spm/certs/agent.key
AISPM_MTLS_CA=/etc/ai-spm/certs/ca.crt
AISPM_LOG_JSON=true
```

Ensure the service user can write to the cert directory on first registration:

```bash
sudo mkdir -p /etc/ai-spm/certs
sudo chown -R aispm:aispm /etc/ai-spm
sudo chmod 700 /etc/ai-spm/certs
```

## Intercepted Domains

The local HTTPS MITM proxy decrypts, inspects, and forwards AI traffic for:

- `chat.openai.com`
- `chatgpt.com`
- `claude.ai`
- `api.anthropic.com`
- `api.openai.com`
- `generativelanguage.googleapis.com`
- `gemini.google.com`

On startup, the agent generates or loads a local MITM root CA, attempts to install it into supported Linux trust stores, and configures supported desktop proxy settings to route traffic through the agent. Non-AI HTTPS `CONNECT` traffic is tunneled without inspection so system-wide proxy mode remains usable.

Set `AISPM_AUTO_CONFIGURE_ENDPOINT=false` to disable all endpoint changes, or disable only CA/proxy setup with `AISPM_AUTO_INSTALL_CA=false` / `AISPM_AUTO_CONFIGURE_PROXY=false`.

## Gateway API

`agent-core` calls:

| Endpoint | Headers | Purpose |
|----------|---------|---------|
| `POST /agent/v1/register` | `X-Org-ID` | First-launch registration (returns mTLS certs) |
| `POST /agent/v1/heartbeat` | `X-Org-ID`, `X-Agent-ID` | 60s health signal |
| `POST /agent/v1/prompt` | `X-Org-ID`, `X-Agent-ID` | Submit intercepted prompt |

Authenticated requests use mTLS when cert/key/CA files are present.

## Linux systemd

Install the unit file from [`deploy/systemd/aispm-agent.service`](../deploy/systemd/aispm-agent.service):

```bash
sudo cp target/release/agent-service /usr/local/bin/
sudo cp ../deploy/systemd/aispm-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aispm-agent
```

## Windows Build

```powershell
cd agent
cargo build -p agent-service --release

# Windows Service integration (SCM)
cargo build -p agent-service --release --features windows-service
```

Install as a Windows Service using `sc create`, the WiX MSI installer ([`installer/wix/README.md`](installer/wix/README.md)), or Intune. Build on a Windows host with the `windows-service` feature enabled.

## Tray App (placeholder)

```bash
cargo build -p agent-tray --release
```

See [`crates/agent-tray/README.md`](crates/agent-tray/README.md) for Tauri 2 integration notes.

## Architecture

```
┌─────────────────┐     local proxy      ┌──────────────────┐
│  Browser / App  │ ──► :8080            │  agent-service   │
└─────────────────┘                      │  ├─ proxy        │
                                         │  └─ heartbeat    │
                                         └────────┬─────────┘
                                                  │ mTLS
                                                  ▼
                                         ┌──────────────────┐
                                         │  Kong Gateway    │
                                         │  /agent/v1/*     │
                                         └──────────────────┘
```

## Development

```bash
# Check formatting
cargo fmt --all

# Lint
cargo clippy --workspace -- -D warnings

# Integration tests only
cargo test -p agent-integration-tests
```

## License

Proprietary — AI-SPM Platform
