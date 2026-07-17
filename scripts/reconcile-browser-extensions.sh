#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-install}"

EXT_INSTALL_DIR="/opt/ai-spm/browser-extension"
EXT_KEY="/opt/ai-spm/extension-key.pem"
EXT_CRX="/opt/ai-spm/ai-spm-prompt-guard.crx"
EXT_XPI="/opt/ai-spm/ai-spm-prompt-guard.xpi"
EXT_XPI_SIGNED="/opt/ai-spm/ai-spm-prompt-guard-signed.xpi"
EXT_ID_FILE="/opt/ai-spm/extension-id"
# Snap Firefox (default on Ubuntu) is sandboxed and cannot read /opt or most of
# /etc. It CAN read /etc/firefox/policies (where it reads policies.json), so the
# XPI must be staged in that exact directory for both snap and deb Firefox.
FIREFOX_XPI_DEPLOY="/etc/firefox/policies/ai-spm-prompt-guard.xpi"

compute_extension_id() {
  python3 - "$1" <<'PY'
import hashlib, subprocess, sys
der = subprocess.check_output(["openssl", "rsa", "-in", sys.argv[1], "-pubout", "-outform", "DER"])
d = hashlib.sha256(der).digest()
print("".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0x0F)) for b in d[:16]))
PY
}

read_manifest_field() {
  local python_expr="$1"
  python3 - "$EXT_INSTALL_DIR/manifest.json" "$python_expr" <<'PY'
import json, sys
path = sys.argv[1]
expr = sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
print(eval(expr, {"data": data}))
PY
}

ext_version() {
  read_manifest_field "data['version']"
}

firefox_extension_id() {
  read_manifest_field "data.get('browser_specific_settings', {}).get('gecko', {}).get('id', 'prompt-guard@aispm.io')"
}

# Read manifest version from a packaged .crx or .xpi (zip).
packaged_extension_version() {
  local artifact="$1"
  python3 - "$artifact" <<'PY'
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

write_extension_updates_xml() {
  local ext_id="$1"
  local version="$2"
  local dest="/opt/ai-spm/updates.xml"
  install -d -m 0755 /opt/ai-spm
  cat > "$dest" <<EOF
<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='${ext_id}'>
    <updatecheck codebase='http://127.0.0.1:8092/extension/ai-spm-prompt-guard.crx' version='${version}' />
  </app>
</gupdate>
EOF
  chmod 644 "$dest"
}

write_json_file() {
  local path="$1"
  local content="$2"
  install -d -m 0755 "$(dirname "$path")"
  printf '%s\n' "$content" > "$path"
  chmod 644 "$path"
}

remove_file_if_exists() {
  local path="$1"
  rm -f "$path"
}

is_installed_command() {
  command -v "$1" >/dev/null 2>&1
}

# True when any source file under the extension dir is newer than the artifact
# (so we repackage after an update instead of serving a stale build).
source_newer_than() {
  local artifact="$1"
  [[ ! -f "$artifact" ]] && return 0
  local newer
  newer="$(find "$EXT_INSTALL_DIR" -type f -newer "$artifact" -print -quit 2>/dev/null || true)"
  [[ -n "$newer" ]]
}

ensure_xpi_packaged() {
  local manifest_ver packaged_ver=""
  manifest_ver="$(ext_version)"
  if [[ -f "$EXT_XPI" ]]; then
    packaged_ver="$(packaged_extension_version "$EXT_XPI")"
  fi
  if [[ -f "$EXT_XPI" && "$packaged_ver" == "$manifest_ver" ]] && ! source_newer_than "$EXT_XPI"; then
    return 0
  fi
  python3 - <<PY
import pathlib, zipfile
src = pathlib.Path("${EXT_INSTALL_DIR}")
dst = pathlib.Path("${EXT_XPI}")
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in src.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(src))
PY
  chmod 644 "$EXT_XPI"
}

ensure_crx_packaged() {
  local manifest_ver packaged_ver=""
  manifest_ver="$(ext_version)"
  if [[ -f "$EXT_CRX" ]]; then
    packaged_ver="$(packaged_extension_version "$EXT_CRX")"
  fi
  if [[ -f "$EXT_CRX" && -f "$EXT_ID_FILE" && "$packaged_ver" == "$manifest_ver" ]] && ! source_newer_than "$EXT_CRX"; then
    return 0
  fi
  if [[ ! -f "$EXT_KEY" ]]; then
    return 0
  fi

  local packer=""
  for cmd in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge microsoft-edge-stable brave-browser vivaldi; do
    if is_installed_command "$cmd"; then
      packer="$cmd"
      break
    fi
  done

  if [[ -z "$packer" ]]; then
    return 0
  fi

  local pack_dir="/tmp/ai-spm-reconcile-ext-$$"
  rm -rf "$pack_dir" "${pack_dir}.pem" "${pack_dir}.crx"
  cp -a "$EXT_INSTALL_DIR" "$pack_dir"
  cp "$EXT_KEY" "${pack_dir}.pem"
  "$packer" --pack-extension="$pack_dir" --pack-extension-key="${pack_dir}.pem" >/dev/null 2>&1 || true
  if [[ -f "${pack_dir}.crx" ]]; then
    install -d -m 0755 "$(dirname "$EXT_CRX")"
    install -m 0644 "${pack_dir}.crx" "$EXT_CRX"
  fi
  if [[ ! -f "$EXT_ID_FILE" ]]; then
    compute_extension_id "$EXT_KEY" > "$EXT_ID_FILE"
  fi
  rm -rf "$pack_dir" "${pack_dir}.pem" "${pack_dir}.crx" 2>/dev/null || true
}

