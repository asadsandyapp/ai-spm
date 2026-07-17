#!/usr/bin/env bash
# Deploy extension 1.0.9 + agent with hook-ping (requires root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo:  sudo $0" >&2
  exit 1
fi

echo "→ Syncing extension sources to /opt/ai-spm/browser-extension"
install -d -m 0755 /opt/ai-spm/browser-extension
install -m 0644 \
  "$ROOT/browser-extension/manifest.json" \
  "$ROOT/browser-extension/inject.js" \
  "$ROOT/browser-extension/bridge.js" \
  "$ROOT/browser-extension/background.js" \
  /opt/ai-spm/browser-extension/

echo "→ Installing agent-service binary"
install -m 0755 "$ROOT/agent/target/release/agent-service" /usr/local/bin/agent-service
systemctl restart ai-spm-agent
sleep 2
systemctl is-active ai-spm-agent

echo "→ Repackaging + refreshing managed browser extension"
bash "$ROOT/scripts/install-agent.sh" refresh-extensions

echo
echo "Done. Next:"
echo "  1. Fully quit Chrome (all windows) and reopen"
echo "  2. chrome://extensions → confirm AI-SPM Prompt Guard is v1.0.9"
echo "  3. Open chatgpt.com or claude.ai → DevTools console should show:"
echo "       [AI-SPM] Prompt Guard hooks active on …"
echo "  4. Send:  email jane@acme.com SSN 123-45-6789"
echo "  5. Check:  grep -E 'hook|inspect|masked' /var/log/ai-spm/agent.log | tail"
echo "  6. Admin Audit should show masked content (not the raw email/SSN)"
echo
echo "Note: the chat box still shows what you typed; masking is on the outbound request."
