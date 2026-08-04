# WiX MSI Installer (Windows)

Real WiX Toolset **v3** source (not a hypothetical example) for the Windows
MSI packaging `agent-service.exe` (as the `AiSpmAgent` Windows Service) and
`agent-tray.exe` (autostarted per-machine). Built and verified locally with
WiX Toolset v3.14 (`candle`/`light`); verified end-to-end (install, service
running, recovery config, tray autostart key, kill-and-confirm-restart,
uninstall, clean removal) by `.github/workflows/agent-ci.yml`'s
`installer-test-windows` job, which runs on every `agent/**` change.

## Prerequisites

- Windows 10/11 or Windows Server 2019+
- [Rust](https://rustup.rs/) with the MSVC toolchain
- [WiX Toolset v3](https://wixtoolset.org/docs/wix3/) (`candle`/`light` on PATH — `choco install wixtoolset`)
- Visual Studio Build Tools (C++ workload)

## Build the binaries

From the `agent/` workspace root:

```powershell
cd agent
cargo build --release -p agent-service --features windows-service -p agent-tray
```

Produces `target\release\agent-service.exe` and `target\release\agent-tray.exe`,
both referenced by `Product.wxs` via relative paths.

## What `Product.wxs` packages

- **`AgentServiceComponent`** — installs `agent-service.exe` and registers it
  as the `AiSpmAgent` Windows Service (`LocalSystem`, auto-start), with a
  `util:ServiceConfig` crash-recovery block (restart on failure, 30s delay)
  matching the Linux systemd unit's `Restart=on-failure` (see
  [`deploy/systemd/aispm-agent.service`](../../../deploy/systemd/aispm-agent.service)) —
  without this, a Windows crash leaves the endpoint unprotected until someone
  notices.
- **`AgentTrayComponent`** — installs `agent-tray.exe` and adds an
  `HKLM\Software\Microsoft\Windows\CurrentVersion\Run` autostart entry, so
  whoever's logged in sees the Protected/Disconnected/Blocked tray.

`UpgradeCode` (`93E7E455-EFF2-4918-BC74-418C39F7C710`) must stay constant
across every future version — `MajorUpgrade` depends on it to detect and
replace prior installs. Component GUIDs are fixed (not `*`), since Windows
Installer needs stable component identity across upgrades, particularly for
the `ServiceInstall`-bearing component.

## Environment Configuration

Ship a template env file to `%ProgramData%\AISPM\agent.env` or document GPO/Intune deployment of:

```ini
AISPM_GATEWAY_URL=https://gateway.example.com
AISPM_ORG_TOKEN=your-org-token-at-least-32-chars-long
AISPM_ORG_ID=00000000-0000-0000-0000-000000000001
AISPM_MTLS_CERT=C:\ProgramData\AISPM\certs\agent.crt
AISPM_MTLS_KEY=C:\ProgramData\AISPM\certs\agent.key
AISPM_MTLS_CA=C:\ProgramData\AISPM\certs\ca.crt
AISPM_LOG_JSON=true
```

On first launch, registration writes client certificates to these paths automatically.

A Windows Service does **not** inherit an interactive session's environment
variables — it reads the machine environment block from the registry at
process creation. Set these as **machine**-scope (`setx /M` or
`[Environment]::SetEnvironmentVariable(name, value, "Machine")`), not just
for your own user.

## Build the MSI

```powershell
cd agent\installer\wix
candle -ext WixUtilExtension Product.wxs
light -ext WixUtilExtension -out aispm-agent.msi Product.wixobj
```

Both binary paths default to `..\..\target\release\<name>.exe`; override with
`candle -dAgentServiceExe=<path> -dAgentTrayExe=<path> Product.wxs` if you built elsewhere.

## Signing (Production)

Sign the MSI with your code-signing certificate before enterprise distribution:

```powershell
signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 aispm-agent.msi
```

## Verification

1. Install (needs an elevated/admin shell — a per-machine service install
   fails with Windows Installer error 1925 otherwise):
   `msiexec /i aispm-agent.msi /quiet /l*v install.log`
2. Confirm service: `sc query AiSpmAgent` → `RUNNING`
3. Confirm recovery config took effect: `sc qfailure AiSpmAgent` should list `RESTART` actions with a 30000ms delay
4. Confirm tray autostart: `Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name AiSpmAgentTray`
5. Kill the process (`Stop-Process -Name agent-service -Force`) and confirm SCM actually restarts it with a **new PID** (`Get-Process agent-service`) — don't just trust the WiX markup; this is exactly the class of thing that looks configured but isn't (see `.github/workflows/agent-ci.yml`'s `installer-test-windows` job, which asserts on the PID change, not just service status)
6. Check logs: Event Viewer → Application, or run with `AISPM_LOG_JSON=false` for console debugging
7. Uninstall: `msiexec /x aispm-agent.msi /quiet`
8. Confirm clean removal: service, registry key, and `C:\Program Files\AISPM` are all gone

## Upgrade Notes

- Bump `Version` in `Product.wxs` for each release.
- Keep `UpgradeCode` constant across versions of the same product line.
- Use `MajorUpgrade` to replace in-place installs.

## Not yet done

- MSI is unsigned (see Signing above — needs a real code-signing cert, not scripted here).
- No Start Menu shortcut or uninstall entry beyond what MSI provides by default.
- Tray autostart is machine-wide (HKLM); there's no per-user opt-out.