install_chromium_policy() {
  local policy_dir="$1"
  local ext_id="$2"
  local browser_label="$3"
  # Forcelist + ExtensionSettings: enterprise install/reinstall (required after we
  # clear Preferences). external_crx JSON handles version bumps on restart.
  local policy_json
  policy_json="$(cat <<EOF
{
  "ExtensionInstallForcelist": [
    "${ext_id};http://127.0.0.1:8092/extension/updates.xml"
  ],
  "ExtensionSettings": {
    "${ext_id}": {
      "installation_mode": "force_installed",
      "update_url": "http://127.0.0.1:8092/extension/updates.xml",
      "toolbar_pin": "force_pinned"
    }
  },
  "ExtensionInstallSources": ["http://127.0.0.1:8092/*", "file:///opt/ai-spm/*"],
  "IncognitoModeAvailability": 1,
  "InPrivateModeAvailability": 1
}
EOF
)"
  write_json_file "${policy_dir}/ai-spm-prompt-guard.json" "$policy_json"
  echo "  ${browser_label}: policy installed at ${policy_dir} (Incognito disabled)"
}

install_external_json() {
  local ext_dir="$1"
  local ext_id="$2"
  local version="$3"
  local browser_label="$4"
  local ext_json
  ext_json="$(cat <<EOF
{
  "external_crx": "${EXT_CRX}",
  "external_version": "${version}"
}
EOF
)"
  install -d -m 0755 "${ext_dir}"
  write_json_file "${ext_dir}/${ext_id}.json" "$ext_json"
  echo "  ${browser_label}: external install file written to ${ext_dir}/${ext_id}.json"
}

# Per-user Chrome external extension JSON (fallback when system paths are not scanned).
# Works under sudo (SUDO_USER) and pkexec (PKEXEC_UID / AISPM_DESKTOP_USER).
resolve_desktop_user() {
  local u="${AISPM_DESKTOP_USER:-}"
  if [[ -n "${u}" && "${u}" != "root" ]]; then
    echo "${u}"
    return 0
  fi
  u="${SUDO_USER:-}"
  if [[ -n "${u}" && "${u}" != "root" ]]; then
    echo "${u}"
    return 0
  fi
  if [[ -n "${PKEXEC_UID:-}" ]]; then
    u="$(getent passwd "${PKEXEC_UID}" | cut -d: -f1 || true)"
    if [[ -n "${u}" && "${u}" != "root" ]]; then
      echo "${u}"
      return 0
    fi
  fi
  echo ""
}

install_user_chrome_external() {
  local ext_id="$1"
  local version="$2"
  local desktop_user
  desktop_user="$(resolve_desktop_user)"
  local desktop_home=""
  [[ -z "${desktop_user}" ]] && return 0
  desktop_home="$(getent passwd "${desktop_user}" | cut -d: -f6)"
  [[ -z "${desktop_home}" ]] && return 0
  local ext_dir="${desktop_home}/.config/google-chrome/External Extensions"
  install -d -m 0755 "${ext_dir}"
  chown -R "${desktop_user}:${desktop_user}" "${ext_dir}" 2>/dev/null || true
  install_external_json "${ext_dir}" "${ext_id}" "${version}" "Chrome (user profile)"
  chown "${desktop_user}:${desktop_user}" "${ext_dir}/${ext_id}.json" 2>/dev/null || true
}

install_firefox_policy() {
  local firefox_id="$1"
  local xpi_path="$2"
  local policy_json
  # private_browsing:true force-enables the extension in Private Windows AND
  # locks the toggle so the user cannot disable it (Firefox enterprise policy).
  policy_json="$(cat <<EOF
{
  "policies": {
    "ExtensionSettings": {
      "${firefox_id}": {
        "installation_mode": "force_installed",
        "install_url": "file://${xpi_path}",
        "private_browsing": true
      }
    }
  }
}
EOF
)"
  write_json_file "/etc/firefox/policies/policies.json" "$policy_json"
  echo "  Firefox: policy installed at /etc/firefox/policies/policies.json (private browsing forced)"
}

