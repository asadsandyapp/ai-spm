# AI-SPM DLP Agent

*Designed and developed by Nabeel Qadri (<nabeel.qadri@sandyapps.co>).*

A Windows endpoint agent, written in Rust, that acts as a local DLP (Data Loss
Prevention) proxy for AI chat traffic. It intercepts outbound HTTPS requests
to configured AI services (ChatGPT, Claude, Gemini, ...), scans request
bodies for sensitive data, and masks, blocks, or logs matches before they
leave the machine.

```
Browser / ChatGPT Desktop / AI Application
                 |
                 v
        Windows Endpoint Agent
     +---------------------------+
     | 1. Local HTTPS Proxy      |
     | 2. TLS Inspection         |
     | 3. DLP Detection Engine   |
     | 4. Mask / Block / Log     |
     +---------------------------+
                 |
                 v
       ChatGPT / Claude / Gemini
```

Traffic to domains outside the configured allowlist is never decrypted —
the proxy tunnels it through untouched. On top of that, the current user's
browser proxy setting is scoped with a generated PAC file so that *only*
the configured AI domains are ever routed to the proxy in the first place —
everything else goes `DIRECT`, never touching this tool at all.

## Status

Milestones M1–M4 are implemented and verified: local MITM proxy, domain
scoping, DLP detection, mask/block/log actions, and a PAC-scoped per-user
proxy setup so only AI-service traffic gets routed through the agent.
Verified not just synthetically but against real `chatgpt.com` traffic in a
browser (see [Tuning detection rules](#tuning-detection-rules) for a false
positive that surfaced during that test and how it was fixed).
WebSocket DLP scanning is implemented — real-browser traffic testing found
that ChatGPT's web UI sends conversation content over `wss://ws.chatgpt.com`,
bypassing HTTP-only scanning entirely; outbound WebSocket frames now get the
same scan/mask/block treatment (verified end-to-end through the proxy against
a live WebSocket connection; see [Testing](#testing)).
Real `ws.chatgpt.com` traffic surfaced a further bug beyond the local-echo-server
testing: the real server negotiates permessage-deflate compression, which
hudsucker's WebSocket client can't decode, so every real WS upgrade failed with
a "Reserved bits are non-zero" error and retried in a loop, never scanning a
single frame. Fixed by stripping `Sec-WebSocket-Extensions` from the upgrade
request before it reaches the upstream connect, so no compression is ever
negotiated; verified against live `chatgpt.com` traffic post-fix (see
`crates/agent-proxy/src/handler.rs`).
`install-ca` also sets up Firefox trust (`policies.json` + `ImportEnterpriseRoots`,
see [Run](#run)) and the ChatGPT Windows desktop app (an Electron/MSIX app) is
covered too, since both just follow the same system CA store and PAC-scoped
proxy setting as any other app. Both are now confirmed against real traffic:
Firefox (PAC routing, CA trust, and a real typed message arriving masked) and
the ChatGPT desktop app (routing, CA trust, and real conversation-body masking
on its `/backend-api/f/conversation` endpoint) — see `ROADMAP.md`'s coverage
matrix.

**Production install is now available.** `agentd` runs as a real Windows
Service (`AiSpmDlpAgent`) with SCM-native crash-restart recovery actions —
verified end-to-end: killing `agentd.exe` outright, SCM spawned a replacement
process exactly 30 seconds later per the configured recovery schedule, with
no external supervisor involved. `agentctl install --full` (elevated) installs
the CA into the **Local Machine** Trusted Root store (covers every account on
the box, not just the invoking user), sets up Firefox enterprise trust, and
registers/starts the service; `agentctl uninstall` reverses it. A `.msi` (via
`cargo wix`, see [Packaging](#packaging)) wraps this into a normal Windows
installer — verified with a real `msiexec /i` / `msiexec /x` cycle: files land
under `Program Files\agent\bin`, the service starts running automatically,
the CA and Firefox trust are set up, and uninstall fully reverses all of it
(service deregistered, CA cert removed from the store). Code signing, a
DPAPI-encrypted CA private key at rest, and a Windows Event Log sink remain
deferred — see [Not yet implemented](#not-yet-implemented).

## How it works

1. **Local HTTPS proxy** (`agentd`, built on [hudsucker](https://github.com/omjadas/hudsucker)) listens on `127.0.0.1:8443`.
2. For each `CONNECT` tunnel, the target host is checked against `[targets].domains`
   in `config.toml`. Non-matching hosts are tunneled byte-for-byte — no
   certificate is minted, nothing is decrypted.
3. For matching hosts, the proxy terminates TLS using a certificate it mints
   on the fly (signed by a local root CA it generates and installs into the
   Windows trust store), reads the request body, and re-encrypts to the real
   upstream server.
4. The request body is scanned against the DLP policy (`policies/default.toml`).
   The highest-priority matched rule's action is applied:
   - **block** — the client gets a `403` immediately; the request never reaches upstream.
   - **mask** — matched spans are redacted (`[MASKED-<label>-NNN]`, where
     `label` is the rule's type code and `NNN` is a per-message sequence
     number) and the modified body is forwarded.
   - **log** — the match is recorded and the body is forwarded unmodified.
5. Every match is logged (rule id, severity, action, destination host, matched
   span length) — the raw matched text itself is never logged.
6. **WebSocket frames are scanned too.** Some chat clients carry real
   conversation content over WebSockets rather than plain HTTP (ChatGPT's web
   UI uses `wss://ws.chatgpt.com/...`), so MITM'd connections that upgrade to
   WebSocket get the same DLP treatment on every **outbound (client → server)**
   frame:
   - **block** — the frame is dropped; it never reaches upstream. (Unlike HTTP,
     there's no in-band way to return an error to the page, so the message
     silently disappears from the server's perspective.)
   - **mask** — text frames are rewritten with matched spans redacted. Binary
     frames matching a mask rule are **dropped** instead — rewriting an unknown
     binary encoding would corrupt it.
   - **log** — the match is recorded and the frame is forwarded unmodified.
   Inbound (server → client) frames and control frames (ping/pong/close) pass
   through unscanned. WebSocket frames carry no content type, so JSON leaf
   scanning is attempted first, falling back to raw-text scanning.

## Project layout

```
agent/
├── Cargo.toml                  # workspace root + `agent` binary package
├── .cargo/config.toml          # static CRT link (no vcruntime140.dll dependency)
├── config.toml                 # agent config (proxy, CA paths, target domains, policy path)
├── policies/default.toml       # DLP rules (regex/literal patterns, severity, action)
├── wix/main.wxs                # cargo-wix packaging source (produces the .msi)
├── packaging/INSTALL-NOTES.txt # tracked, recipient-facing usage notes bundled with every build
├── scripts/package-release.ps1 # builds + packages a release into dist/ (see Packaging)
├── crates/
│   ├── agent-core/             # config + policy types (serde/toml)
│   ├── agent-ca/               # root CA generation (rcgen) + Windows trust store install
│   ├── agent-dlp/              # DLP engine: rule compilation, scanning, masking
│   ├── agent-proxy/            # hudsucker Http/WebSocket handlers: intercept, scan, act
│   └── agent-sysnet/           # PAC file generation + current-user proxy auto-config
├── src/
│   ├── lib.rs                  # shared support code for both binaries
│   ├── runtime.rs              # core agent startup, shared by console + service modes
│   ├── service.rs              # Windows Service (SCM) dispatch/control-handler glue
│   ├── service_install.rs      # registers/configures/removes the Windows Service
│   └── bin/
│       ├── agentd.rs           # the running proxy (console or `--service` mode)
│       └── agentctl.rs         # CLI: install-ca, enable-proxy, disable-proxy, status,
│                                #      install --full, uninstall
```

## Prerequisites

- Windows 10/11
- Rust (via [rustup](https://rustup.rs/)) — `x86_64-pc-windows-msvc` toolchain
- MSVC linker: Visual Studio Build Tools 2022 with the "Desktop development
  with C++" workload
- [CMake](https://cmake.org/) and [NASM](https://www.nasm.us/) (build-time
  dependencies of the TLS/crypto stack)
- Only if you're building the `.msi` (see [Packaging](#packaging)), not for a
  plain `cargo build`: [`cargo-wix`](https://github.com/volks73/cargo-wix)
  (`cargo install cargo-wix`) and the
  [WiX Toolset v3](https://wixtoolset.org/) (`winget install --id
  WiXToolset.WiXToolset`, which needs the .NET Framework 3.5 Windows feature
  enabled and admin rights for that one-time install step)

On this machine, all of the above were installed via `winget`:

```powershell
winget install --id Rustlang.Rustup -e
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
winget install --id Kitware.CMake -e
winget install --id NASM.NASM -e
```

## Build

```powershell
cargo build --release
```

Binaries land in `target\release\agentd.exe` and `target\release\agentctl.exe`.
`.cargo/config.toml` statically links the MSVC C runtime
(`target-feature=+crt-static`), so neither binary needs the Visual C++
Redistributable (`vcruntime140.dll`) installed on the machine they run on —
confirmed by checking the built exes contain no reference to it.

## Run

### Production install

The easiest path for a real machine: build/download the `.msi` (see
[Packaging](#packaging)) and install it — `msiexec /i agent-0.1.0-x86_64.msi`,
or just double-click it. This needs one UAC elevation (it's a `perMachine`
install), and does everything below in one step: installs `agentd`/`agentctl`
under `Program Files\agent\bin`, generates and trusts the CA in the **Local
Machine** store, sets up Firefox enterprise trust, and registers/starts
`agentd` as an auto-start Windows Service (`AiSpmDlpAgent`) with SCM-native
crash-restart recovery actions. `msiexec /x` (or Apps & Features) reverses all
of it: stops and removes the service, and best-effort removes the CA cert.

The MSI's install/uninstall steps are just `agentctl install --full` /
`agentctl uninstall` under the hood (see `wix/main.wxs`'s custom actions) —
you can run those directly instead of building an MSI if you prefer, from an
elevated prompt, once `agentd.exe`/`agentctl.exe`/`config.toml`/
`policies\default.toml` are wherever you want them installed:

```powershell
.\agentctl.exe install --full --config .\config.toml
# ... later, to remove it:
.\agentctl.exe uninstall
```

One thing the full install does *not* do: point any specific user's browser
at the agent (that's inherently per-user state, see step 3 below). Each user
on the machine still runs `agentctl enable-proxy` themselves once, no admin
needed.

### Manual / development setup

The granular subcommands below are what `install --full` composes internally,
and remain the way to run the agent for local development/testing without
building or installing anything system-wide.

**1. Generate and trust the local CA** (installs into the current user's
Trusted Root store — no admin required):

```powershell
.\target\release\agentctl.exe install-ca
```

Chromium browsers (Chrome, Edge) read that store directly. Firefox doesn't —
it has its own NSS trust store — so `install-ca` also looks for a local
Firefox install and writes a `policies.json` enabling
`Certificates.ImportEnterpriseRoots`, the built-in Firefox policy for
trusting the OS certificate stores. This covers the modern per-user Firefox
install (`%LOCALAPPDATA%\Mozilla Firefox`) with no admin needed; a
machine-wide install under `Program Files` needs `install-ca` run elevated.
Restart Firefox afterward. See `crates/agent-ca/src/firefox.rs`.

**2. Start the proxy:**

```powershell
$env:RUST_LOG = "info"
.\target\release\agentd.exe --config config.toml
```

The proxy listens on `127.0.0.1:8443` (configurable in `config.toml`).

**3. Route only AI-service traffic through it** (points the current user's
proxy auto-config at the PAC that `agentd` serves over HTTP — per-user, no
admin required):

```powershell
.\target\release\agentctl.exe enable-proxy
```

The auto-config URL is `http://127.0.0.1:8444/proxy.pac`, served by `agentd`
itself (the port is `sysnet.pac_port`). HTTP is used deliberately: Chromium
browsers (Chrome, Edge) silently ignore PAC scripts loaded from `file://`
URLs, so a file-based PAC would leave them unproxied. Because the PAC is
served by `agentd`, the proxy must be running for routing to take effect; when
it's stopped, the browser's PAC fetch fails open and traffic goes DIRECT.

Everything *not* in `[targets].domains` resolves to `DIRECT` in the PAC
script, so general browsing bypasses the proxy entirely — it's not just
"not decrypted," it's not routed to the proxy process at all. Restart your
browser (or the ChatGPT desktop app) afterward so it picks up the change.
To revert:

```powershell
.\target\release\agentctl.exe disable-proxy
```

To test manually without touching your real browser/OS proxy settings, you
can still point a single request at the proxy directly:

```powershell
curl.exe --ssl-no-revoke -x http://127.0.0.1:8443 https://api.anthropic.com/
```

(`--ssl-no-revoke` works around a Windows/Schannel quirk where certificates
from a private CA — ours — have no CRL/OCSP info, so revocation status can't
be checked; this doesn't affect trust, only that specific check.)

**4. Check status:**

```powershell
.\target\release\agentctl.exe status
```

## Seeing what requests come through, and their data

**Where the logs are:** `agentd` writes to both the console it's running in
and a daily-rotating file at `logging.file_dir` (default `logs/`, relative to
wherever you started `agentd` from) — e.g. `logs/agentd.log.2026-07-16`. Set
`file_dir` in `config.toml` under `[logging]` to change the location.

There are two separate logging levels, deliberately kept apart:

- **`info` (default)** — one line per DLP match: rule id, severity, action,
  destination host, and matched span *length* only. Safe to run in
  production; the matched text itself is never included.
- **`trace`** — a full dump of each intercepted request: method, URI,
  headers, and the **entire raw body**. This is opt-in and only intended for
  local debugging — it defeats the point of a DLP tool if left on in
  production, since it logs exactly the sensitive content the tool exists to
  protect.

To see full request data, scope `trace` to the proxy crate specifically
(leaving everything else at `info` keeps the output readable):

```powershell
$env:RUST_LOG = "agent_proxy=trace,info"
.\target\release\agentd.exe --config config.toml
```

Example output for a request to `POST http://127.0.0.1:9000/chat`:

```
TRACE agent_proxy::handler: raw request host="127.0.0.1" method=POST uri=http://127.0.0.1:9000/chat
  headers={"host": "127.0.0.1:9000", "content-type": "application/json", "content-length": "72"}
  body={"messages":[{"role":"user","content":"hello, nothing sensitive here"}]}
```

This line is emitted in `handle_request` (`crates/agent-proxy/src/handler.rs`)
right before the DLP scan runs, so it shows the body exactly as the engine
sees it — before any masking is applied.

## Configuration

`config.toml`:

```toml
[proxy]
listen_addr = "127.0.0.1"
listen_port = 8443
max_body_bytes = 10_485_760   # bodies larger than this are passed through unscanned
on_oversized = "log"          # log | block

[ca]
cert_path = "data/ca/root.crt"
key_path  = "data/ca/root.key"

[targets]
domains = ["chat.openai.com", "chatgpt.com", "claude.ai", "api.anthropic.com", ...]

[policy]
source = "policies/default.toml"

[logging]
level = "info"       # used only if RUST_LOG isn't set
file_dir = "logs"     # daily-rotating log file location

[sysnet]
pac_path = "data/proxy.pac"   # disk copy of the PAC (for inspection); agentd serves it over HTTP
pac_port = 8444               # loopback port agentd serves the PAC on (auto-config URL points here)
```

`policies/default.toml` — one `[[rule]]` per detection:

```toml
[[rule]]
id = "aws_access_key"
kind = "regex"           # regex | literal
label = "AWS_KEY"        # optional: type code in the mask token [MASKED-<label>-NNN]
pattern = 'AKIA[0-9A-Z]{16}'
severity = "critical"    # low | medium | high | critical
action = "block"         # log | mask | block
```

`label` is optional — it's the short type code that appears in the mask token
(`[MASKED-CC-001]`, `[MASKED-CNIC-002]`, …), with a sequence number that
restarts per request/frame. If omitted, the upper-cased `id` is used.

When multiple rules match a request, `block` wins over `mask` wins over `log`
(ties broken by severity). **Restart `agentd` after editing the policy file**
— it's loaded once at startup; hot-reload is not implemented yet (see
[Not yet implemented](#not-yet-implemented)).

## Tuning detection rules

Loose regexes cause false positives, and false positives on a tool that
masks/blocks traffic aren't just noisy — they can silently mutate or drop
legitimate requests. This already happened once during testing:

The original `credit_card` rule used `\b(?:\d[ -]?){13,16}\b` — any bare run
of 13–16 digits, optionally separated by spaces/dashes. Once real
`chatgpt.com` traffic was routed through the agent (see
[Run](#run) step 3), this matched **228 times in a few minutes**, 100% false
positives, all against ChatGPT's own Datadog RUM telemetry beacons
(`/ces/v1/t`, `/ces/v1/telemetry/intake`) — the pattern was matching epoch
millisecond timestamps and fragments of request/trace IDs, not card numbers,
and (since the rule's action is `mask`) was rewriting that telemetry data in
flight.

The fix was to require the actual shape a human-entered/pasted card number
has — four groups of four digits with a consistent separator — rather than
any loose digit run:

```toml
pattern = '\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,4}\b'
```

This still matches `4111 1111 1111 1111` / `4111-1111-1111-1111`, but no
longer matches bare digit runs like timestamps or UUID fragments. Verified
both directions with the local mock server (see [Testing](#testing)) before
rolling it back out.

**Takeaway for any new rule:** synthetic test strings passing isn't enough
proof a pattern is safe to ship. Run it against a stretch of real traffic
(`agentctl enable-proxy` + normal browsing, or `RUST_LOG=info` and watch
`logs/`) before trusting it, the same way this one was caught.

## Testing

```powershell
cargo test --workspace
```

Runs the DLP engine's unit tests (rule detection, masking, action precedence)
plus config/policy parsing tests. These don't require the proxy to be
running.

For an end-to-end check, run `agentd`, then send requests through it — see
[Run](#run) above. A local mock HTTP server is useful for inspecting exactly
what bytes a masked/blocked/logged request produces; a minimal example:

```python
import http.server

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        print(self.rfile.read(length))
        self.send_response(200); self.end_headers()

http.server.HTTPServer(("127.0.0.1", 9000), Handler).serve_forever()
```

Then, with `agentd` running:

```powershell
curl.exe -x http://127.0.0.1:8443 -X POST http://127.0.0.1:9000/chat `
  -H "Content-Type: application/json" `
  -d '{"messages":[{"role":"user","content":"key AKIAABCDEFGHIJKLMNOP"}]}'
```

This should return `403` and the mock server should receive nothing.

### WebSocket end-to-end check

The same idea works for the WebSocket path. Add `"localhost"` to
`[targets].domains` temporarily (or use a copy of the config), run a local
echo server (`pip install websockets websocket-client`):

```python
# ws_echo_server.py
import asyncio, websockets

async def handler(ws):
    async for msg in ws:
        print(f"SERVER RECEIVED: {msg!r}", flush=True)
        await ws.send(f"echo: {msg}")

async def main():
    async with websockets.serve(handler, "127.0.0.1", 9001):
        await asyncio.Future()

asyncio.run(main())
```

then connect through the proxy and send a frame that should be masked:

```python
import websocket
ws = websocket.create_connection(
    "ws://localhost:9001/",
    http_proxy_host="127.0.0.1", http_proxy_port=8443, proxy_type="http",
)
ws.send('{"content":"my card is 4111 1111 1111 1111"}')
print(ws.recv())   # echo: {"content":"my card is [MASKED-CC-001]"}
```

The proxy sniffs the bytes inside an intercepted `CONNECT` tunnel, so plain
`ws://` and TLS `wss://` both land on the same WebSocket DLP handler — this
test exercises the same code path real `wss://` traffic takes.

## Packaging

**Standing convention: every production build lands in `dist/`, zipped up
with its usage notes.** Run:

```powershell
.\scripts\package-release.ps1
```

This builds the release binaries, runs `cargo wix`, and produces
`dist\AI-SPM-DLP-Agent-<version>.zip` containing the `.msi` and
`packaging\INSTALL-NOTES.txt` (the tracked, hand-maintained recipient-facing
instructions - edit that file, not anything under `dist\`, which is
regenerated output and gitignored). This is the one command to run whenever
someone needs "the current build" - it always produces the same
self-contained deliverable in the same place, so there's nothing to
reconstruct by hand each time.

The script resolves the WiX Toolset's `bin` directory from the machine-level
`WIX` environment variable rather than `$env:WIX`, since a shell session
started before the WiX Toolset was installed won't have picked up that env
var - reading it via `[System.Environment]::GetEnvironmentVariable("WIX",
"Machine")` works regardless of when the current session started.

Manual/lower-level equivalent, if you need just the `.msi` without the
zip/notes bundle:

```powershell
cargo install cargo-wix        # one-time
cargo wix -p agent
```

Produces `target\wix\agent-0.1.0-x86_64.msi`. `wix\main.wxs` (generated by
`cargo wix init` and then hand-edited) ships `agentd.exe`, `agentctl.exe`,
`config.toml`, and `policies\default.toml` together under
`Program Files\agent\bin`, and wires two deferred custom actions into the
install/uninstall sequence: `agentctl.exe install --full --config
"[installed config.toml path]"` after files are installed, and `agentctl.exe
uninstall` before they're removed. Both need the elevation a `perMachine` MSI
already runs under. `data\` (the CA key/cert) and `logs\` aren't in the MSI's
file table, since they're written at runtime, not installed — so they're
intentionally left behind on uninstall (the same CA key survives a
reinstall/upgrade) rather than deleted; remove `Program Files\agent` by hand
if you want a fully clean slate.

Verified with a real `msiexec /i` / `msiexec /x` cycle: install lands the
files, starts the service (`Status: Running`, `StartType: Automatic`), and
installs the CA into the Local Machine store and Firefox's `policies.json`;
uninstall stops and deregisters the service and removes the CA cert
(including cleaning up more than one stale cert with a matching subject, if
present — see `agent-ca::remove_root_cert`).

Not done yet: the MSI is unsigned, so Windows SmartScreen will warn on first
run until it's signed with a real code-signing certificate — that's a
certificate-acquisition step, not something fixable in the build.

## Security notes

- The CA private key is currently stored as a plaintext PEM file
  (`data/ca/key_path`, `Program Files\agent\bin\data\ca\root.key` in a
  production install). DPAPI encryption at rest is a follow-up item (see
  below).
- `agentctl install --full` installs the CA into the **Local Machine**
  Trusted Root store — every account on the box (and the ChatGPT desktop app,
  and Firefox via its enterprise policy) trusts it, not just the user who ran
  the installer. This is a wider blast radius than the granular `install-ca`
  subcommand's current-user-only scope (kept for dev/test): if the CA private
  key were ever exfiltrated, it can mint a trusted certificate for *any*
  hostname on the machine, not just the configured AI domains — there's no
  certificate name-constraint tying it to `[targets].domains`. Worth
  hardening (rcgen supports X.509 name constraints) before a wide rollout,
  independent of the DPAPI-at-rest item above.
- Deploying this tool means decrypting employees' traffic to AI services.
  Confirm scope and disclosure requirements with legal/compliance before any
  real rollout — this is a policy question, not something enforced in code.

## Not yet implemented

- Code signing for the `.msi` (see [Packaging](#packaging))
- Windows Event Log sink for block/critical-severity events
- DPAPI-encrypted CA private key at rest
- CA certificate name constraints (scope the CA to `[targets].domains` rather
  than trusting it for any hostname — see [Security notes](#security-notes))
- Policy hot-reload
- Machine-wide *proxy auto-config* for other user sessions and
  services/SYSTEM-level processes (today's per-user `agentctl enable-proxy`,
  via WinINet `AutoConfigURL`, is unchanged by `install --full` — a
  machine-wide WinHTTP equivalent is still a separate follow-up; see
  ROADMAP.md's "Machine-wide option")

## Author

Designed and developed by **Nabeel Qadri** — <nabeel.qadri@sandyapps.co>.
