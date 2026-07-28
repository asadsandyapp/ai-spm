#!/usr/bin/env bash
# Deploy latest web_ui_mitm.py to the running AI-SPM mitmproxy service.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${ROOT}/scripts/mitmproxy/web_ui_mitm.py"
DST="/opt/ai-spm/mitmproxy/web_ui_mitm.py"
INSTALLER="${ROOT}/scripts/install-agent.sh"
UNIT="ai-spm-web-mitm.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi
if [[ ! -f "${SRC}" ]]; then
  echo "Missing ${SRC}" >&2
  exit 1
fi

# A clean endpoint has no web-MITM unit yet. Install the complete service,
# venv, CA trust, and desktop proxy instead of trying to restart a missing unit.
if ! systemctl cat "${UNIT}" >/dev/null 2>&1 \
   || [[ ! -x /opt/ai-spm/mitmproxy-venv/bin/mitmdump ]]; then
  if [[ ! -x "${INSTALLER}" ]]; then
    echo "Missing ${INSTALLER}" >&2
    exit 1
  fi
  echo "Web MITM service is missing — installing complete SPM-style web path..."
  exec "${INSTALLER}" web-mitm
fi

install -d -m 0755 /opt/ai-spm/mitmproxy
install -m 0644 "${SRC}" "${DST}"
if [[ -f "${ROOT}/scripts/mitmproxy/pii_rules.py" ]]; then
  install -m 0644 "${ROOT}/scripts/mitmproxy/pii_rules.py" /opt/ai-spm/mitmproxy/pii_rules.py
fi
if [[ -f "${ROOT}/scripts/mitmproxy/start-web-mitm.sh" ]]; then
  install -m 0755 "${ROOT}/scripts/mitmproxy/start-web-mitm.sh" /opt/ai-spm/mitmproxy/start-web-mitm.sh
fi
chown aispm:aispm "${DST}" /opt/ai-spm/mitmproxy/pii_rules.py /opt/ai-spm/mitmproxy/start-web-mitm.sh 2>/dev/null || true
systemctl restart "${UNIT}"
sleep 1
systemctl is-active "${UNIT}"
echo "Deployed $(wc -l < "${DST}") lines → ${DST}"
echo "Next: fully quit browser, NEW ChatGPT chat."
echo "  Normal prompts should stream fully (no 'Connection interrupted')."
echo "  Sensitive prompts should still mask (***@***.com)."
echo "  Expect logs: [AI-SPM] Masked N PII hit(s) ... (X.XXms)"
echo "  sudo journalctl -u ai-spm-web-mitm -f"
echo "  OR: sudo tail -f /var/log/ai-spm/web-mitm.log"
