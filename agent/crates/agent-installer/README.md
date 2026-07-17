# agent-installer — Linux guided enrollment launcher

Binary name: `aispm-agent-installer`.

Shipped inside Admin → **Download Agent** sealed `.run` installers with:

- `enrollment.env` (org-bound gateway URL + org token)
- `aispm-agent-installer-gui.py` (Tkinter enterprise wizard)
- `install-agent.sh` (privileged engine)

## Build

```bash
cd agent
cargo build -p agent-installer --release
```

## Tauri 2 (future)

Replace the Tkinter GUI with a Tauri 2 shell that hosts the same wizard steps and
still elevates `install-agent.sh` via `pkexec`. Keep enrollment.env contract stable.
