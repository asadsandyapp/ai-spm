#!/usr/bin/env bash
#
# Enterprise AI-SPM endpoint agent installer for Linux.
#
# Installs a system service that transparently intercepts outbound HTTPS at the
# network layer (iptables REDIRECT). All browsers and apps are covered — no
# browser proxy configuration required.
#
#   sudo ./scripts/install-agent.sh
#   sudo ./scripts/install-agent.sh uninstall   # full removal (also: stop)
#   sudo ./scripts/install-agent.sh refresh-extensions
#
# Configuration (env vars):
#   AISPM_GATEWAY_URL          default http://localhost:8090
#   AISPM_ORG_ID               default 2117eef6-a519-47d5-bd6b-8a7357dafbb7
#   AISPM_ORG_TOKEN            default dev-org-token-please-change-32chars-minimum
#   AISPM_TRANSPARENT_LISTEN   default 0.0.0.0:9443
set -euo pipefail

# pkexec/PolicyKit uses a sanitized PATH that often omits /usr/sbin (iptables) —
# missing commands then abort this script with exit 127. Keep a full admin PATH.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${PATH:+:$PATH}"

BIN_NAME="agent-service"
INSTALL_BIN="/usr/local/bin/${BIN_NAME}"
SERVICE_USER="aispm"
SERVICE_NAME="ai-spm-agent"
ENV_FILE="/etc/ai-spm/agent.env"
CA_DIR="/etc/ai-spm/certs/mitm"
CA_CERT="${CA_DIR}/mitm-ca.crt"
SYSTEM_CA_PATH="/usr/local/share/ca-certificates/ai-spm-mitm.crt"
LOG_FILE="/var/log/ai-spm/agent.log"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
EXT_INSTALL_DIR="/opt/ai-spm/browser-extension"
EXT_KEY="/opt/ai-spm/extension-key.pem"
EXT_CRX="/opt/ai-spm/ai-spm-prompt-guard.crx"
EXT_XPI="/opt/ai-spm/ai-spm-prompt-guard.xpi"
EXT_XPI_SIGNED="/opt/ai-spm/ai-spm-prompt-guard-signed.xpi"
EXT_ID_FILE="/opt/ai-spm/extension-id"
CHROME_POLICY_DIR="/etc/opt/chrome/policies/managed"
RECONCILE_SCRIPT="/usr/local/lib/ai-spm/reconcile-browser-extensions.sh"
INSTALLER_LIB="/usr/local/lib/ai-spm/install-agent.sh"
UNINSTALL_BIN="/usr/local/sbin/aispm-agent-uninstall"
RECONCILE_SERVICE="/etc/systemd/system/ai-spm-browser-reconcile.service"
RECONCILE_TIMER="/etc/systemd/system/ai-spm-browser-reconcile.timer"

REAL_USER="${SUDO_USER:-}"
if [[ -z "${REAL_USER}" || "${REAL_USER}" == "root" ]]; then
  # pkexec sets PKEXEC_UID but not always SUDO_USER.
  if [[ -n "${PKEXEC_UID:-}" ]]; then
    REAL_USER="$(getent passwd "${PKEXEC_UID}" | cut -d: -f1 || true)"
  fi
fi
if [[ -z "${REAL_USER}" || "${REAL_USER}" == "root" ]]; then
  REAL_USER="${USER}"
fi
if [[ "${REAL_USER}" == "root" ]]; then
  echo "ERROR: run as your desktop user via sudo/pkexec, e.g.  sudo ./scripts/install-agent.sh" >&2
  exit 1
fi
REAL_HOME="$(getent passwd "${REAL_USER}" | cut -d: -f6)"
REAL_UID="$(id -u "${REAL_USER}")"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer package layout (sealed .run / enrollment package) over living inside the git repo.
if [[ -f "${SCRIPT_DIR}/enrollment.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/enrollment.env"
  set +a
fi
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGENT_DIR="${AISPM_AGENT_DIR:-${REPO_ROOT}/agent}"
PACKAGE_BIN="${SCRIPT_DIR}/agent-service"

# Resolve extension source next to install-agent.sh (sealed package) or from repo checkout.
resolve_extension_src() {
  if [[ -d "${SCRIPT_DIR}/browser-extension" && -f "${SCRIPT_DIR}/browser-extension/manifest.json" ]]; then
    echo "${SCRIPT_DIR}/browser-extension"
  elif [[ -d "${REPO_ROOT}/browser-extension" && -f "${REPO_ROOT}/browser-extension/manifest.json" ]]; then
    echo "${REPO_ROOT}/browser-extension"
  else
    echo ""
  fi
}

resolve_reconcile_script_src() {
  if [[ -f "${SCRIPT_DIR}/reconcile-browser-extensions.sh" ]]; then
    echo "${SCRIPT_DIR}/reconcile-browser-extensions.sh"
  elif [[ -f "${REPO_ROOT}/scripts/reconcile-browser-extensions.sh" ]]; then
    echo "${REPO_ROOT}/scripts/reconcile-browser-extensions.sh"
  else
    echo ""
  fi
}

GATEWAY_URL="${AISPM_GATEWAY_URL:-http://localhost:8090}"
ORG_ID="${AISPM_ORG_ID:-2117eef6-a519-47d5-bd6b-8a7357dafbb7}"
ORG_TOKEN="${AISPM_ORG_TOKEN:-dev-org-token-please-change-32chars-minimum}"
TRANSPARENT_LISTEN="${AISPM_TRANSPARENT_LISTEN:-0.0.0.0:9443}"
TRANSPARENT_PORT="${TRANSPARENT_LISTEN##*:}"
SOCKET_MARK="${AISPM_SOCKET_MARK:-0x4149534d}"

QUIC_COMMENT="ai-spm-quic-block"
IPTABLES_CHAIN="AISPM"
IPTABLES_COMMENT="ai-spm-transparent"

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: run with sudo." >&2
    exit 1
  fi
}

as_user() {
  sudo -u "${REAL_USER}" \
    XDG_RUNTIME_DIR="/run/user/${REAL_UID}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${REAL_UID}/bus" \
    HOME="${REAL_HOME}" \
    "$@"
}

browser_installed() {
  local browser="$1"
  case "$browser" in
    chrome)
      command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1
      ;;
    chromium)
      command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1
      ;;
    edge)
      command -v microsoft-edge >/dev/null 2>&1 || command -v microsoft-edge-stable >/dev/null 2>&1
      ;;
    brave)
      command -v brave-browser >/dev/null 2>&1
      ;;
    vivaldi)
      command -v vivaldi >/dev/null 2>&1 || [[ -x "/opt/vivaldi/vivaldi" ]]
      ;;
    firefox)
      command -v firefox >/dev/null 2>&1 || [[ -d "/etc/firefox" ]]
      ;;
    *)
      return 1
      ;;
  esac
}

