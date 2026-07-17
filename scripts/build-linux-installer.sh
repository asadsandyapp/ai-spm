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
if [[ -f "${ROOT}/scripts/reconcile-browser-extensions.sh" ]]; then
  install -m 0755 "${ROOT}/scripts/reconcile-browser-extensions.sh" \
    "${OUT}/reconcile-browser-extensions.sh"
fi

# Managed browser extension (Chrome/Edge/Brave/… + Firefox) — required for CF web UIs.
# Sealed Admin download embeds this so install works without a git checkout.
EXT_SRC="${ROOT}/browser-extension"
if [[ -d "${EXT_SRC}" && -f "${EXT_SRC}/manifest.json" ]]; then
  echo "→ Staging browser-extension for managed install…"
  rm -rf "${OUT}/browser-extension"
  mkdir -p "${OUT}/browser-extension"
  install -m 0644 "${EXT_SRC}/manifest.json" "${OUT}/browser-extension/manifest.json"
  for f in "${EXT_SRC}"/*.js; do
    [[ -f "${f}" ]] || continue
    install -m 0644 "${f}" "${OUT}/browser-extension/$(basename "${f}")"
  done
  if [[ -f "${EXT_SRC}/ai-spm-prompt-guard-signed.xpi" ]]; then
    install -m 0644 "${EXT_SRC}/ai-spm-prompt-guard-signed.xpi" \
      "${OUT}/browser-extension/ai-spm-prompt-guard-signed.xpi"
  elif [[ -f "${ROOT}/dist/ai-spm-prompt-guard-signed.xpi" ]]; then
    install -m 0644 "${ROOT}/dist/ai-spm-prompt-guard-signed.xpi" \
      "${OUT}/browser-extension/ai-spm-prompt-guard-signed.xpi"
  fi
else
  echo "WARNING: browser-extension/ missing — sealed install will fail extension deploy." >&2
fi

# One vendor RSA key → stable Chromium extension ID on every endpoint (AGENTS.md).
KEY="${OUT}/extension-key.pem"
if [[ ! -f "${KEY}" ]]; then
  echo "→ Generating stable Chromium extension signing key…"
  openssl genrsa -out "${KEY}" 2048 2>/dev/null
  chmod 600 "${KEY}"
fi

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
