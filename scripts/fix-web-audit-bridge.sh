#!/usr/bin/env bash
# Fix web-MITM → Admin Audit: install agent with /web-audit localhost bridge.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEW="${ROOT}/agent/target/release/agent-service"
DST="/usr/local/bin/agent-service"
ENV_FILE="/etc/ai-spm/agent.env"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi
if [[ ! -x "${NEW}" ]]; then
  echo "Missing ${NEW} — run: cd agent && cargo build --release -p agent-service" >&2
  exit 1
fi

install -m 0755 "${NEW}" "${DST}"
# Ensure local audit bridge is enabled even on older configs.
if [[ -f "${ENV_FILE}" ]]; then
  if grep -q '^AISPM_LOCAL_API_ENABLED=' "${ENV_FILE}"; then
    sed -i 's/^AISPM_LOCAL_API_ENABLED=.*/AISPM_LOCAL_API_ENABLED=true/' "${ENV_FILE}"
  else
    echo 'AISPM_LOCAL_API_ENABLED=true' >> "${ENV_FILE}"
  fi
fi
systemctl restart ai-spm-agent
sleep 1
systemctl is-active ai-spm-agent
if ss -ltn | grep -q '127.0.0.1:8092'; then
  echo "OK: local web-audit bridge listening on 127.0.0.1:8092"
else
  echo "WARN: 8092 not listening — check /var/log/ai-spm/agent.log" >&2
  exit 1
fi
echo "Next: new ChatGPT chat → Admin Audit / Threat Feed should show masked prompts."