print_browser_status() {
  local name="$1"
  local installed="$2"
  local policy_path="$3"
  local extra_path="${4:-}"
  if browser_installed "$installed"; then
    echo "   • ${name}: detected"
    echo "     policy: ${policy_path}"
    if [[ -n "${extra_path}" ]]; then
      echo "     install: ${extra_path}"
    fi
  else
    echo "   • ${name}: not detected"
  fi
}

ensure_service_user() {
  if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    echo "→ Creating system user ${SERVICE_USER}..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
  fi
  mkdir -p /etc/ai-spm/certs/mitm /var/log/ai-spm
  chown -R "${SERVICE_USER}:${SERVICE_USER}" /etc/ai-spm /var/log/ai-spm
}

install_dependencies() {
  echo "→ Installing dependencies..."
  if command -v certutil >/dev/null 2>&1 && command -v update-ca-certificates >/dev/null 2>&1 \
     && command -v iptables >/dev/null 2>&1 && command -v cmake >/dev/null 2>&1 \
     && command -v clang >/dev/null 2>&1; then
    echo "  Dependencies already present."
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      ca-certificates libnss3-tools iptables cmake clang libclang-dev \
      >/dev/null 2>&1 || true
  fi
}

build_agent() {
  if [[ -x "${PACKAGE_BIN}" ]]; then
    echo "→ Using packaged agent binary ${PACKAGE_BIN}"
    return 0
  fi
  if [[ -x "${AISPM_AGENT_BINARY:-}" ]]; then
    echo "→ Using AISPM_AGENT_BINARY=${AISPM_AGENT_BINARY}"
    return 0
  fi
  if [[ -x "${AGENT_DIR}/target/release/${BIN_NAME}" && "${REBUILD:-0}" != "1" ]]; then
    echo "→ Reusing existing release binary (set REBUILD=1 to rebuild)."
    return 0
  fi
  if [[ ! -d "${AGENT_DIR}" ]]; then
    echo "ERROR: no agent binary in package and agent source not found at ${AGENT_DIR}" >&2
    exit 1
  fi
  echo "→ Building agent..."
  local cargo_bin="${REAL_HOME}/.cargo/bin/cargo"
  [[ -x "${cargo_bin}" ]] || cargo_bin="cargo"
  as_user bash -lc "cd '${AGENT_DIR}' && '${cargo_bin}' build --release -p agent-service"
}

install_binary() {
  echo "→ Installing ${INSTALL_BIN}..."
  local src=""
  if [[ -x "${PACKAGE_BIN}" ]]; then
    src="${PACKAGE_BIN}"
  elif [[ -x "${AISPM_AGENT_BINARY:-}" ]]; then
    src="${AISPM_AGENT_BINARY}"
  else
    src="${AGENT_DIR}/target/release/${BIN_NAME}"
  fi
  install -m 0755 "${src}" "${INSTALL_BIN}"
}

write_env_file() {
  echo "→ Writing ${ENV_FILE}..."
  cat > "${ENV_FILE}" <<EOF
AISPM_GATEWAY_URL=${GATEWAY_URL}
AISPM_ORG_ID=${ORG_ID}
AISPM_ORG_TOKEN=${ORG_TOKEN}
AISPM_MITM_CA_DIR=${CA_DIR}
AISPM_TRANSPARENT_ENABLED=true
AISPM_TRANSPARENT_LISTEN=${TRANSPARENT_LISTEN}
AISPM_AUTO_CONFIGURE_NETWORK=false
AISPM_AUTO_CONFIGURE_PROXY=false
AISPM_EXPLICIT_PROXY_ENABLED=false
AISPM_AUTO_CONFIGURE_ENDPOINT=true
AISPM_AUTO_INSTALL_CA=false
AISPM_SOCKET_MARK=${SOCKET_MARK}
AISPM_LOG_JSON=false
AISPM_LOCAL_API_ENABLED=true
AISPM_LOCAL_API_LISTEN=127.0.0.1:8092
EOF
  chown "${SERVICE_USER}:${SERVICE_USER}" "${ENV_FILE}"
  chmod 0600 "${ENV_FILE}"
  # Ensure MITM CA dir is writable by the service user (crash cause if root-owned).
  install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0700 "${CA_DIR}"
}

write_systemd_unit() {
  echo "→ Installing systemd unit ${SERVICE_NAME}..."
  cat > "${UNIT_FILE}" <<EOF
[Unit]
Description=AI-SPM Enterprise Endpoint Agent
Documentation=https://github.com/ai-spm/ai-spm
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
EnvironmentFile=${ENV_FILE}
ExecStart=${INSTALL_BIN}
Restart=on-failure
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
}

