#!/usr/bin/env bash
# Generate development mTLS CA and certificates for AI-SPM agents.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/../infrastructure/certs"
DAYS="${CERT_DAYS:-365}"

mkdir -p "${CERT_DIR}"

if [[ ! -f "${CERT_DIR}/ca.key" ]]; then
  echo "Generating CA..."
  openssl req -x509 -newkey rsa:4096 -sha256 -days "${DAYS}" -nodes \
    -keyout "${CERT_DIR}/ca.key" \
    -out "${CERT_DIR}/ca.crt" \
    -subj "/CN=AI-SPM Dev CA/O=AI-SPM/C=US"
fi

generate_agent_cert() {
  local org_id="$1"
  local agent_id="$2"
  local name="agent-${org_id}-${agent_id}"

  openssl genrsa -out "${CERT_DIR}/${name}.key" 2048

  openssl req -new \
    -key "${CERT_DIR}/${name}.key" \
    -out "${CERT_DIR}/${name}.csr" \
    -subj "/CN=${name}/O=AI-SPM Agent"

  cat > "${CERT_DIR}/${name}.ext" <<EOF
subjectAltName = URI:spiffe://aispm.io/org/${org_id}/agent/${agent_id}
extendedKeyUsage = clientAuth
EOF

  openssl x509 -req \
    -in "${CERT_DIR}/${name}.csr" \
    -CA "${CERT_DIR}/ca.crt" \
    -CAkey "${CERT_DIR}/ca.key" \
    -CAcreateserial \
    -out "${CERT_DIR}/${name}.crt" \
    -days "${DAYS}" \
    -sha256 \
    -extfile "${CERT_DIR}/${name}.ext"

  rm -f "${CERT_DIR}/${name}.csr" "${CERT_DIR}/${name}.ext"
  echo "Generated ${CERT_DIR}/${name}.crt"
}

ORG_ID="${1:-00000000-0000-0000-0000-000000000001}"
AGENT_ID="${2:-00000000-0000-0000-0000-000000000002}"

generate_agent_cert "${ORG_ID}" "${AGENT_ID}"

echo ""
echo "CA certificate: ${CERT_DIR}/ca.crt"
echo "Agent certificate: ${CERT_DIR}/agent-${ORG_ID}-${AGENT_ID}.crt"
echo "Agent private key: ${CERT_DIR}/agent-${ORG_ID}-${AGENT_ID}.key"
echo ""
echo "Kong mTLS: mount ca.crt as trusted CA for client verification."
