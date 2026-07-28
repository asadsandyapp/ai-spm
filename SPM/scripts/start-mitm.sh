#!/usr/bin/env bash
# Start the HTTPS MITM proxy that masks emails in ChatGPT web traffic.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${MITM_PORT:-8800}"
VENV_MITM="${ROOT}/.venv/bin/mitmdump"

if [[ -x "${VENV_MITM}" ]]; then
  MITMDUMP="${VENV_MITM}"
elif command -v mitmdump >/dev/null 2>&1; then
  MITMDUMP="$(command -v mitmdump)"
else
  echo "mitmproxy not found."
  echo ""
  echo "Install into the project venv (recommended on Ubuntu/Debian):"
  echo "  cd ${ROOT}"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install mitmproxy"
  echo ""
  echo "Or with pipx:"
  echo "  pipx install mitmproxy"
  exit 1
fi

echo "Starting MITM proxy on port ${PORT}"
echo "Using: ${MITMDUMP}"
echo ""
echo "NEXT STEPS (required or ChatGPT traffic will NOT be intercepted):"
echo "  1. Trust the CA:  bash scripts/trust-ca-linux.sh"
echo "  2. Set browser/system proxy to 127.0.0.1:${PORT}"
echo "  3. Open https://chatgpt.com and send a prompt with an email"
echo ""

exec "${MITMDUMP}" \
  -s "${ROOT}/scripts/chatgpt_mitm.py" \
  --listen-host 0.0.0.0 \
  --listen-port "${PORT}" \
  --set block_global=false