setup_network_redirect() {
  echo "→ Installing transparent HTTPS redirect (iptables)..."
  if ! command -v iptables >/dev/null 2>&1; then
    echo "  WARNING: iptables missing; transparent interception will not work." >&2
    return 0
  fi

  iptables -t nat -N "${IPTABLES_CHAIN}" 2>/dev/null || iptables -t nat -F "${IPTABLES_CHAIN}"

  AISPM_UID="$(id -u "${SERVICE_USER}")"
  iptables -t nat -C "${IPTABLES_CHAIN}" -m owner --uid-owner "${AISPM_UID}" -j RETURN 2>/dev/null \
    || iptables -t nat -A "${IPTABLES_CHAIN}" -m owner --uid-owner "${AISPM_UID}" -j RETURN

  iptables -t nat -C "${IPTABLES_CHAIN}" -m mark --mark "${SOCKET_MARK}" -j RETURN 2>/dev/null \
    || iptables -t nat -A "${IPTABLES_CHAIN}" -m mark --mark "${SOCKET_MARK}" -j RETURN
  iptables -t nat -C "${IPTABLES_CHAIN}" -d 127.0.0.0/8 -j RETURN 2>/dev/null \
    || iptables -t nat -A "${IPTABLES_CHAIN}" -d 127.0.0.0/8 -j RETURN
  iptables -t nat -C "${IPTABLES_CHAIN}" -d 169.254.0.0/16 -j RETURN 2>/dev/null \
    || iptables -t nat -A "${IPTABLES_CHAIN}" -d 169.254.0.0/16 -j RETURN
  iptables -t nat -C "${IPTABLES_CHAIN}" -p tcp --dport 443 -m comment --comment "${IPTABLES_COMMENT}" -j REDIRECT --to-ports "${TRANSPARENT_PORT}" 2>/dev/null \
    || iptables -t nat -A "${IPTABLES_CHAIN}" -p tcp --dport 443 -m comment --comment "${IPTABLES_COMMENT}" -j REDIRECT --to-ports "${TRANSPARENT_PORT}"

  iptables -t nat -C OUTPUT -j "${IPTABLES_CHAIN}" 2>/dev/null \
    || iptables -t nat -I OUTPUT 1 -j "${IPTABLES_CHAIN}"

  echo "  Outbound TCP/443 redirected to ${TRANSPARENT_LISTEN}."
}

remove_network_redirect() {
  command -v iptables >/dev/null 2>&1 || return 0
  while iptables -t nat -C OUTPUT -j "${IPTABLES_CHAIN}" 2>/dev/null; do
    iptables -t nat -D OUTPUT -j "${IPTABLES_CHAIN}"
  done
  iptables -t nat -F "${IPTABLES_CHAIN}" 2>/dev/null || true
  iptables -t nat -X "${IPTABLES_CHAIN}" 2>/dev/null || true
}

block_quic() {
  echo "→ Blocking outbound QUIC (UDP/443)..."
  command -v iptables >/dev/null 2>&1 || return 0
  iptables -C OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT 2>/dev/null \
    || iptables -A OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT
  if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -C OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT 2>/dev/null \
      || ip6tables -A OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT 2>/dev/null || true
  fi
}

unblock_quic() {
  command -v iptables >/dev/null 2>&1 || return 0
  while iptables -C OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT 2>/dev/null; do
    iptables -D OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT
  done
  if command -v ip6tables >/dev/null 2>&1; then
    while ip6tables -C OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT 2>/dev/null; do
      ip6tables -D OUTPUT -p udp --dport 443 -m comment --comment "${QUIC_COMMENT}" -j REJECT
    done
  fi
}

trust_system_ca() {
  echo "→ Trusting MITM CA in the system store..."
  local tries=0
  while [[ ! -f "${CA_CERT}" && ${tries} -lt 20 ]]; do
    sleep 1
    tries=$((tries + 1))
  done
  if [[ ! -f "${CA_CERT}" ]]; then
    echo "  WARNING: CA not found at ${CA_CERT}" >&2
    return 0
  fi
  # Agent creates the CA as service user (mode 600). Make the cert readable so
  # desktop-user NSS certutil and other tooling can install it.
  chmod 644 "${CA_CERT}" 2>/dev/null || true
  install -m 0644 "${CA_CERT}" "${SYSTEM_CA_PATH}"
  update-ca-certificates >/dev/null 2>&1 || true
  echo "  System trust store updated."
}

install_nss_for_desktop_user() {
  echo "→ Trusting MITM CA in browser NSS stores for ${REAL_USER}..."
  local ca_for_nss="${SYSTEM_CA_PATH}"
  if [[ ! -f "${ca_for_nss}" ]]; then
    ca_for_nss="${CA_CERT}"
  fi
  if ! command -v certutil >/dev/null 2>&1 || [[ ! -f "${ca_for_nss}" ]]; then
    return 0
  fi
  # Readable copy for the desktop user (pkexec path is often mode 600 under aispm).
  local ca_readable="/tmp/ai-spm-mitm-ca.$$.crt"
  install -m 0644 "${ca_for_nss}" "${ca_readable}"
  local db
  for db in "${REAL_HOME}/.pki/nssdb" "${REAL_HOME}/.mozilla/firefox/"*; do
    [[ -d "${db}" ]] || continue
    [[ -f "${db}/cert9.db" || -f "${db}/cert8.db" ]] || continue
    local db_arg="sql:${db}"
    sudo -u "${REAL_USER}" certutil -d "${db_arg}" -D -n "AI-SPM MITM CA" 2>/dev/null || true
    if sudo -u "${REAL_USER}" certutil -d "${db_arg}" -A -t "C,," -n "AI-SPM MITM CA" -i "${ca_readable}"; then
      echo "  Installed CA into ${db}"
    fi
  done
  rm -f "${ca_readable}" 2>/dev/null || true
}

compute_extension_id() {
  python3 - "$1" <<'PY'
import hashlib, subprocess, sys
der = subprocess.check_output(["openssl", "rsa", "-in", sys.argv[1], "-pubout", "-outform", "DER"])
d = hashlib.sha256(der).digest()
print("".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0x0F)) for b in d[:16]))
PY
}

