#!/usr/bin/env bash
# Start SPM-style mitmproxy for ChatGPT / Claude / Gemini web UI masking.
#
# Performance: only AI web hosts are TLS-intercepted. All other HTTPS
# (Cursor, Google, CDN assets, etc.) is tunneled without decryption.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${AISPM_WEB_MITM_PORT:-8800}"
CONFDIR="${AISPM_WEB_MITM_CONFDIR:-/etc/ai-spm/mitmproxy}"
ADDON="${ROOT}/web_ui_mitm.py"
VENV_MITM="${AISPM_WEB_MITM_VENV:-/opt/ai-spm/mitmproxy-venv}/bin/mitmdump"

# Only MITM these hosts. Everything else is a fast CONNECT tunnel.
ALLOW_HOSTS="${AISPM_WEB_MITM_ALLOW_HOSTS:-.*chatgpt\\.com:443$|.*chat\\.openai\\.com:443$|.*claude\\.ai:443$|.*gemini\\.google\\.com:443$|.*openai\\.com:443$}"

if [[ -x "${VENV_MITM}" ]]; then
  MITMDUMP="${VENV_MITM}"
elif command -v mitmdump >/dev/null 2>&1; then
  MITMDUMP="$(command -v mitmdump)"
else
  echo "mitmdump not found. Install during agent setup or: pip install mitmproxy" >&2
  exit 1
fi

mkdir -p "${CONFDIR}"
# stream_large_bodies: fallback for large bodies; addon also forces SSE streaming
# via responseheaders so ChatGPT answers are not buffered (avoids
# "Connection interrupted" on long non-PII replies).
exec "${MITMDUMP}" \
  -s "${ADDON}" \
  --listen-host 127.0.0.1 \
  --listen-port "${PORT}" \
  --set "confdir=${CONFDIR}" \
  --set block_global=false \
  --set "allow_hosts=${ALLOW_HOSTS}" \
  --set stream_large_bodies=512k \
  --set websocket=true
