# agent-tray — Tauri 2 Placeholder

This crate is a **stub binary** for the AI-SPM endpoint agent system tray UI.

## Planned Integration (Tauri 2)

Per `IMPLEMENTATION_ROADMAP.md` (REQ-001, MOD-12), the tray app will:

- Show agent connection status (online / offline / blocked)
- Display policy block notifications to employees
- Link to IT support documentation
- Run alongside `agent-service` on Windows workstations

## Next Steps

1. Initialize a Tauri 2 project in this crate (`cargo tauri init`)
2. Share `agent-core` for gateway status via IPC (named pipe on Windows, Unix socket on Linux)
3. Subscribe to block events pushed from `agent-service`
4. Package tray + service in the WiX MSI (`agent/installer/wix/`)

## Build (stub)

```bash
cargo build -p agent-tray --release
```

The stub prints a startup log message and exits. No GUI is bundled yet.