install_managed_extension() {
  echo "→ Packaging managed browser extension (enterprise web-UI masking)..."
  local ext_src
  ext_src="$(resolve_extension_src)"
  if [[ -z "${ext_src}" ]]; then
    echo "ERROR: browser-extension sources missing from this installer package." >&2
    echo "  Re-download from Admin → Download Agent after rebuilding assets (make installer-linux)." >&2
    exit 1
  fi
  echo "  Extension source: ${ext_src}"

  install -d -m 0755 /opt/ai-spm
  rm -rf "${EXT_INSTALL_DIR}"
  mkdir -p "${EXT_INSTALL_DIR}"
  cp -a "${ext_src}/." "${EXT_INSTALL_DIR}/"
  rm -f "${EXT_INSTALL_DIR}/.amo-upload-uuid" 2>/dev/null || true
  if [[ ! -f "${EXT_INSTALL_DIR}/manifest.json" ]]; then
    echo "ERROR: browser-extension/manifest.json missing after copy." >&2
    exit 1
  fi
  # Sealed .run extracts with go-rwx; agent (aispm) must read manifest for updates.xml.
  # Without this, local_api falls back to version 1.0.9 and Chrome forcelist fails.
  chmod 755 "${EXT_INSTALL_DIR}"
  find "${EXT_INSTALL_DIR}" -type d -exec chmod 755 {} +
  find "${EXT_INSTALL_DIR}" -type f -exec chmod 644 {} +
  chown -R root:root "${EXT_INSTALL_DIR}" 2>/dev/null || true

  # Stable Chromium extension ID across reinstalls (same vendor key in every .run).
  if [[ -f "${SCRIPT_DIR}/extension-key.pem" ]]; then
    install -m 600 "${SCRIPT_DIR}/extension-key.pem" "${EXT_KEY}"
  elif [[ ! -f "${EXT_KEY}" ]]; then
    openssl genrsa -out "${EXT_KEY}" 2048 2>/dev/null
    chmod 600 "${EXT_KEY}"
  fi

  local chrome_bin=""
  for c in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge microsoft-edge-stable brave-browser vivaldi; do
    if command -v "${c}" >/dev/null 2>&1; then
      chrome_bin="${c}"
      break
    fi
  done

  rm -f "${EXT_INSTALL_DIR}.crx" "${EXT_CRX}" "${EXT_XPI}"
  if [[ -n "${chrome_bin}" ]]; then
    local pack_dir="/tmp/ai-spm-ext-pack-$$"
    cp -a "${EXT_INSTALL_DIR}" "${pack_dir}"
    cp "${EXT_KEY}" "${pack_dir}.pem"
    chown -R "${REAL_USER}:${REAL_USER}" "${pack_dir}" "${pack_dir}.pem" 2>/dev/null || true
    sudo -u "${REAL_USER}" "${chrome_bin}" \
      --pack-extension="${pack_dir}" \
      --pack-extension-key="${pack_dir}.pem" 2>/dev/null || true
    if [[ -f "${pack_dir}.crx" ]]; then
      install -m 0644 "${pack_dir}.crx" "${EXT_CRX}"
      echo "  Packaged ${EXT_CRX}"
    else
      echo "  WARNING: CRX packaging failed." >&2
    fi
    rm -rf "${pack_dir}" "${pack_dir}.pem" 2>/dev/null || true
  else
    echo "  WARNING: no Chromium-family browser found — CRX packaging skipped." >&2
    echo "  Policies will still be written; reopen browser after Chrome/Chromium is installed." >&2
  fi

  python3 - <<PY
import pathlib, zipfile
src = pathlib.Path("${EXT_INSTALL_DIR}")
dst = pathlib.Path("${EXT_XPI}")
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in src.rglob("*"):
        if path.is_file() and path.name != ".amo-upload-uuid":
            zf.write(path, path.relative_to(src))
PY
  chmod 0644 "${EXT_XPI}"
  echo "  Packaged ${EXT_XPI}"

  compute_extension_id "${EXT_KEY}" > "${EXT_ID_FILE}"
  chmod 0644 "${EXT_ID_FILE}" 2>/dev/null || true
  echo "  Extension ID: $(cat "${EXT_ID_FILE}")"

  stage_signed_firefox_xpi
}

wait_for_extension_local_api() {
  echo "→ Waiting for agent extension endpoint (http://127.0.0.1:8092)…"
  # Chrome forcelist downloads CRX from the agent — must be up before browsers reopen.
  local i
  for i in $(seq 1 30); do
    if curl -sf --max-time 1 "http://127.0.0.1:8092/extension/updates.xml" >/dev/null 2>&1; then
      echo "  Extension updates.xml is reachable."
      return 0
    fi
    sleep 1
  done
  echo "ERROR: local_api not reachable on :8092 — Chrome cannot auto-install Prompt Guard." >&2
  echo "  Check: systemctl status ${SERVICE_NAME} && journalctl -u ${SERVICE_NAME} -n 50" >&2
  echo "  Agent log: /var/log/ai-spm/agent.log" >&2
  return 1
}

# Stage a Mozilla-signed Firefox XPI if the vendor shipped one. This is a
# one-time signing artifact (AMO unlisted / self-distribution) that makes the
# extension installable on standard Firefox release builds for every user.
# Lookup order: explicit env var, then known repo locations.
packaged_extension_version() {
  python3 - "$1" <<'PY'
import json, sys, zipfile
path = sys.argv[1]
try:
    with zipfile.ZipFile(path) as zf:
        data = json.loads(zf.read("manifest.json"))
    print(data.get("version", ""))
except Exception:
    print("")
PY
}

