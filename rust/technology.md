# Technology Stack

Everything used to build, test, package, and run the AI-SPM DLP Agent.

## Language & toolchain

- **Rust** (2021 edition), `x86_64-pc-windows-msvc` target only
- **rustup** — toolchain installer/manager
- **MSVC linker** — Visual Studio 2022 Build Tools, "Desktop development with
  C++" workload (required to link on Windows)
- **CMake** and **NASM** — build-time dependencies of the TLS/crypto stack
  (`aws-lc-rs`, pulled in via `rustls`)
- Static CRT linking (`-C target-feature=+crt-static`, via `.cargo/config.toml`)
  so the built binaries don't need the Visual C++ Redistributable installed

## Architecture

A Cargo workspace: one `agent` binary package (`agentd`/`agentctl`) plus five
library crates (`agent-core`, `agent-ca`, `agent-dlp`, `agent-proxy`,
`agent-sysnet`).

## Core crates (direct dependencies)

**Async runtime & networking**
- `tokio` 1.52 (`full` features) — async runtime for the proxy, PAC server, and Windows Service loop
- `hudsucker` 0.25 — MITM HTTP/WebSocket proxy framework (TLS termination, per-host certificate minting, request/response and WebSocket handler traits)
- `rustls` 0.23 (`aws_lc_rs` crypto provider, `tls12`) — TLS implementation used by the proxy
- `http` 1.4 / `http-body-util` 0.1 / `bytes` 1.12 — HTTP types and body handling shared with hudsucker

**Certificates & Windows trust store**
- `rcgen` 0.14 — generates the local root CA and per-host leaf certificates on the fly
- `time` 0.3 — certificate validity window calculations
- `windows` 0.61 — official Microsoft Win32 API bindings, used directly (not through a wrapper) for:
  - **CNG/CryptoAPI** (`Win32_Security_Cryptography`) — installing/removing the CA in the Windows Certificate Store (`CertOpenStore`, `CertAddEncodedCertificateToStore`, `CertEnumCertificatesInStore`, `CertDeleteCertificateFromStore`, `CertGetNameStringW`, …)
  - **WinInet** (`Win32_Networking_WinInet`) — refreshing the per-user proxy settings after changing them (`InternetSetOptionW`)
- `winreg` 0.56 — reads/writes the current user's `Internet Settings` registry key (`AutoConfigURL`, `ProxyEnable`) for per-user PAC-based proxy configuration
- `windows-service` 0.7 — safe wrapper for Windows Service Control Manager (SCM) integration: service dispatch table, control handler (start/stop/shutdown), status reporting, service registration, and crash-restart recovery-action configuration

**DLP detection engine**
- `regex` 1.13 — regex-based detection rules (AWS keys, credit cards, CNICs, SSNs, emails, phone numbers, IBANs, …)
- `aho-corasick` 1.1 — case-insensitive multi-pattern literal matching (e.g. internal codename detection, private-key headers)

**Config, serialization & data**
- `serde` 1.0 (`derive`) / `serde_json` 1.0 — JSON parsing (request/response body leaf scanning) and general (de)serialization
- `toml` 0.8 — `config.toml` and `policies/*.toml` parsing

**CLI, errors & logging**
- `clap` 4.6 (`derive`) — `agentd`/`agentctl` command-line argument and subcommand parsing
- `anyhow` 1.0 — application-level error handling/context in the binaries
- `thiserror` 1.0 / 2.0 — typed library errors (`CaError`, `CoreError`, `DlpError`, `SysnetError`)
- `tracing` 0.1 / `tracing-subscriber` 0.3 (`env-filter`) / `tracing-appender` 0.2 — structured logging to console and a daily-rotating log file, with `info`/`trace` level separation so sensitive request bodies are never logged by default

**Transitively pulled in (not used directly, but part of the built binary)**
- `windows-sys`, `widestring`, `bitflags` — used internally by `windows-service`

## Windows platform integration

- **Windows Certificate Store** — Current User and Local Machine Trusted
  Root stores (`CERT_SYSTEM_STORE_CURRENT_USER` / `_LOCAL_MACHINE`)
- **WinINet / Internet Settings registry** — per-user browser proxy
  auto-configuration (`AutoConfigURL`, `ProxyEnable`)
- **Windows Service Control Manager (SCM)** — `agentd` runs as a real Windows
  Service (`AiSpmDlpAgent`) with native crash-restart recovery actions
- **Firefox enterprise policy engine** — `policies.json` /
  `Certificates.ImportEnterpriseRoots`, since Firefox uses its own NSS trust
  store rather than the Windows one

## Protocols & formats implemented/handled

- **TLS 1.2/1.3** interception (MITM) via on-the-fly leaf certificate minting
- **HTTP/1.1** request/response interception
- **WebSocket** (RFC 6455) frame interception, including handling real
  clients' `permessage-deflate` (RFC 7692) negotiation
- **PAC (Proxy Auto-Config)** script generation, served over HTTP
- **X.509** certificates (self-signed root CA + per-host leaf certs)
- **TOML** (config and policy files) and **JSON** (request/response bodies,
  Firefox `policies.json`)

## Packaging & distribution

- **cargo-wix** 0.3 — Cargo subcommand driving the WiX build
- **WiX Toolset v3.14** (`candle.exe` / `light.exe`) — compiles `wix/main.wxs`
  into the `.msi`; requires the .NET Framework 3.5 Windows feature
- **Windows Installer (MSI)** — `perMachine` install scope, with deferred
  custom actions (`agentctl install --full` / `agentctl uninstall`) wired
  into the install/uninstall sequence
- **PowerShell** — `scripts/package-release.ps1` automates build → `cargo
  wix` → `dist/` packaging into a versioned zip

## Testing

- `cargo test --workspace` — Rust's built-in test framework; unit tests
  across every crate (DLP engine/masking, config/policy parsing, CA
  generation, PAC rendering, WebSocket handler logic) plus a few
  file-system-based integration-style tests (e.g. CA regeneration behavior)
- No external test framework, mocking library, or fuzzer in use today
- Manual/real-traffic verification (not automated): local Python
  `http.server`/`websockets` mock servers, `curl`, and real browser/desktop-app
  traffic against `chatgpt.com`, `claude.ai`, etc.

## Development & ops tooling used to build this

- **Git** — version control (this file's own commit history)
- **GitHub** — remote hosting (`asadsandyapp/ai-spm`)
- **winget** — installed Rust, Visual Studio Build Tools, CMake, NASM, and
  the WiX Toolset
- **PowerShell** / **Git Bash** — command-line environments used throughout
  development and for the elevated install/service verification tests
