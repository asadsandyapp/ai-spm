#!/usr/bin/env bash
#
# AI-SPM — one-shot Ubuntu deploy (platform stack).
#
# Run from anywhere after cloning the repo:
#
#   chmod +x scripts/deploy-ubuntu.sh
#   ./scripts/deploy-ubuntu.sh
#
# Options:
#   --reset            Stop stack, remove volumes, rebuild from scratch
#   --no-build         Start existing images only (skip docker build)
#   --with-installer   Also install Rust toolchain + build Linux agent installer assets
#   --with-dev         Install Python 3.12+/Node 20+ for native backend/frontend work
#   --skip-apt         Do not apt-install packages (assume Docker already present)
#   --status           Print service URLs / health and exit
#   --down             Stop the Compose stack and exit
#   -h, --help         Show help
#
# What this script sets up:
#   Postgres, Redis, MinIO, FastAPI API, Kong (:8090), Prometheus, Grafana,
#   Admin dashboard (:3000). Migrations + platform/dev seeds run on API start.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/deploy/docker-compose.yml"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")
ENV_FILE="${ROOT}/deploy/.env"
ENV_EXAMPLE="${ROOT}/deploy/.env.example"
FE_ENV="${ROOT}/frontend/.env"
FE_ENV_EXAMPLE="${ROOT}/frontend/.env.example"
INSTALLER_DIR="${ROOT}/dist/linux-installer"

DO_APT=1
DO_BUILD=1
DO_RESET=0
DO_INSTALLER=0
DO_DEV=0
MODE="deploy" # deploy | status | down

GATEWAY_URL="${AISPM_PUBLIC_GATEWAY_URL:-http://localhost:8090}"
DASHBOARD_URL="${AISPM_DASHBOARD_URL:-http://localhost:3000}"

RED=$'\033[31m'
GRN=$'\033[32m'
YLW=$'\033[33m'
BLU=$'\033[34m'
BOLD=$'\033[1m'
RST=$'\033[0m'

log()  { printf '%s→%s %s\n' "${BLU}" "${RST}" "$*"; }
ok()   { printf '%s✓%s %s\n' "${GRN}" "${RST}" "$*"; }
warn() { printf '%s!%s %s\n' "${YLW}" "${RST}" "$*" >&2; }
die()  { printf '%sERROR:%s %s\n' "${RED}" "${RST}" "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
AI-SPM — one-shot Ubuntu deploy (platform stack).

Usage:
  ./scripts/deploy-ubuntu.sh [options]

Options:
  --reset            Stop stack, remove volumes, rebuild from scratch
  --no-build         Start existing images only (skip docker build)
  --with-installer   Also install Rust toolchain + build Linux agent installer assets
  --with-dev         Install Python 3.12+/Node 20+ for native backend/frontend work
  --skip-apt         Do not apt-install packages (assume Docker already present)
  --status           Print service URLs / health and exit
  --down             Stop the Compose stack and exit
  -h, --help         Show help

Example (new Ubuntu PC after git clone):
  chmod +x scripts/deploy-ubuntu.sh
  ./scripts/deploy-ubuntu.sh
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset) DO_RESET=1 ;;
    --no-build) DO_BUILD=0 ;;
    --with-installer) DO_INSTALLER=1 ;;
    --with-dev) DO_DEV=1 ;;
    --skip-apt) DO_APT=0 ;;
    --status) MODE="status" ;;
    --down) MODE="down" ;;
    -h|--help) usage ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
  shift
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

is_ubuntu() {
  [[ -f /etc/os-release ]] || return 1
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" || "${ID_LIKE:-}" == *ubuntu* || "${ID:-}" == "debian" ]]
}

run_docker() {
  # Prefer plain docker when the current user can talk to the daemon.
  if docker info >/dev/null 2>&1; then
    "$@"
    return
  fi
  if command -v sg >/dev/null 2>&1 && id -nG | grep -qw docker; then
    # Group membership present but shell session not refreshed yet.
    sg docker -c "$(printf '%q ' "$@")"
    return
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return
  fi
  # Last resort: sudo (password prompt once).
  if sudo -n docker info >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  warn "Docker needs elevated access. You may be prompted for your password."
  sudo "$@"
}