stage_signed_firefox_xpi() {
  local manifest_ver signed_ver=""
  manifest_ver="$(python3 -c "import json; print(json.load(open('${EXT_INSTALL_DIR}/manifest.json'))['version'])")"
  local candidates=(
    "${AISPM_FIREFOX_SIGNED_XPI:-}"
    "${SCRIPT_DIR}/browser-extension/ai-spm-prompt-guard-signed.xpi"
    "${SCRIPT_DIR}/ai-spm-prompt-guard-signed.xpi"
    "${REPO_ROOT}/browser-extension/ai-spm-prompt-guard-signed.xpi"
    "${REPO_ROOT}/browser-extension-signed/ai-spm-prompt-guard.xpi"
    "${REPO_ROOT}/dist/ai-spm-prompt-guard-signed.xpi"
  )
  local src
  for src in "${candidates[@]}"; do
    [[ -n "${src}" && -f "${src}" ]] || continue
    signed_ver="$(packaged_extension_version "${src}")"
    if [[ "${signed_ver}" == "${manifest_ver}" ]]; then
      install -m 0644 "${src}" "${EXT_XPI_SIGNED}"
      echo "  Staged Mozilla-signed Firefox XPI from ${src} (v${signed_ver})"
      return 0
    fi
    if [[ -n "${signed_ver}" ]]; then
      echo "  Note: signed Firefox XPI at ${src} is v${signed_ver} (source v${manifest_ver})."
      echo "  Staging it anyway — release Firefox requires a signed build."
      echo "  Re-sign for latest fixes: scripts/sign-firefox-extension.sh"
      install -m 0644 "${src}" "${EXT_XPI_SIGNED}"
      return 0
    fi
    install -m 0644 "${src}" "${EXT_XPI_SIGNED}"
    echo "  Staged Mozilla-signed Firefox XPI from ${src}"
    return 0
  done
  rm -f "${EXT_XPI_SIGNED}" 2>/dev/null || true
  echo "  No current signed Firefox XPI found — Firefox release builds require one."
  echo "  Sign once with: scripts/sign-firefox-extension.sh (AMO unlisted)."
}

install_reconcile_script() {
  echo "→ Installing browser extension reconciler..."
  local src
  src="$(resolve_reconcile_script_src)"
  if [[ -z "${src}" ]]; then
    echo "ERROR: reconcile-browser-extensions.sh missing from installer package." >&2
    exit 1
  fi
  install -d -m 0755 "$(dirname "${RECONCILE_SCRIPT}")"
  install -m 0755 "${src}" "${RECONCILE_SCRIPT}"
}

# Keep a local copy of this installer so uninstall works without the git repo / sealed .run.
install_local_management_tools() {
  echo "→ Installing local management tools (uninstall / refresh)…"
  install -d -m 0755 "$(dirname "${INSTALLER_LIB}")"
  install -m 0755 "${BASH_SOURCE[0]}" "${INSTALLER_LIB}"
  cat > "${UNINSTALL_BIN}" <<EOF
#!/usr/bin/env bash
# AI-SPM endpoint uninstall — works after gateway is remote; no repo checkout required.
exec bash "${INSTALLER_LIB}" uninstall "\$@"
EOF
  chmod 0755 "${UNINSTALL_BIN}"
  # Convenience: aispm-agent refresh-extensions | uninstall | stop
  cat > /usr/local/sbin/aispm-agent <<EOF
#!/usr/bin/env bash
set -euo pipefail
cmd="\${1:-}"
shift || true
case "\${cmd}" in
  uninstall|stop|remove|refresh-extensions)
    exec bash "${INSTALLER_LIB}" "\${cmd}" "\$@"
    ;;
  ""|-h|--help|help)
    echo "Usage: aispm-agent {uninstall|refresh-extensions}"
    exit 0
    ;;
  *)
    echo "Usage: aispm-agent {uninstall|refresh-extensions}" >&2
    exit 1
    ;;
esac
EOF
  chmod 0755 /usr/local/sbin/aispm-agent
}

write_reconcile_units() {
  echo "→ Installing browser extension reconcile timer..."
  cat > "${RECONCILE_SERVICE}" <<EOF
[Unit]
Description=AI-SPM Browser Extension Reconciler
After=network-online.target ai-spm-agent.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${RECONCILE_SCRIPT} install
EOF

  cat > "${RECONCILE_TIMER}" <<EOF
[Unit]
Description=Periodic AI-SPM Browser Extension Reconciler

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=ai-spm-browser-reconcile.service
Persistent=true

[Install]
WantedBy=timers.target
EOF
  chmod 0644 "${RECONCILE_SERVICE}" "${RECONCILE_TIMER}"
  systemctl daemon-reload
}

run_browser_reconcile() {
  echo "→ Reconciling managed browser extensions..."
  "${RECONCILE_SCRIPT}" install
}

enable_reconcile_timer() {
  echo "→ Enabling browser extension reconcile timer..."
  systemctl enable --now ai-spm-browser-reconcile.timer >/dev/null
}

remove_browser_extension_integration() {
  "${RECONCILE_SCRIPT}" remove 2>/dev/null || true
  rm -f "${RECONCILE_SERVICE}" "${RECONCILE_TIMER}"
  systemctl daemon-reload
}

kill_browser_processes() {
  echo "→ Stopping browser processes (required to reload managed extensions)..."
  for proc in chrome google-chrome google-chrome-stable chromium chromium-browser \
    firefox microsoft-edge microsoft-edge-stable brave brave-browser vivaldi; do
    pkill -9 -x "${proc}" 2>/dev/null || true
  done
  sleep 2
}

