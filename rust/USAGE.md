# AI-SPM DLP Agent — How to Use

*Designed and developed by Nabeel Qadri (<nabeel.qadri@sandyapps.co>).*

A short, practical guide to installing, running, and turning off the agent on a
Windows machine. For architecture and internals, see [README.md](README.md).

## What it does

The agent is a local proxy that sits between your browser and AI chat services
(ChatGPT, Claude, Gemini). It inspects what you send to those services and, per
the detection policy, **masks** sensitive values (e.g. card numbers, CNICs,
emails) or **blocks** the request entirely. Only the configured AI domains are
routed through it — all other browsing goes straight out, untouched.

## 1. Prerequisites

- **Windows 10 or 11.**
- Nothing else — the binaries are statically linked, so no Visual C++
  Redistributable install is needed.
- If you're installing the `.msi` (recommended - see below), you'll see **one
  administrator/UAC prompt** during install; nothing after that needs admin.
  If you're using the older manual/per-user steps instead, no admin rights are
  needed at all.

If you're building from source instead of using a prebuilt binary/installer,
you need the Rust toolchain (`x86_64-pc-windows-msvc`); then run `cargo build
--release`.

## 2. Recommended: install the `.msi`

If you have `agent-<version>-x86_64.msi`, this is the easiest path - just
double-click it (or `msiexec /i agent-<version>-x86_64.msi` for a silent
install). One UAC prompt, and it does everything in one step: installs the
agent under `Program Files\agent\bin`, generates and trusts the CA machine-wide
(so it covers every account on this PC, not just yours), sets up Firefox
trust if Firefox is installed, and registers `agentd` as a Windows Service
that starts automatically and restarts itself if it ever crashes - you don't
need to keep a terminal window open.

One thing the installer can't do for you, because it's inherently a per-user
setting: point *your* browser at the agent. After installing, run this once
(no admin needed):

```powershell
"C:\Program Files\agent\bin\agentctl.exe" enable-proxy
```

Then restart your browser. Everyone else who uses this machine runs that same
one command for themselves, once each. To remove everything (service, CA
trust, files), uninstall it from **Settings → Apps** like any other program,
or `msiexec /x agent-<version>-x86_64.msi`.

