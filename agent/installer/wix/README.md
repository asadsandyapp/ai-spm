# WiX MSI Installer (Windows)

Build a Windows MSI package for the AI-SPM endpoint agent using [WiX Toolset v4+](https://wixtoolset.org/).

## Prerequisites

- Windows 10/11 or Windows Server 2019+
- [Rust](https://rustup.rs/) with the MSVC toolchain
- [WiX Toolset](https://wixtoolset.org/docs/intro/) (`wix` CLI on PATH)
- Visual Studio Build Tools (C++ workload)

## Build the Agent Binary

From the `agent/` workspace root:

```powershell
cd agent
cargo build -p agent-service --release --features windows-service
```

The release binary is written to:

```text
target\release\agent-service.exe
```

## Directory Layout

Create the WiX source tree under `agent/installer/wix/`:

```text
agent/installer/wix/
├── README.md
├── Product.wxs          # Product definition (upgrade code, version, features)
├── Files.wxs            # Harvested or explicit file components
├── Service.wxs          # Windows Service (AiSpmAgent) install/remove
└── agent.wixproj        # WiX project file (optional, for MSBuild)
```

## Example `Product.wxs`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package
    Name="AI-SPM Endpoint Agent"
    Manufacturer="AI-SPM Platform"
    Version="0.1.0.0"
    UpgradeCode="PUT-GUID-HERE"
    Scope="perMachine">

    <MajorUpgrade DowngradeErrorMessage="A newer version is already installed." />
    <MediaTemplate EmbedCab="yes" />

    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLDIR" Name="AISPM">
        <Directory Id="AgentDir" Name="Agent" />
      </Directory>
    </StandardDirectory>

    <StandardDirectory Id="CommonAppDataFolder">
      <Directory Id="CertDir" Name="AISPM\certs" />
    </StandardDirectory>

    <ComponentGroup Id="AgentComponents" Directory="AgentDir">
      <Component Id="AgentServiceExe" Guid="PUT-GUID-HERE">
        <File Source="..\..\target\release\agent-service.exe" KeyPath="yes" />
      </Component>
    </ComponentGroup>

    <Feature Id="MainFeature" Title="AI-SPM Agent" Level="1">
      <ComponentGroupRef Id="AgentComponents" />
    </Feature>
  </Package>
</Wix>
```

## Windows Service Component

Register the agent as `AiSpmAgent` (matches the `windows-service` feature in `agent-service`).

Include the WiX Util extension's `<util:ServiceConfig>` so a crashed agent restarts
under SCM the same way the Linux systemd unit's `Restart=on-failure` does (see
[`deploy/systemd/aispm-agent.service`](../../../deploy/systemd/aispm-agent.service)) —
without this, a Windows crash leaves the endpoint unprotected until someone notices:

```xml
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:util="http://wixtoolset.org/schemas/v4/wxs/util">
  ...
  <Component Id="AgentWindowsService" Directory="AgentDir" Guid="PUT-GUID-HERE">
    <File Id="AgentServiceExeFile" Source="..\..\target\release\agent-service.exe" KeyPath="yes" />
    <ServiceInstall
      Id="AgentServiceInstall"
      Name="AiSpmAgent"
      DisplayName="AI-SPM Endpoint Agent"
      Description="Intercepts AI provider traffic and forwards prompts through the AI-SPM gateway."
      Type="ownProcess"
      Start="auto"
      Account="LocalSystem"
      ErrorControl="normal">
      <util:ServiceConfig
        FirstFailureActionType="restart"
        SecondFailureActionType="restart"
        ThirdFailureActionType="restart"
        RestartServiceDelayInSeconds="30"
        ResetPeriodInDays="1" />
    </ServiceInstall>
    <ServiceControl
      Id="AgentServiceControl"
      Name="AiSpmAgent"
      Start="install"
      Stop="both"
      Remove="uninstall"
      Wait="yes" />
  </Component>
</Wix>
```

Requires the WiX Util extension: `wix extension add WixToolset.Util.wixext` (v4+),
or `-ext WixUtilExtension` on the `candle`/`light` command line for WiX v3.

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

## Build the MSI

With WiX v4 CLI:

```powershell
cd agent\installer\wix
wix build Product.wxs Files.wxs Service.wxs -ext WixToolset.Util.wixext -o aispm-agent.msi
```

For WiX v3 (legacy):

```powershell
candle Product.wxs Files.wxs Service.wxs
light -ext WixUtilExtension -out aispm-agent.msi Product.wixobj Files.wixobj Service.wixobj
```

## Signing (Production)

Sign the MSI with your code-signing certificate before enterprise distribution:

```powershell
signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 aispm-agent.msi
```

## Verification

1. Install: `msiexec /i aispm-agent.msi /l*v install.log`
2. Confirm service: `sc query AiSpmAgent`
3. Confirm recovery config took effect: `sc qfailure AiSpmAgent` should list `RESTART` actions with a 30000ms delay
4. Kill the process (`taskkill /f /im agent-service.exe`) and confirm SCM restarts it (`sc query AiSpmAgent` shows a new PID) — mirrors the real-hardware verification already done for the Linux/rust DLP agent's systemd unit, do the same here rather than trusting the WiX markup alone
5. Check logs: Event Viewer → Application, or run with `AISPM_LOG_JSON=false` for console debugging
6. Uninstall: `msiexec /x aispm-agent.msi`

## Upgrade Notes

- Bump `Version` in `Product.wxs` for each release.
- Keep `UpgradeCode` constant across versions of the same product line.
- Use `MajorUpgrade` to replace in-place installs.