compose() {
  run_docker "${COMPOSE[@]}" "$@"
}

wait_http() {
  local url="$1"
  local label="$2"
  local tries="${3:-60}"
  local i
  for ((i = 1; i <= tries; i++)); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      ok "${label} is up (${url})"
      return 0
    fi
    sleep 2
  done
  return 1
}

print_banner() {
  cat <<EOF

${BOLD}╔══════════════════════════════════════════════════════════╗
║           AI-SPM — Ubuntu platform deploy                ║
╚══════════════════════════════════════════════════════════╝${RST}

  Repo: ${ROOT}

EOF
}

print_summary() {
  cat <<EOF

${BOLD}══════════════════════════════════════════════════════════${RST}
 ${BOLD}AI-SPM is ready${RST}
${BOLD}══════════════════════════════════════════════════════════${RST}

  ${BOLD}Admin dashboard${RST}   ${DASHBOARD_URL}
  ${BOLD}API gateway${RST}       ${GATEWAY_URL}
  ${BOLD}API docs${RST}          ${GATEWAY_URL}/docs
  ${BOLD}Grafana${RST}           http://localhost:3001  (admin / admin)
  ${BOLD}Prometheus${RST}        http://localhost:9090
  ${BOLD}MinIO console${RST}     http://localhost:9001  (minioadmin / minioadmin)

  ${BOLD}Login (unified /login)${RST}
    Platform admin:  platform-admin@aispm.io  /  PlatformAdmin123!
    Dev tenant:      admin@devcorp.io         /  DevAdminPass123!

  ${BOLD}Dev org token (agent enroll)${RST}
    ${YLW}dev-org-token-please-change-32chars-minimum${RST}
    (org id is printed by seed / visible in Admin → Agents)

  ${BOLD}Useful commands${RST}
    ./scripts/deploy-ubuntu.sh --status
    ./scripts/deploy-ubuntu.sh --down
    docker compose -f deploy/docker-compose.yml logs -f api
    make installer-linux          # after: --with-installer once

  ${BOLD}Endpoint agent (this PC or another desktop)${RST}
    1. Open ${DASHBOARD_URL}/agents/download as a tenant admin
    2. Download the sealed .run and execute it
    3. Reopen the browser, then test chatgpt.com with an email

${BOLD}══════════════════════════════════════════════════════════${RST}

EOF
}

check_ports() {
  local ports=(5432 6380 8090 3000 3001 9000 9001 9090)
  local p busy=0
  for p in "${ports[@]}"; do
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${p}\$"; then
      # Port may already be our stack — only warn if compose is not up yet.
      if ! compose ps --status running 2>/dev/null | grep -q .; then
        warn "Host port ${p} is already in use — Compose may fail to bind it"
        busy=1
      fi
    fi
  done
  if [[ "$busy" -eq 1 ]]; then
    warn "Free conflicting ports or adjust deploy/docker-compose.yml mappings, then re-run."
  fi
}

install_apt_base() {
  log "Installing OS packages (Docker, curl, make, git)…"
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl gnupg lsb-release git make \
    apt-transport-https software-properties-common \
    iptables ip6tables libnss3-tools python3 python3-venv \
    build-essential pkg-config libssl-dev

  if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker Engine (official apt repo)…"
    sudo install -m 0755 -d /etc/apt/keyrings
    if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
      sudo chmod a+r /etc/apt/keyrings/docker.asc
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    local arch codename
    arch="$(dpkg --print-architecture)"
    codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-jammy}}"
    echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update -y
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
      || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2
  else
    # Ensure Compose v2 plugin exists
    if ! docker compose version >/dev/null 2>&1; then
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin \
        || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-v2 \
        || true
    fi
  fi

  sudo systemctl enable --now docker >/dev/null 2>&1 || true

  local user_name="${SUDO_USER:-$USER}"
  if [[ "${user_name}" != "root" ]] && ! id -nG "${user_name}" | grep -qw docker; then
    log "Adding ${user_name} to the docker group…"
    sudo usermod -aG docker "${user_name}"
    warn "Docker group updated. This script continues via sg/sudo; new terminals will not need sudo."
  fi
  ok "Docker ready: $(run_docker docker --version | head -1)"
}