The rest of this guide (sections 3-7) covers the older manual/per-user setup -
useful if you don't have an `.msi`, or for development/testing. If you
installed via the `.msi`, skip ahead to [section 6](#6-check-its-working) to
confirm it's working, and [section 9](#9-troubleshooting) if something's wrong.

## 3. Files you need (manual setup only)

Keep the executables together with their config and policy files, in this
layout, and run commands **from this folder**:

```
ai-spm-agent/
├── config.toml              # proxy port, target domains, file paths
├── policies/default.toml    # the detection rules
├── agentd.exe               # the proxy (from target/release/)
└── agentctl.exe             # the control CLI (from target/release/)
```

`data/` (certificate + PAC file) and `logs/` are created automatically on first
run — you don't ship them.

## 4. One-time setup (manual)

Open a terminal (PowerShell) in the folder above and run:

```powershell
# a) Generate the local CA and trust it for the current user.
.\agentctl.exe install-ca

# b) Route the AI-service domains through the agent (writes a PAC file and
#    points your browser's proxy setting at it).
.\agentctl.exe enable-proxy
```

`install-ca` creates `data/ca/root.crt` + `root.key` if they don't exist and
adds the certificate to your Trusted Root store. `enable-proxy` configures the
current user's proxy auto-config so only the listed domains use the agent.

Firefox doesn't use the Windows certificate store, so `install-ca` also looks
for a local Firefox install and, if found, writes a `policies.json` enabling
`Certificates.ImportEnterpriseRoots` (a built-in Firefox policy that makes it
trust the same Root/CA stores Windows does). This works without admin rights
for the modern per-user Firefox install (`%LOCALAPPDATA%\Mozilla Firefox`); a
machine-wide install under `Program Files` needs `install-ca` run as
Administrator to write there. Restart Firefox afterward.

## 5. Run the agent (manual)

Start the proxy and leave it running:

```powershell
.\agentd.exe
```

It listens on `127.0.0.1:8443` (configurable in `config.toml`), logs to the
console and to a daily file under `logs\agentd.log.<date>`, and keeps running
until you press `Ctrl+C`.

**Restart your browser** after `enable-proxy` so it picks up the new proxy
configuration.

## 6. Check it's working

Send a message containing a test value through a routed AI site (e.g. a card
number `4111 1111 1111 1111`). Then look at the log:

```powershell
Get-Content logs\agentd.log.* -Tail 20
```

You should see an `intercepting target domain` line for the AI host and a
`dlp match` line naming the rule that fired (e.g. `rule_id=credit_card
action=Mask`). Matched values are logged by rule and span length only — never
the raw sensitive text.

`.\agentctl.exe status` prints the current config, target domains, and whether
the CA/policy files exist.

## 7. What gets detected

The rules live in `policies/default.toml`. Defaults:

| Rule | Detects | Action |
|------|---------|--------|
| `aws_access_key`   | AWS access key IDs           | block |
| `private_key_block`| PEM private-key header       | block |
| `credit_card`      | Card numbers (4-4-4-4 shape) | mask  |
| `pk_cnic`          | Pakistani CNIC (5-7-1)       | mask  |
| `us_ssn`           | US SSN (3-2-4)               | mask  |
| `email_address`    | Email addresses              | mask  |
| `phone_intl`       | International phone numbers   | mask  |
| `iban`             | IBAN / bank account          | mask  |
| `internal_codename_falcon` | Literal "Project Falcon" | log |

- **block** — the request is stopped; over HTTP the browser gets a `403`, over
  a WebSocket the message is silently dropped.
- **mask** — matched values are replaced with `[MASKED-<TYPE>-NNN]` before the
  request continues.
- **log** — recorded only; the request is unchanged.

When several rules match one request, **block wins over mask wins over log**. To
add or change rules, edit `policies/default.toml` and **restart `agentd`**
(policy is read once at startup). See the README's "Tuning detection rules" for
guidance on avoiding false positives.

## 8. Turning it off

**If you installed the `.msi`:** uninstall it from Settings → Apps (or
`msiexec /x`) - this stops and removes the Windows Service and the CA
certificate. Each user should still run `.\agentctl.exe disable-proxy`
themselves first, since that's per-user state the uninstaller can't reach.

**Manual setup:**

```powershell
# Stop routing traffic through the agent (reverts the proxy setting).
.\agentctl.exe disable-proxy

# Then stop the proxy itself: Ctrl+C in the agentd window.
```

Restart your browser afterward. The CA stays trusted until you remove it
manually (`certmgr.msc` → Trusted Root Certification Authorities).

## 9. Troubleshooting

- **Nothing appears in the log when I use ChatGPT in Chrome/Edge.** Make sure
  `agentd` is running — it serves the PAC over HTTP (`http://<addr>:8444/proxy.pac`),
  and the browser fetches that on startup. If the agent wasn't running when the
  browser launched, restart the browser after starting `agentd`. (Browsers load
  the PAC over HTTP because they refuse `file://` PAC URLs.)
- **Browser shows a certificate warning.** The CA isn't trusted in the store
  you're using. Re-run `install-ca`, and make sure you restarted the browser.
- **Firefox shows a certificate warning even after `install-ca`.** Check the
  `install-ca` output: if it printed "could not write policy" for a
  machine-wide install, re-run `install-ca` as Administrator. If it printed
  "Firefox not found", your Firefox isn't in one of the locations
  `install-ca` checks (per-user `%LOCALAPPDATA%` or the two `Program Files`
  paths) — a portable/zip install, for example. Either way, restart Firefox
  after any `policies.json` change; `about:policies` (Active tab) confirms
  whether it picked up `ImportEnterpriseRoots`.
- **A legitimate request got masked/blocked.** A rule is too broad. Tighten its
  pattern in `policies/default.toml` and restart `agentd` (or, for the `.msi`
  install, restart the `AiSpmDlpAgent` Windows Service from `services.msc`).
- **(`.msi` install) The service isn't running.** Check `services.msc` for
  `AiSpmDlpAgent` - it's set to auto-restart on failure, so a crash should
  self-heal within about 30 seconds; if it's not there at all, re-run the
  installer.

## 10. If you're sharing the agent with someone else

**Recommended: share the `.msi`.** Each recipient double-clicks it, approves
one UAC prompt, and everything (CA, Firefox trust, the service) is set up for
them automatically - they only need to run `enable-proxy` themselves
afterward (see [section 2](#2-recommended-install-the-msi)). Nobody needs to
generate or handle a CA key manually.

If you're instead sharing the raw executables for manual/dev setup:

- **Do not ship your `data/ca/` folder.** `root.key` is your CA's private key;
  anyone who has it could impersonate any site your CA trusts. Ship only the
  exes + `config.toml` + `policies/`, and let each machine generate its own CA
  on first `install-ca`.
- Each recipient runs `install-ca` and `enable-proxy` on their own machine
  (per-user, no admin needed).

Either way:
- The `.msi`/binaries are unsigned, so SmartScreen/antivirus may warn on first
  run.
- Deploying this means decrypting a user's traffic to AI services — confirm
  disclosure/consent requirements before rolling it out to anyone else.