remove_chromium_policy() {
  local policy_dir="$1"
  remove_file_if_exists "${policy_dir}/ai-spm-prompt-guard.json"
}

remove_external_json() {
  local ext_dir="$1"
  local ext_id="$2"
  remove_file_if_exists "${ext_dir}/${ext_id}.json"
}

remove_firefox_policy() {
  remove_file_if_exists "/etc/firefox/policies/policies.json"
  remove_file_if_exists "$FIREFOX_XPI_DEPLOY"
}

# Drop leftover Chrome external-extension JSON from prior installs (new RSA key → new ID).
purge_stale_chromium_external_extensions() {
  local keep_id="${1:-}"
  local desktop_user desktop_home
  desktop_user="$(resolve_desktop_user)"
  desktop_home=""
  [[ -n "${desktop_user}" ]] && desktop_home="$(getent passwd "${desktop_user}" | cut -d: -f6)"

  local -a dirs=(
    /opt/google/chrome/extensions
    /usr/share/google-chrome/extensions
    /usr/share/chromium/extensions
    /usr/share/chromium-browser/extensions
    /usr/share/microsoft-edge/extensions
    /opt/microsoft/msedge/extensions
    /opt/vivaldi/extensions
    /usr/share/vivaldi/extensions
  )
  if [[ -n "${desktop_home}" ]]; then
    dirs+=("${desktop_home}/.config/google-chrome/External Extensions")
    dirs+=("${desktop_home}/.config/chromium/External Extensions")
  fi

  local dir f id
  for dir in "${dirs[@]}"; do
    [[ -d "${dir}" ]] || continue
    for f in "${dir}"/*.json; do
      [[ -f "${f}" ]] || continue
      grep -qE 'ai-spm-prompt-guard\.crx|/opt/ai-spm/' "${f}" 2>/dev/null || continue
      id="$(basename "${f}" .json)"
      if [[ -n "${keep_id}" && "${id}" == "${keep_id}" ]]; then
        continue
      fi
      rm -f "${f}"
      echo "  Purged stale Chromium external extension: ${f}"
    done
  done
}

# Stage the chosen XPI into /etc/firefox so sandboxed (snap) Firefox can read it.
# Prints the deployed path on success, empty on failure.
stage_firefox_xpi() {
  local src="$1"
  install -d -m 0755 /etc/firefox/policies
  if install -m 0644 "$src" "$FIREFOX_XPI_DEPLOY" 2>/dev/null; then
    echo "$FIREFOX_XPI_DEPLOY"
  fi
}

install_all() {
  if [[ ! -f "$EXT_INSTALL_DIR/manifest.json" ]]; then
    echo "Browser extension artifacts missing; nothing to reconcile."
    exit 0
  fi

  purge_stale_chromium_external_extensions

  ensure_xpi_packaged
  ensure_crx_packaged

  if [[ ! -f "$EXT_ID_FILE" ]]; then
    echo "Chromium extension ID missing; Chromium-family deployment skipped."
  fi

  local ext_id version firefox_id
  ext_id="$(cat "$EXT_ID_FILE" 2>/dev/null || true)"
  version="$(ext_version)"
  firefox_id="$(firefox_extension_id)"

  echo "Reconciling managed browser extensions..."

  if [[ -n "$ext_id" ]]; then
    install_chromium_policy "/etc/opt/chrome/policies/managed" "$ext_id" "Chrome"
    install_chromium_policy "/etc/chromium/policies/managed" "$ext_id" "Chromium"
    install_chromium_policy "/etc/chromium-browser/policies/managed" "$ext_id" "Chromium"
    install_chromium_policy "/etc/opt/edge/policies/managed" "$ext_id" "Edge"
    install_chromium_policy "/etc/brave/policies/managed" "$ext_id" "Brave"
    install_chromium_policy "/etc/brave-browser/policies/managed" "$ext_id" "Brave"
    install_chromium_policy "/etc/opt/vivaldi/policies/managed" "$ext_id" "Vivaldi"

    if [[ -f "$EXT_CRX" ]]; then
      if is_installed_command "google-chrome" || is_installed_command "google-chrome-stable"; then
        install_external_json "/opt/google/chrome/extensions" "$ext_id" "$version" "Chrome"
        install_external_json "/usr/share/google-chrome/extensions" "$ext_id" "$version" "Chrome"
        install_user_chrome_external "$ext_id" "$version"
      fi

      if is_installed_command "chromium" || is_installed_command "chromium-browser"; then
        install_external_json "/usr/share/chromium/extensions" "$ext_id" "$version" "Chromium"
        install_external_json "/usr/share/chromium-browser/extensions" "$ext_id" "$version" "Chromium"
      fi

      if is_installed_command "microsoft-edge" || is_installed_command "microsoft-edge-stable"; then
        install_external_json "/usr/share/microsoft-edge/extensions" "$ext_id" "$version" "Edge"
        install_external_json "/opt/microsoft/msedge/extensions" "$ext_id" "$version" "Edge"
      fi

      if is_installed_command "vivaldi" || [[ -x "/opt/vivaldi/vivaldi" ]]; then
        install_external_json "/opt/vivaldi/extensions" "$ext_id" "$version" "Vivaldi"
        install_external_json "/usr/share/vivaldi/extensions" "$ext_id" "$version" "Vivaldi"
      fi
    fi
  fi

  if is_installed_command "firefox" || [[ -d "/etc/firefox" ]]; then
    local ff_src="" ff_signed=0 manifest_ver signed_ver=""
    manifest_ver="$(ext_version)"
    if [[ -f "$EXT_XPI_SIGNED" ]]; then
      signed_ver="$(packaged_extension_version "$EXT_XPI_SIGNED")"
    fi
    if [[ -n "$signed_ver" && "$signed_ver" == "$manifest_ver" ]]; then
      ff_src="$EXT_XPI_SIGNED"
      ff_signed=1
    elif [[ -n "$signed_ver" && -f "$EXT_XPI_SIGNED" ]]; then
      # Release Firefox rejects unsigned XPI — use stale signed build so the
      # extension at least installs; re-sign for the latest masking fixes.
      ff_src="$EXT_XPI_SIGNED"
      ff_signed=1
      echo "  Firefox: using signed v${signed_ver} (source is v${manifest_ver})."
      echo "  Firefox: re-sign with scripts/sign-firefox-extension.sh for latest fixes."
    elif [[ -f "$EXT_XPI" ]]; then
      ff_src="$EXT_XPI"
    fi

    if [[ -z "$ff_src" ]]; then
      echo "  Firefox: skipped policy because no XPI is available."
    else
      local ff_deployed
      ff_deployed="$(stage_firefox_xpi "$ff_src")"
      if [[ -z "$ff_deployed" ]]; then
        echo "  Firefox: ERROR — could not stage XPI into /etc/firefox."
      else
        install_firefox_policy "$firefox_id" "$ff_deployed"
        if [[ "$ff_signed" -eq 1 ]]; then
          echo "  Firefox: using Mozilla-signed XPI at ${ff_deployed} (snap + deb compatible)."
        else
          echo "  Firefox: WARNING — using UNSIGNED XPI. Standard Firefox release will"
          echo "           reject it. Provide a signed XPI at ${EXT_XPI_SIGNED}"
          echo "           (see scripts/sign-firefox-extension.sh) or deploy Firefox ESR."
        fi
      fi
    fi
  fi

  if [[ -n "$ext_id" ]]; then
    write_extension_updates_xml "$ext_id" "$version"
    echo "  Chromium: updates.xml written (v${version})"
  fi
}

remove_all() {
  local ext_id=""
  [[ -f "$EXT_ID_FILE" ]] && ext_id="$(cat "$EXT_ID_FILE" 2>/dev/null || true)"

  echo "Removing managed browser extension integration..."
  remove_chromium_policy "/etc/opt/chrome/policies/managed"
  remove_chromium_policy "/etc/chromium/policies/managed"
  remove_chromium_policy "/etc/chromium-browser/policies/managed"
  remove_chromium_policy "/etc/opt/edge/policies/managed"
  remove_chromium_policy "/etc/brave/policies/managed"
  remove_chromium_policy "/etc/brave-browser/policies/managed"
  remove_chromium_policy "/etc/opt/vivaldi/policies/managed"
  remove_firefox_policy

  if [[ -n "$ext_id" ]]; then
    remove_external_json "/opt/google/chrome/extensions" "$ext_id"
    remove_external_json "/usr/share/google-chrome/extensions" "$ext_id"
    remove_external_json "/usr/share/chromium/extensions" "$ext_id"
    remove_external_json "/usr/share/chromium-browser/extensions" "$ext_id"
    remove_external_json "/usr/share/microsoft-edge/extensions" "$ext_id"
    remove_external_json "/opt/microsoft/msedge/extensions" "$ext_id"
    remove_external_json "/opt/vivaldi/extensions" "$ext_id"
    remove_external_json "/usr/share/vivaldi/extensions" "$ext_id"
  fi
  purge_stale_chromium_external_extensions
}

case "$ACTION" in
  install)
    install_all
    ;;
  remove)
    remove_all
    ;;
  purge-stale)
    purge_stale_chromium_external_extensions
    ;;
  *)
    echo "Usage: $0 [install|remove|purge-stale]" >&2
    exit 1
    ;;
esac
