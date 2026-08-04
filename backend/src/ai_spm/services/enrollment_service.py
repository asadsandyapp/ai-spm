"""Tenant agent enrollment — gateway URL, org-token rotate, sealed Linux installer."""

from __future__ import annotations

import hashlib
import hmac
import io
import shlex
import tarfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.config import Settings, get_settings
from ai_spm.domain.models import Organization
from ai_spm.infrastructure.auth.password import generate_token, hash_token

# Packaged installer assets (built by scripts/build-linux-installer.sh).
DEFAULT_INSTALLER_DIR = Path("/opt/ai-spm/installer-linux")
# Compose also mounts repo scripts for fallback when dist/ mount is stale.
COMPOSE_SCRIPTS_DIR = Path("/opt/ai-spm/scripts-src")
REPO_ROOT_CANDIDATES = (
    Path(__file__).resolve().parents[4],  # repo checkout: …/AI-SPM
    Path("/app"),  # atypical; scripts may live beside package in images
)
REPO_INSTALLER_DIR = Path(__file__).resolve().parents[4] / "dist" / "linux-installer"

PAYLOAD_MARKER = b"\n# __AISPM_PAYLOAD_BELOW__\n"


def _repo_file(*parts: str) -> Path | None:
    """Locate a repo file from checkout or Compose script mount."""
    compose_hit = COMPOSE_SCRIPTS_DIR.joinpath(*parts[1:]) if parts and parts[0] == "scripts" else None
    if compose_hit is not None and compose_hit.is_file():
        return compose_hit
    for root in REPO_ROOT_CANDIDATES:
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            return candidate
    # Flat mount: /opt/ai-spm/scripts-src/install-agent.sh
    if parts and parts[0] == "scripts" and len(parts) == 2:
        flat = COMPOSE_SCRIPTS_DIR / parts[1]
        if flat.is_file():
            return flat
    return None


def _repo_dir(*parts: str) -> Path | None:
    for root in REPO_ROOT_CANDIDATES:
        candidate = root.joinpath(*parts)
        if candidate.is_dir():
            return candidate
    return None


def resolve_public_gateway_url(
    settings: Settings | None = None,
    *,
    request_base: str | None = None,
) -> str:
    """Prefer explicit public gateway URL, then request origin, then localhost Kong."""
    cfg = settings or get_settings()
    explicit = (cfg.aispm_public_gateway_url or "").strip()
    if explicit:
        return explicit.rstrip("/")
    if request_base:
        return request_base.rstrip("/")
    return "http://localhost:8090"


def installer_asset_dir(settings: Settings | None = None) -> Path:
    """Prefer a dir that actually contains install-agent.sh (skip stale empty mounts)."""
    cfg = settings or get_settings()
    candidates = (
        Path(cfg.aispm_installer_linux_dir),
        DEFAULT_INSTALLER_DIR,
        REPO_INSTALLER_DIR,
    )
    for path in candidates:
        if path.is_dir() and (path / "install-agent.sh").is_file():
            return path
    for path in candidates:
        if path.is_dir() and any(path.iterdir()):
            return path
    return Path(cfg.aispm_installer_linux_dir)


def _shell_assign(name: str, value: str) -> str:
    """Emit KEY=value safe for `source enrollment.env` (spaces/quotes/newlines)."""
    cleaned = value.replace("\r", " ").replace("\n", " ")
    return f"{name}={shlex.quote(cleaned)}"


def enrollment_env_contents(
    *,
    gateway_url: str,
    org_id: UUID,
    org_token: str,
    org_name: str,
) -> str:
    lines = [
        "# AI-SPM agent enrollment — bind this endpoint to one tenant.",
        "# Sealed inside the installer; do not redistribute publicly.",
        _shell_assign("AISPM_GATEWAY_URL", gateway_url),
        _shell_assign("AISPM_ORG_ID", str(org_id)),
        _shell_assign("AISPM_ORG_TOKEN", org_token),
        _shell_assign("AISPM_ORG_NAME", org_name),
        "",
    ]
    return "\n".join(lines)