install_dev_tools() {
  log "Installing native dev tools (Python + Node)…"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-venv python3-pip python3-dev
  if ! command -v node >/dev/null 2>&1 || [[ "$(node -v 2>/dev/null | tr -d v | cut -d. -f1 || echo 0)" -lt 20 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
  fi
  ok "Python $(python3 --version) · Node $(node --version) · npm $(npm --version)"
}

install_rust_if_needed() {
  if command -v cargo >/dev/null 2>&1; then
    ok "Rust already installed: $(rustc --version 2>/dev/null || true)"
    return
  fi
  log "Installing Rust toolchain (rustup)…"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  # shellcheck disable=SC1091
  source "${HOME}/.cargo/env"
  ok "Rust installed: $(rustc --version)"
}

prepare_env_files() {
  mkdir -p "${ROOT}/deploy" "${INSTALLER_DIR}"

  if [[ ! -f "${ENV_FILE}" ]]; then
    if [[ -f "${ENV_EXAMPLE}" ]]; then
      cp "${ENV_EXAMPLE}" "${ENV_FILE}"
      # Local deploy defaults: Stripe off unless user edits keys.
      sed -i 's/^STRIPE_ENABLED=.*/STRIPE_ENABLED=false/' "${ENV_FILE}" || true
      ok "Created ${ENV_FILE} from example (Stripe disabled)"
    else
      cat > "${ENV_FILE}" <<EOF
STRIPE_ENABLED=false
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_STARTER=
STRIPE_PRICE_PROFESSIONAL=
JWT_SECRET_KEY=dev-secret-change-in-production
PLATFORM_JWT_SECRET_KEY=dev-platform-secret
APP_BASE_URL=http://localhost:5173
AISPM_PUBLIC_GATEWAY_URL=http://localhost:8090
EOF
      ok "Created minimal ${ENV_FILE}"
    fi
  else
    ok "Using existing ${ENV_FILE}"
  fi

  # Ensure gateway URL is stamped for sealed agent downloads.
  if ! grep -q '^AISPM_PUBLIC_GATEWAY_URL=' "${ENV_FILE}" 2>/dev/null; then
    echo "AISPM_PUBLIC_GATEWAY_URL=${GATEWAY_URL}" >> "${ENV_FILE}"
  fi

  if [[ ! -f "${FE_ENV}" ]]; then
    if [[ -f "${FE_ENV_EXAMPLE}" ]]; then
      cp "${FE_ENV_EXAMPLE}" "${FE_ENV}"
    else
      echo "VITE_API_URL=http://localhost:8090" > "${FE_ENV}"
    fi
  fi
  # Compose dashboard build bakes VITE_API_URL=8090; keep local Vite consistent.
  if grep -q '^VITE_API_URL=' "${FE_ENV}"; then
    sed -i 's|^VITE_API_URL=.*|VITE_API_URL=http://localhost:8090|' "${FE_ENV}"
  else
    echo "VITE_API_URL=http://localhost:8090" >> "${FE_ENV}"
  fi
  ok "Frontend VITE_API_URL → http://localhost:8090"

  # Placeholder so the API bind-mount is never an empty missing path.
  mkdir -p "${INSTALLER_DIR}"
  if [[ ! -f "${INSTALLER_DIR}/.keep" ]]; then
    echo "Run: make installer-linux   (or ./scripts/deploy-ubuntu.sh --with-installer)" \
      > "${INSTALLER_DIR}/README.txt"
    touch "${INSTALLER_DIR}/.keep"
  fi
}

show_status() {
  log "Compose services:"
  compose ps || true
  echo
  if wait_http "${GATEWAY_URL}/health" "Kong/API health" 3; then
    curl -fsS "${GATEWAY_URL}/health" || true
    echo
  else
    warn "Gateway health check failed at ${GATEWAY_URL}/health"
  fi
  if curl -fsS --max-time 3 "${DASHBOARD_URL}" >/dev/null 2>&1; then
    ok "Dashboard responds at ${DASHBOARD_URL}"
  else
    warn "Dashboard not reachable at ${DASHBOARD_URL}"
  fi
  print_summary
}

do_down() {
  log "Stopping AI-SPM Compose stack…"
  compose down
  ok "Stack stopped"
}

build_and_up() {
  cd "${ROOT}"
  check_ports

  if [[ "${DO_RESET}" -eq 1 ]]; then
    warn "Reset: stopping stack and removing volumes…"
    compose down -v --remove-orphans || true
    DO_BUILD=1
  fi

  if [[ "${DO_BUILD}" -eq 1 ]]; then
    log "Building images (api + dashboard)…"
    # NOTE: `docker compose build --network=host` is rejected on Compose v2.39+
    # ("unknown flag: --network"). Plain `compose build` is the portable path.
    # If Hub pulls hang on broken IPv6, fix host DNS or set:
    #   echo '{"ipv6":false}' | sudo tee /etc/docker/daemon.json && sudo systemctl restart docker
    compose build
    ok "Images built"
  else
    log "Skipping image build (--no-build)"
  fi

  log "Starting services…"
  compose up -d
  ok "Compose up -d issued"

  log "Waiting for API via Kong (${GATEWAY_URL}/health)…"
  if ! wait_http "${GATEWAY_URL}/health" "API health" 90; then
    warn "Health check timed out. Recent API logs:"
    compose logs --tail=80 api || true
    die "Stack did not become healthy. Fix the errors above and re-run."
  fi

  # Readiness (DB) — best effort
  wait_http "${GATEWAY_URL}/ready" "API ready" 30 || warn "/ready not OK yet (DB may still be migrating)"

  wait_http "${DASHBOARD_URL}" "Dashboard" 30 || warn "Dashboard image may still be starting — refresh in a minute"
}

build_installer_assets() {
  log "Building Linux agent installer assets…"
  # shellcheck disable=SC1091
  [[ -f "${HOME}/.cargo/env" ]] && source "${HOME}/.cargo/env"
  need_cmd cargo
  bash "${ROOT}/scripts/build-linux-installer.sh"
  ok "Installer assets in ${INSTALLER_DIR}"
  log "Recreating API so it remounts installer assets…"
  compose up -d --force-recreate api kong dashboard || compose up -d
}

# ── main ─────────────────────────────────────────────────────────────

print_banner

[[ -f "${COMPOSE_FILE}" ]] || die "Cannot find ${COMPOSE_FILE}. Clone the full AI-SPM repo first."

case "${MODE}" in
  status)
    need_cmd docker
    show_status
    exit 0
    ;;
  down)
    need_cmd docker
    do_down
    exit 0
    ;;
esac

if ! is_ubuntu; then
  warn "This script targets Ubuntu/Debian. Continuing anyway…"
fi

if [[ "$(id -u)" -eq 0 && -z "${SUDO_USER:-}" ]]; then
  warn "Running as root. Prefer: sudo -u YOUR_USER ./scripts/deploy-ubuntu.sh"
fi

if [[ "${DO_APT}" -eq 1 ]]; then
  install_apt_base
else
  need_cmd docker
  docker compose version >/dev/null 2>&1 || die "docker compose plugin missing"
fi

if [[ "${DO_DEV}" -eq 1 ]]; then
  install_dev_tools
fi

if [[ "${DO_INSTALLER}" -eq 1 ]]; then
  install_rust_if_needed
fi

need_cmd curl
prepare_env_files
build_and_up

if [[ "${DO_INSTALLER}" -eq 1 ]]; then
  build_installer_assets
fi

print_summary
ok "Deploy finished successfully."
exit 0