clear_extension_profile_caches() {
  local ext_id
  ext_id="$(cat "${EXT_ID_FILE}" 2>/dev/null || true)"

  if [[ -n "${REAL_HOME}" && -n "${ext_id}" ]]; then
    echo "→ Clearing cached Chromium extension (${ext_id}) from ${REAL_USER} profile..."
    while IFS= read -r -d '' d; do
      rm -rf "${d}"
      echo "  removed ${d}"
    done < <(find "${REAL_HOME}/.config" "${REAL_HOME}/snap" \
      \( -path "*/Extensions/${ext_id}" \
        -o -path "*/Extensions/${ext_id}/*" \
        -o -path "*/Local Extension Settings/${ext_id}" \
        -o -path "*/Sync Extension Settings/${ext_id}" \
        -o -path "*/Managed Extension Settings/${ext_id}" \
        -o -path "*/Extension State/${ext_id}" \) \
      -print0 2>/dev/null || true)

    # Policy/external extensions store version in Preferences, not always under Extensions/.
    while IFS= read -r -d '' prefs; do
      if python3 - "${prefs}" "${ext_id}" <<'PY'
import json, sys
path, ext_id = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
changed = False
ext = data.get("extensions", {})
settings = ext.get("settings", {})
if ext_id in settings:
    del settings[ext_id]
    changed = True
for key in ("install_signature", "last_chrome_version"):
    if key in ext:
        ext.pop(key, None)
        changed = True
if changed:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"  cleared {ext_id} from {path}")
PY
      then
        :
      fi
    done < <(find "${REAL_HOME}/.config/google-chrome" "${REAL_HOME}/.config/chromium" \
      "${REAL_HOME}/snap" -name "Preferences" -print0 2>/dev/null || true)
  fi

  if [[ -n "${REAL_HOME}" ]]; then
    echo "→ Clearing cached Firefox extension from ${REAL_USER} profile..."
    while IFS= read -r -d '' f; do
      rm -rf "${f}"
      echo "  removed ${f}"
    done < <(find "${REAL_HOME}/.mozilla/firefox" "${REAL_HOME}/snap/firefox" \
      \( -name 'prompt-guard@aispm.io*' -o -name 'ai-spm-prompt-guard*' \) -print0 2>/dev/null || true)
  fi
}

# Remove enterprise policies + wipe browser-side caches, then redeploy the latest
# packaged extension. Use when Chrome/Firefox still show an old version after install.
refresh_browser_extensions() {
  require_root
  echo "AI-SPM browser extension refresh"
  export AISPM_DESKTOP_USER="${REAL_USER}"
  export SUDO_USER="${REAL_USER}"
  kill_browser_processes
  remove_browser_extension_integration
  clear_extension_profile_caches
  install_managed_extension
  install_reconcile_script
  install_local_management_tools
  write_reconcile_units
  run_browser_reconcile
  enable_reconcile_timer
  systemctl restart "${SERVICE_NAME}" >/dev/null 2>&1 || true
  sleep 2
  wait_for_extension_local_api

  local ext_display_version="?"
  if [[ -f "${EXT_INSTALL_DIR}/manifest.json" ]]; then
    ext_display_version="$(python3 -c "import json; print(json.load(open('${EXT_INSTALL_DIR}/manifest.json'))['version'])")"
  fi
  echo ""
  echo "Extension redeployed as v${ext_display_version}."
  if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    echo "  Agent: RUNNING (Chrome will fetch v${ext_display_version} from updates.xml)."
  else
    echo "  WARNING: Agent is NOT running — start it before opening Chrome:"
    echo "           sudo systemctl start ${SERVICE_NAME}"
  fi
  echo "  1. Ensure agent is running, THEN open Chrome (not before)."
  echo "  2. chrome://extensions → confirm v${ext_display_version}"
  echo "  3. Firefox → about:addons (re-sign for v${ext_display_version} if needed)"
  echo "  4. Hard-refresh gemini.google.com / chatgpt.com (Ctrl+Shift+R)"
}

start_service() {
  echo "→ Enabling and starting ${SERVICE_NAME}..."
  systemctl enable "${SERVICE_NAME}" >/dev/null
  systemctl restart "${SERVICE_NAME}"
  sleep 2
  if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "  Service running."
  else
    echo "  WARNING: service failed to start. Check: journalctl -u ${SERVICE_NAME} -n 50" >&2
  fi
}

# Employee UX: do not ask users to run systemctl/tail — verify gateway bind here.
wait_for_agent_registered() {
  echo "→ Waiting for agent to register with the organization gateway…"
  local cert="/etc/ai-spm/certs/agent.crt"
  local agent_log="/var/log/ai-spm/agent.log"
  local i
  for i in $(seq 1 45); do
    # mTLS cert on disk is the real success signal (gateway must return PEMs).
    if [[ -f "${cert}" ]] && systemctl is-active --quiet "${SERVICE_NAME}"; then
      _persist_agent_id_from_cert "${cert}"
      echo "  Registered with gateway (mTLS certificate present)."
      return 0
    fi
    if [[ -f "${agent_log}" ]] && grep -q 'Invalid org token\|403 Forbidden' "${agent_log}" 2>/dev/null; then
      if grep -q 'Invalid org token\|Invalid organization' "${agent_log}" 2>/dev/null \
        || grep -qE 'status: 403' "${agent_log}" 2>/dev/null; then
        # Only fail early if we still have no cert after a rejected register.
        if [[ ! -f "${cert}" ]] && grep -qE 'registration failed|Api \{ status: 403' "${agent_log}" 2>/dev/null; then
          echo "ERROR: gateway rejected the enrollment token (Invalid org token)." >&2
          echo "  Admin → Download Agent again, then re-run the new .run on this PC." >&2
          echo "  (Each download rotates the token; do not reuse an older installer.)" >&2
          return 1
        fi
      fi
    fi
    if [[ -f "${agent_log}" ]] && grep -q 'no certificate material was returned' "${agent_log}" 2>/dev/null; then
      if [[ ! -f "${cert}" ]]; then
        echo "ERROR: gateway registered the agent but did not issue an mTLS certificate." >&2
        echo "  Check API/openssl CA on the gateway, then: sudo systemctl restart ${SERVICE_NAME}" >&2
        return 1
      fi
    fi
    sleep 2
  done
  echo "ERROR: agent did not register with the gateway in time." >&2
  echo "  Gateway URL: ${GATEWAY_URL}" >&2
  echo "  Confirm the admin console/gateway is running, then re-run this installer." >&2
  if [[ -f "${agent_log}" ]]; then
    echo "  Recent agent log:" >&2
    tail -n 15 "${agent_log}" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' >&2 || true
  fi
  return 1
}