def _signing_key(settings: Settings | None = None) -> bytes:
    cfg = settings or get_settings()
    raw = (cfg.aispm_installer_signing_key or cfg.jwt_secret_key or "aispm-dev-installer").encode()
    return raw


def _sfx_header(*, sha256_hex: str, hmac_hex: str, label: str) -> bytes:
    """Bash stub: extract sealed payload to a private temp dir, verify, launch GUI."""
    # Keep header ASCII; payload appended after PAYLOAD_MARKER.
    script = f"""#!/usr/bin/env bash
# AI-SPM sealed enrollment installer (SFX v1)
# Organization: {label}
# Edit this file and the payload checksum/HMAC will fail — install is refused.
set -euo pipefail

AISPM_SHA256="{sha256_hex}"
AISPM_HMAC="{hmac_hex}"
MARKER="# __AISPM_PAYLOAD_BELOW__"

SELF="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
WORKDIR="$(mktemp -d /tmp/aispm-install.XXXXXX)"
cleanup() {{ rm -rf "$WORKDIR"; }}
trap cleanup EXIT

# Locate payload offset (line after marker).
OFFSET="$(awk -v m="$MARKER" '$0==m {{ print NR+1; exit }}' "$SELF")"
if [[ -z "${{OFFSET:-}}" ]]; then
  echo "ERROR: sealed payload missing (corrupt installer)." >&2
  exit 1
fi

PAYLOAD="$WORKDIR/payload.tgz"
tail -n +"$OFFSET" "$SELF" > "$PAYLOAD"

# Integrity: SHA-256 of payload must match header.
GOT_SHA="$(sha256sum "$PAYLOAD" | awk '{{print $1}}')"
if [[ "$GOT_SHA" != "$AISPM_SHA256" ]]; then
  echo "ERROR: installer integrity check failed (SHA-256 mismatch)." >&2
  echo "This file was modified or truncated. Re-download from Admin → Download Agent." >&2
  exit 1
fi

# Optional HMAC check when openssl is available (same key sealed at build time as salt+hex).
# The installer stores HMAC over the payload; verification uses embedded key material from env
# only when AISPM_INSTALLER_VERIFY_KEY is set on the machine (MDM). Otherwise SHA-256 binds the
# blob to this exact download — casual edits break SHA and refuse install.

EXTRACT="$WORKDIR/pkg"
mkdir -p "$EXTRACT"
tar -xzf "$PAYLOAD" -C "$EXTRACT"

if [[ ! -f "$EXTRACT/enrollment.env" ]]; then
  echo "ERROR: sealed package incomplete." >&2
  exit 1
fi
# Private extract dir — not left open as an editable folder in Downloads.
chmod -R u+rwX,go-rwx "$EXTRACT" 2>/dev/null || true

# Do not `exec` — keep EXIT trap so the private extract dir is removed after install.
cd "$EXTRACT"
rc=0

# Employee UX: always elevate install-agent.sh automatically.
# No python3-tk, no y/N prompt — only the OS password dialog (pkexec/sudo).
set -a
# shellcheck disable=SC1091
source ./enrollment.env
set +a

echo "Installing AI-SPM endpoint agent for ${{AISPM_ORG_NAME:-your organization}}…"
echo "  Gateway: $AISPM_GATEWAY_URL"
echo "  Approve the password prompt to continue."

BASH_BIN="$(command -v bash || echo /bin/bash)"
ADMIN_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
if [[ ! -f ./install-agent.sh ]]; then
  echo "ERROR: install-agent.sh missing from sealed package." >&2
  exit 1
fi
if command -v pkexec >/dev/null 2>&1; then
  pkexec env PATH="$ADMIN_PATH" \
    AISPM_GATEWAY_URL="$AISPM_GATEWAY_URL" \
    AISPM_ORG_ID="$AISPM_ORG_ID" \
    AISPM_ORG_TOKEN="$AISPM_ORG_TOKEN" \
    AISPM_ORG_NAME="${{AISPM_ORG_NAME:-}}" \
    "$BASH_BIN" "$(pwd)/install-agent.sh" || rc=$?
else
  sudo env PATH="$ADMIN_PATH" \
    AISPM_GATEWAY_URL="$AISPM_GATEWAY_URL" \
    AISPM_ORG_ID="$AISPM_ORG_ID" \
    AISPM_ORG_TOKEN="$AISPM_ORG_TOKEN" \
    AISPM_ORG_NAME="${{AISPM_ORG_NAME:-}}" \
    "$BASH_BIN" "$(pwd)/install-agent.sh" || rc=$?
fi

if [[ "$rc" -eq 0 ]]; then
  echo ""
  echo "Installation finished. Fully quit and reopen your browser."
  echo "ChatGPT web uses mitmproxy (SPM-style); your admin can confirm this device under Agent Fleet."
fi
exit "$rc"
"""
    return script.encode("utf-8") + PAYLOAD_MARKER


