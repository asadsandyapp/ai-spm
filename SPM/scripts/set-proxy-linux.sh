#!/usr/bin/env bash
# Enable system HTTP/HTTPS proxy (GNOME). Disable with scripts/unset-proxy-linux.sh
set -euo pipefail

PORT="${MITM_PORT:-8800}"
HOST="${MITM_HOST:-127.0.0.1}"

if ! command -v gsettings >/dev/null 2>&1; then
  echo "gsettings not found. Set proxy manually in browser:"
  echo "  HTTP proxy:  ${HOST}:${PORT}"
  echo "  HTTPS proxy: ${HOST}:${PORT}"
  exit 1
fi

gsettings set org.gnome.system.proxy mode 'manual'
gsettings set org.gnome.system.proxy.http host "${HOST}"
gsettings set org.gnome.system.proxy.http port "${PORT}"
gsettings set org.gnome.system.proxy.https host "${HOST}"
gsettings set org.gnome.system.proxy.https port "${PORT}"

echo "System proxy enabled: ${HOST}:${PORT}"
echo "Most browsers on GNOME will use this automatically."