_persist_agent_id_from_cert() {
  local cert="$1"
  [[ -f "${cert}" && -f "${ENV_FILE}" ]] || return 0
  command -v openssl >/dev/null 2>&1 || return 0
  local agent_id
  agent_id="$(openssl x509 -in "${cert}" -noout -text 2>/dev/null \
    | sed -n 's/.*spiffe:\/\/aispm\.io\/org\/[^/]*\/agent\/\([0-9a-fA-F-]\{36\}\).*/\1/p' \
    | head -1)"
  [[ -n "${agent_id}" ]] || return 0
  if grep -q '^AISPM_AGENT_ID=' "${ENV_FILE}" 2>/dev/null; then
    sed -i "s/^AISPM_AGENT_ID=.*/AISPM_AGENT_ID=${agent_id}/" "${ENV_FILE}"
  else
    echo "AISPM_AGENT_ID=${agent_id}" >> "${ENV_FILE}"
  fi
}

verify_inspect_path() {
  echo "→ Verifying prompt inspection path…"
  local out
  out="$(curl -sf --max-time 8 -X POST "http://127.0.0.1:8092/inspect" \
    -H "Content-Type: application/json" \
    -d '{"provider":"openai","model":"gpt-4o","messages":[{"role":"user","content":"contact me at verify-install@example.com"}]}' 2>/dev/null || true)"
  if [[ -z "${out}" ]]; then
    echo "  WARNING: local inspect API did not respond (masking may fail until agent is healthy)." >&2
    return 0
  fi
  if echo "${out}" | grep -q 'agent not registered'; then
    echo "ERROR: inspect path still reports agent not registered." >&2
    return 1
  fi
  if echo "${out}" | grep -qiE 'verify-install@example\.com|masked_messages|MASKED|EMAIL|pii|decision'; then
    if echo "${out}" | grep -q 'verify-install@example.com' \
      && ! echo "${out}" | grep -qiE 'MASKED|masked_messages|"decision":"(masked|allowed)"'; then
      echo "  WARNING: inspect returned without clear masking — check admin policies/PII engine." >&2
    else
      echo "  Inspection path OK (gateway reachable from agent)."
    fi
    return 0
  fi
  echo "  Inspection path responded."
  return 0
}

remove_nss_ca_for_desktop_user() {
  if ! command -v certutil >/dev/null 2>&1 || [[ -z "${REAL_HOME}" ]]; then
    return 0
  fi
  local db
  for db in "${REAL_HOME}/.pki/nssdb" "${REAL_HOME}/.mozilla/firefox/"*; do
    [[ -d "${db}" ]] || continue
    [[ -f "${db}/cert9.db" || -f "${db}/cert8.db" ]] || continue
    sudo -u "${REAL_USER}" certutil -d "sql:${db}" -D -n "AI-SPM MITM CA" 2>/dev/null || true
  done
}

# Tell the org gateway to delete this endpoint from Agent Fleet before wiping local state.
notify_gateway_unregister() {
  echo "→ Notifying gateway to remove this device from Agent Fleet…"
  local env_file="${ENV_FILE}"
  local cert="/etc/ai-spm/certs/agent.crt"
  if [[ ! -f "${env_file}" ]]; then
    echo "  No ${env_file} — skipping fleet unregister (already cleaned locally)."
    return 0
  fi

  # shellcheck disable=SC1090
  set -a
  # shellcheck disable=SC1091
  source "${env_file}"
  set +a

  local gateway="${AISPM_GATEWAY_URL:-}"
  local org_id="${AISPM_ORG_ID:-}"
  local agent_id="${AISPM_AGENT_ID:-}"

  if [[ -z "${agent_id}" && -f "${cert}" ]] && command -v openssl >/dev/null 2>&1; then
    agent_id="$(openssl x509 -in "${cert}" -noout -text 2>/dev/null \
      | sed -n 's/.*spiffe:\/\/aispm\.io\/org\/[^/]*\/agent\/\([0-9a-fA-F-]\{36\}\).*/\1/p' \
      | head -1)"
  fi

  if [[ -z "${gateway}" || -z "${org_id}" || -z "${agent_id}" ]]; then
    echo "  Could not resolve gateway/org/agent id — remove the Offline row in Admin → Agent Fleet if needed."
    return 0
  fi

  local code
  code="$(curl -sS -o /tmp/aispm-unregister.out -w '%{http_code}' --max-time 15 \
    -X POST "${gateway%/}/agent/v1/unregister" \
    -H "Content-Type: application/json" \
    -H "X-Org-ID: ${org_id}" \
    -H "X-Agent-ID: ${agent_id}" \
    2>/dev/null || echo "000")"

  if [[ "${code}" == "204" || "${code}" == "404" ]]; then
    echo "  Fleet record removed (HTTP ${code})."
  else
    echo "  WARNING: gateway unregister returned HTTP ${code} — delete the device in Admin → Agent Fleet if it still appears." >&2
    [[ -f /tmp/aispm-unregister.out ]] && head -c 200 /tmp/aispm-unregister.out >&2 || true
    echo >&2
  fi
  rm -f /tmp/aispm-unregister.out 2>/dev/null || true
}