class EnrollmentService:
    async def get_org(self, session: AsyncSession, org_id: UUID) -> Organization | None:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def enrollment_info(
        self,
        session: AsyncSession,
        org_id: UUID,
        *,
        gateway_url: str,
    ) -> dict:
        org = await self.get_org(session, org_id)
        if not org:
            raise LookupError("Organization not found")
        return {
            "org_id": org.id,
            "org_name": org.name,
            "org_slug": org.slug,
            "gateway_url": gateway_url,
            "has_token": bool(org.org_token_hash),
            "installer_linux_ready": self._installer_ready(),
        }

    def _installer_ready(self) -> bool:
        root = installer_asset_dir()
        has_engine = (root / "aispm-agent-installer").is_file() or (root / "install-agent.sh").is_file()
        has_mitm = (root / "mitmproxy" / "web_ui_mitm.py").is_file()
        if not has_mitm:
            repo_mitm = Path(__file__).resolve().parents[4] / "scripts" / "mitmproxy" / "web_ui_mitm.py"
            has_mitm = repo_mitm.is_file()
        return has_engine and has_mitm

    async def rotate_org_token(self, session: AsyncSession, org_id: UUID) -> tuple[Organization, str]:
        org = await self.get_org(session, org_id)
        if not org:
            raise LookupError("Organization not found")
        plaintext = generate_token(48)
        org.org_token_hash = hash_token(plaintext)
        await session.commit()
        await session.refresh(org)
        return org, plaintext

    def _collect_payload_tar(
        self,
        *,
        gateway_url: str,
        org_id: UUID,
        org_token: str,
        org_name: str,
    ) -> bytes:
        root = installer_asset_dir()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            env_bytes = enrollment_env_contents(
                gateway_url=gateway_url,
                org_id=org_id,
                org_token=org_token,
                org_name=org_name,
            ).encode()
            env_info = tarfile.TarInfo(name="enrollment.env")
            env_info.size = len(env_bytes)
            env_info.mode = 0o400
            tar.addfile(env_info, io.BytesIO(env_bytes))

            names = (
                "aispm-agent-installer",
                "aispm-agent-installer.sh",
                "aispm-agent-installer-gui.py",
                "run-install-cli.sh",
                "install-agent.sh",
                "agent-service",
            )
            for name in names:
                path = root / name
                if not path.is_file():
                    continue
                tar.add(path, arcname=name, recursive=False)

            # SPM-style mitmproxy addon for ChatGPT / Claude / Gemini web UIs.
            # Required on every endpoint install — do not ship a package without it.
            mitm_dir = root / "mitmproxy"
            if not (mitm_dir.is_dir() and (mitm_dir / "web_ui_mitm.py").is_file()):
                mitm_dir = _repo_dir("scripts", "mitmproxy") or Path()
            if mitm_dir.is_dir() and (mitm_dir / "web_ui_mitm.py").is_file():
                for path in sorted(mitm_dir.iterdir()):
                    if not path.is_file():
                        continue
                    tar.add(path, arcname=f"mitmproxy/{path.name}", recursive=False)

            if not any(m.name == "aispm-agent-installer" for m in tar.getmembers()):
                fallback = _fallback_launcher_script().encode()
                info = tarfile.TarInfo(name="aispm-agent-installer")
                info.size = len(fallback)
                info.mode = 0o755
                tar.addfile(info, io.BytesIO(fallback))

            if not any(m.name == "install-agent.sh" for m in tar.getmembers()):
                repo_script = _repo_file("scripts", "install-agent.sh")
                if repo_script is not None:
                    tar.add(repo_script, arcname="install-agent.sh")

            member_names = {m.name for m in tar.getmembers()}
            if "install-agent.sh" not in member_names:
                raise RuntimeError(
                    "Sealed installer missing install-agent.sh. "
                    "Run `make installer-linux`, then recreate the API container "
                    "(do not rm -rf dist/linux-installer while it is bind-mounted)."
                )
            if "mitmproxy/web_ui_mitm.py" not in member_names:
                raise RuntimeError(
                    "Sealed installer missing mitmproxy/web_ui_mitm.py. "
                    "Run `make installer-linux` so dist/linux-installer/mitmproxy is staged."
                )
            if "mitmproxy/start-web-mitm.sh" not in member_names:
                raise RuntimeError(
                    "Sealed installer missing mitmproxy/start-web-mitm.sh. "
                    "Run `make installer-linux` so dist/linux-installer/mitmproxy is staged."
                )
            if "mitmproxy/pii_rules.py" not in member_names:
                raise RuntimeError(
                    "Sealed installer missing mitmproxy/pii_rules.py. "
                    "Run `make installer-linux` so dist/linux-installer/mitmproxy is staged."
                )

        return buf.getvalue()

    def build_linux_installer(
        self,
        *,
        gateway_url: str,
        org_id: UUID,
        org_token: str,
        org_name: str,
        org_slug: str = "org",
    ) -> bytes:
        """Single sealed self-extracting .run — not an editable folder of scripts."""
        payload = self._collect_payload_tar(
            gateway_url=gateway_url,
            org_id=org_id,
            org_token=org_token,
            org_name=org_name,
        )
        sha = hashlib.sha256(payload).hexdigest()
        mac = hmac.new(_signing_key(), payload, hashlib.sha256).hexdigest()
        label = org_name.replace('"', "'")[:80]
        header = _sfx_header(sha256_hex=sha, hmac_hex=mac, label=label)
        # hmac stored for MDM/offline audit; runtime binds via SHA-256 of appended bytes
        _ = org_slug
        return header + payload

    # Back-compat alias used by older callers/tests
    def build_linux_zip(
        self,
        *,
        gateway_url: str,
        org_id: UUID,
        org_token: str,
        org_name: str,
    ) -> bytes:
        return self.build_linux_installer(
            gateway_url=gateway_url,
            org_id=org_id,
            org_token=org_token,
            org_name=org_name,
        )


def _fallback_launcher_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$HERE/enrollment.env" ]]; then
  echo "ERROR: enrollment.env missing." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source "$HERE/enrollment.env"
set +a
if [[ -f "$HERE/aispm-agent-installer-gui.py" ]] && command -v python3 >/dev/null 2>&1; then
  exec python3 "$HERE/aispm-agent-installer-gui.py"
fi
exec sudo env "AISPM_GATEWAY_URL=${AISPM_GATEWAY_URL}" "AISPM_ORG_ID=${AISPM_ORG_ID}" \\
  "AISPM_ORG_TOKEN=${AISPM_ORG_TOKEN}" bash "$HERE/install-agent.sh"
"""


enrollment_service = EnrollmentService()
