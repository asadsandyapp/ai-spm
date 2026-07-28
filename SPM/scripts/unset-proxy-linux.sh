#!/usr/bin/env bash
set -euo pipefail

if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.system.proxy mode 'none'
  echo "System proxy disabled."
else
  echo "Disable proxy manually in browser settings."
fi
