#!/usr/bin/env bash
# Install mitmproxy's CA certificate so the browser allows HTTPS interception.
set -euo pipefail

MITM_DIR="${HOME}/.mitmproxy"
CERT="${MITM_DIR}/mitmproxy-ca-cert.pem"

if [[ ! -f "${CERT}" ]]; then
  echo "CA cert not found at ${CERT}"
  echo "Run mitmdump once first (bash scripts/start-mitm.sh), then Ctrl+C and rerun this."
  exit 1
fi

echo "Installing mitmproxy CA certificate..."
echo "You may be prompted for your sudo password."
echo ""

if command -v trust >/dev/null 2>&1; then
  sudo cp "${CERT}" /usr/local/share/ca-certificates/mitmproxy.crt
  sudo update-ca-certificates
  echo "Done (system trust store)."
elif command -v update-ca-trust >/dev/null 2>&1; then
  sudo cp "${CERT}" /etc/pki/ca-trust/source/anchors/mitmproxy.crt
  sudo update-ca-trust
  echo "Done (system trust store)."
else
  echo "Could not find trust/update-ca-trust."
  echo "Manually import this file into your browser as a trusted root CA:"
  echo "  ${CERT}"
  echo ""
  echo "Firefox: Settings → Privacy & Security → Certificates → View Certificates → Authorities → Import"
  echo "Chrome:  Settings → Privacy → Security → Manage certificates → Authorities → Import"
  exit 1
fi

if command -v certutil >/dev/null 2>&1; then
  NSS_DB="${HOME}/.pki/nssdb"
  mkdir -p "${NSS_DB}"

  # Chrome/Chromium on Linux may use this per-user NSS database instead of
  # relying only on the operating system trust store.
  if [[ ! -f "${NSS_DB}/cert9.db" ]]; then
    certutil -N -d "sql:${NSS_DB}" --empty-password
  fi
  certutil -D -d "sql:${NSS_DB}" -n mitmproxy 2>/dev/null || true
  certutil -A -d "sql:${NSS_DB}" -n mitmproxy -t "C,," -i "${CERT}"
  echo "Done (Chrome/Chromium NSS trust store)."
else
  echo "Warning: certutil is unavailable; Chrome may require manual CA import."
fi

echo ""
echo "Fully close every browser process, then reopen the browser."
