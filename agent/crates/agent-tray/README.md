# agent-tray — Tauri 2 System Tray

Real Tauri 2 tray app for the AI-SPM endpoint agent (no longer the placeholder
stub — see git history if you need the old stub binary).

## What it does

- Polls `agent-service`'s `local_api` `GET /status` every 5s over plain
  loopback HTTP (default `http://127.0.0.1:8092/status`, override with
  `AISPM_STATUS_URL`) rather than linking `agent-core` directly, so this
  crate stays free of the BoringSSL/MITM dependency chain the service needs.
- Reflects three states in the tray tooltip + menu:
  - **Protected** — heartbeat healthy, no recent policy block
  - **Disconnected** — `/status` unreachable, or the agent reports
    `connected: false` (heartbeat failing)
  - **Blocked (recent policy block)** — a block happened in the last 30s
    (`BLOCK_DISPLAY_WINDOW_MS` in `src/main.rs`)
- Fires a desktop notification (`tauri-plugin-notification`) the first time a
  *new* block event appears — not on every poll, and not for a block that was
  already on record when the tray started.

## Important caveat

`local_api` (and therefore `/status`) only starts when
`AISPM_LOCAL_API_ENABLED=1` or transparent mode is on (see
`agent-service/src/main.rs`). If neither is set, the tray will correctly show
**Disconnected** forever — that's not a tray bug, it's the status source not
running. Enable one of those on the agent if you want to see Protected.

## Build

```bash
cargo build -p agent-tray --release
```

Requires the Tauri 2 native prerequisites for your platform (WebView2 on
Windows — usually already present via Edge; `libwebkit2gtk` + friends on
Linux, see the [Tauri prerequisites docs](https://v2.tauri.app/start/prerequisites/)).
This crate could not be built/run in the environment this was scaffolded in
(no display to verify tray behavior) — build and exercise it locally before
relying on it: confirm the three states actually change the tray tooltip/menu
and that a real policy block triggers a notification.

## Icons

`icons/*.png` are placeholder solid-color squares generated for this scaffold
— replace with real branded assets before shipping, and run `tauri icon` (or
add `.ico`/`.icns` manually) if you start producing installer bundles, since
`tauri.conf.json`'s `bundle.icon` currently only lists PNGs.

## Next Steps

1. Replace placeholder icons with real branded assets; generate `.ico`/`.icns`
   via `tauri icon` for installer bundling.
2. Package tray + service together in the WiX MSI
   (`agent/installer/wix/`) so employees get both from one install.
3. Consider swapping the time-window "Blocked" display for an explicit
   click-to-acknowledge once there's a tray window/dialog to click into.
