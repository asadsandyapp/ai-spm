#!/usr/bin/env bash
#
# Build Linux enrollment installer assets for Admin → Download Agent.
#
# Outputs to dist/linux-installer/ (mounted into the API container as
# /opt/ai-spm/installer-linux).
#
#   ./scripts/build-linux-installer.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${AISPM_INSTALLER_OUT:-${ROOT}/dist/linux-installer}"
GUI_SRC="${ROOT}/agent/installer/linux-gui"
AGENT_DIR="${ROOT}/agent"

echo "→ Building Linux installer assets into ${OUT}"
# Do NOT `rm -rf` the directory itself while Docker bind-mounts it — that
# orphans the container mount (empty view until recreate). Clear contents only.
mkdir -p "${OUT}"
find "${OUT}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

# Guided UI + shell launcher
install -m 0755 "${GUI_SRC}/aispm-agent-installer" "${OUT}/aispm-agent-installer"
install -m 0755 "${GUI_SRC}/aispm-agent-installer-gui.py" "${OUT}/aispm-agent-installer-gui.py"

# Privileged engine
install -m 0755 "${ROOT}/scripts/install-agent.sh" "${OUT}/install-agent.sh"

# SPM-style mitmproxy addon for ChatGPT/Claude/Gemini web UIs (required).
if [[ ! -f "${ROOT}/scripts/mitmproxy/web_ui_mitm.py" || ! -f "${ROOT}/scripts/mitmproxy/start-web-mitm.sh" || ! -f "${ROOT}/scripts/mitmproxy/pii_rules.py" ]]; then
  echo "ERROR: scripts/mitmproxy/{web_ui_mitm.py,start-web-mitm.sh,pii_rules.py} required for endpoint install." >&2
  exit 1
fi
echo "→ Staging mitmproxy web UI masking scripts…"
mkdir -p "${OUT}/mitmproxy"
install -m 0644 "${ROOT}/scripts/mitmproxy/web_ui_mitm.py" "${OUT}/mitmproxy/web_ui_mitm.py"
install -m 0644 "${ROOT}/scripts/mitmproxy/pii_rules.py" "${OUT}/mitmproxy/pii_rules.py"
install -m 0755 "${ROOT}/scripts/mitmproxy/start-web-mitm.sh" "${OUT}/mitmproxy/start-web-mitm.sh"

# Prefer release agent-service; build if missing
BIN_SRC="${AGENT_DIR}/target/release/agent-service"
if [[ ! -x "${BIN_SRC}" ]]; then
  echo "→ Building agent-service (release)…"
  (cd "${AGENT_DIR}" && cargo build --release -p agent-service)
fi
if [[ -x "${BIN_SRC}" ]]; then
  install -m 0755 "${BIN_SRC}" "${OUT}/agent-service"
else
  echo "WARNING: agent-service binary not found — ZIP will build-from-source on target host." >&2
fi

# Optional Rust launcher overlay (same name) when available
INSTALLER_BIN="${AGENT_DIR}/target/release/aispm-agent-installer"
if [[ ! -x "${INSTALLER_BIN}" ]]; then
  echo "→ Building aispm-agent-installer launcher…"
  (cd "${AGENT_DIR}" && cargo build --release -p agent-installer) || true
fi
if [[ -x "${INSTALLER_BIN}" ]]; then
  # Keep shell launcher as aispm-agent-installer.sh; Rust binary becomes primary entrypoint
  mv "${OUT}/aispm-agent-installer" "${OUT}/aispm-agent-installer.sh"
  install -m 0755 "${INSTALLER_BIN}" "${OUT}/aispm-agent-installer"
  # Teach Rust binary about shell helper name used in crate
  install -m 0755 "${OUT}/aispm-agent-installer.sh" "${OUT}/run-install-cli.sh"
fi

# Sample enrollment template (not used by API — API synthesizes per-tenant file)
cat > "${OUT}/enrollment.env.example" <<'EOF'
# Example only — real packages get enrollment.env from Admin Download Agent.
AISPM_GATEWAY_URL=http://localhost:8090
AISPM_ORG_ID=00000000-0000-0000-0000-000000000000
AISPM_ORG_TOKEN=replace-with-rotated-org-token-min-32-chars
AISPM_ORG_NAME=Example Corp
EOF

# Template README (API also writes README.txt into ZIP)
cp "${ROOT}/agent/crates/agent-installer/README.md" "${OUT}/INSTALLER.md" 2>/dev/null || true

echo "✓ Linux installer assets ready:"
ls -la "${OUT}"
echo
echo "API serves these via AISPM_INSTALLER_LINUX_DIR=${OUT}"
echo "Compose mounts dist/linux-installer → /opt/ai-spm/installer-linux"
