#!/usr/bin/env bash
# Install the AI-SPM MITM root CA into the OS and browser trust stores (Linux).
set -euo pipefail

CA_DIR="${1:-${HOME}/.local/share/ai-spm/mitm}"
CA_CERT="${CA_DIR}/mitm-ca.crt"

if [[ ! -f "${CA_CERT}" ]]; then
  echo "MITM CA not found at ${CA_CERT}"
  echo "Start the agent once to generate it, or pass the CA directory as an argument."
  exit 1
fi

echo "Installing MITM CA from ${CA_CERT}..."

# System trust store (requires sudo)
if command -v update-ca-certificates >/dev/null 2>&1; then
  echo "→ Installing into system CA store (sudo required)..."
  sudo cp "${CA_CERT}" /usr/local/share/ca-certificates/ai-spm-mitm.crt
  sudo update-ca-certificates
  echo "  System trust store updated."
fi

# Firefox / Chrome (NSS) user profile
if command -v certutil >/dev/null 2>&1; then
  NSSDB="${HOME}/.pki/nssdb"
  if [[ -d "${NSSDB}" ]]; then
    echo "→ Installing into NSS database (${NSSDB})..."
    certutil -d "sql:${NSSDB}" -A -t "C,," -n "AI-SPM MITM CA" -i "${CA_CERT}" 2>/dev/null || \
      certutil -d "${NSSDB}" -A -t "C,," -n "AI-SPM MITM CA" -i "${CA_CERT}"
    echo "  NSS trust store updated (Chrome/Firefox on Linux)."
  fi
fi

echo ""
echo "Done. Configure your browser/system to use the agent proxy:"
echo "  HTTP/HTTPS proxy: 127.0.0.1:8081"
echo ""
echo "Then restart the browser and test ChatGPT — emails should be masked."