uninstall_agent() {
  require_root
  # If we were invoked from the on-disk management copy, re-exec from /tmp so
  # deleting /usr/local/lib/ai-spm cannot truncate this running script mid-run.
  if [[ "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")" == "$(readlink -f "${INSTALLER_LIB}" 2>/dev/null || true)" ]]; then
    local tmp
    tmp="$(mktemp /tmp/aispm-uninstall.XXXXXX.sh)"
    cp -a "${BASH_SOURCE[0]}" "${tmp}"
    chmod 700 "${tmp}"
    exec bash "${tmp}" uninstall
  fi

  echo "→ Uninstalling AI-SPM endpoint agent (full cleanup)..."

  systemctl stop ai-spm-browser-reconcile.timer 2>/dev/null || true
  systemctl disable ai-spm-browser-reconcile.timer 2>/dev/null || true
  systemctl stop ai-spm-browser-reconcile.service 2>/dev/null || true
  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

  # Must run before deleting /etc/ai-spm (uses agent.env + client cert).
  notify_gateway_unregister

  remove_network_redirect
  unblock_quic

  export AISPM_DESKTOP_USER="${REAL_USER}"
  export SUDO_USER="${REAL_USER}"
  kill_browser_processes
  remove_browser_extension_integration
  clear_extension_profile_caches

  echo "→ Removing systemd units…"
  rm -f "${UNIT_FILE}" "${RECONCILE_SERVICE}" "${RECONCILE_TIMER}"
  systemctl daemon-reload 2>/dev/null || true
  systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true

  echo "→ Removing agent binary and local packages…"
  rm -f "${INSTALL_BIN}" "${RECONCILE_SCRIPT}" "${UNINSTALL_BIN}" /usr/local/sbin/aispm-agent
  # Remove lib dir last (contains this script when run from INSTALLER_LIB).
  rm -rf /opt/ai-spm /usr/local/lib/ai-spm
  rm -f "${INSTALLER_LIB}" 2>/dev/null || true

  echo "→ Removing config, certs, and logs…"
  remove_nss_ca_for_desktop_user
  rm -f "${SYSTEM_CA_PATH}"
  update-ca-certificates >/dev/null 2>&1 || true
  rm -rf /etc/ai-spm /var/log/ai-spm
  rm -f /etc/firefox/policies/ai-spm-prompt-guard.xpi 2>/dev/null || true

  # Optional: remove dedicated system user if nothing else owns it.
  if id "${SERVICE_USER}" >/dev/null 2>&1; then
    userdel "${SERVICE_USER}" 2>/dev/null || true
  fi

  echo "  Network redirect and QUIC block removed."
  echo "  Managed browser extensions / policies removed."
  echo "  Removed /etc/ai-spm, /opt/ai-spm, /var/log/ai-spm, and ${INSTALL_BIN}."
  echo "  Reopen browsers to confirm Prompt Guard is gone."
  echo "Done."
}

# Back-compat alias used by docs / older packages.
stop_agent() {
  uninstall_agent
}

main() {
  case "${1:-}" in
    stop|uninstall|remove)
      uninstall_agent
      exit 0
      ;;
    refresh-extensions)
      refresh_browser_extensions
      exit 0
      ;;
  esac

  require_root
  echo "AI-SPM enterprise agent install"
  echo "  gateway=${GATEWAY_URL}"
  echo "  transparent=${TRANSPARENT_LISTEN}"
  echo ""

  install_dependencies
  ensure_service_user
  build_agent
  install_binary
  write_env_file
  write_systemd_unit
  setup_network_redirect
  block_quic
  start_service
  trust_system_ca
  install_nss_for_desktop_user

  # Chrome must be closed before policy/CRX deploy (same order as refresh-extensions).
  export AISPM_DESKTOP_USER="${REAL_USER}"
  export SUDO_USER="${REAL_USER}"
  kill_browser_processes
  rec_src="$(resolve_reconcile_script_src)"
  if [[ -n "${rec_src}" ]]; then
    bash "${rec_src}" purge-stale
  fi
  remove_browser_extension_integration

  install_managed_extension
  install_reconcile_script
  install_local_management_tools
  write_reconcile_units
  run_browser_reconcile
  enable_reconcile_timer
  # Restart so local_api serves the freshly packaged CRX; Chrome forcelist needs :8092.
  systemctl restart "${SERVICE_NAME}" >/dev/null 2>&1 || true
  sleep 2
  if ! wait_for_extension_local_api; then
    echo ""
    echo "============================================================"
    echo " Install incomplete — agent local API (:8092) is not healthy."
    echo " Extensions and prompt masking will NOT work until the agent stays running."
    echo "============================================================"
    exit 1
  fi
  if ! wait_for_agent_registered; then
    echo ""
    echo "============================================================"
    echo " Install incomplete — agent is not linked to your organization."
    echo " Prompt masking and audit will NOT work until registration succeeds."
    echo "============================================================"
    exit 1
  fi
  if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "ERROR: agent service is not running after registration." >&2
    exit 1
  fi
  verify_inspect_path || true

  echo "→ Clearing cached extension copies (required for version updates)..."
  kill_browser_processes
  clear_extension_profile_caches

  local ext_display_version="?"
  if [[ -f "${EXT_INSTALL_DIR}/manifest.json" ]]; then
    ext_display_version="$(python3 -c "import json; print(json.load(open('${EXT_INSTALL_DIR}/manifest.json'))['version'])")"
  fi
  local ff_signed_ver=""
  if [[ -f "${EXT_XPI_SIGNED}" ]]; then
    ff_signed_ver="$(packaged_extension_version "${EXT_XPI_SIGNED}")"
  fi

  echo ""
  echo "============================================================"
  echo " AI-SPM is installed and registered with your organization."
  echo ""
  echo "   • Agent:         running (starts automatically on reboot)"
  echo "   • Web UI mask:   Chrome / Firefox Prompt Guard v${ext_display_version}"
  echo "   • API traffic:   protected at the network layer"
  echo ""
  echo " What you should do:"
  echo "   1. Open Chrome and Firefox (quit them fully first if they were open)."
  echo "   2. Confirm 'AI-SPM Prompt Guard' appears under extensions/add-ons."
  echo "   3. Use ChatGPT / Claude / Gemini as usual — masking is automatic."
  echo ""
  echo " To uninstall later (no download / git repo needed):"
  echo "   sudo aispm-agent uninstall"
  echo ""
  print_browser_status "Chrome" "chrome" "/etc/opt/chrome/policies/managed/ai-spm-prompt-guard.json"
  print_browser_status "Firefox" "firefox" "/etc/firefox/policies/policies.json"
  if [[ -n "${ff_signed_ver}" && "${ff_signed_ver}" != "${ext_display_version}" ]]; then
    echo "   Note: Firefox signed package is v${ff_signed_ver} (source v${ext_display_version})."
  fi
  echo "============================================================"
}

main "$@"
