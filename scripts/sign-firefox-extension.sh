#!/usr/bin/env bash
#
# One-time Firefox extension signing for enterprise distribution.
#
# Standard Firefox release builds only install Mozilla-signed extensions, even
# via enterprise force-install policy. This script produces a signed, self-
# distributed (unlisted) XPI using Mozilla's AMO signing API. You run it ONCE
# as the vendor; the resulting signed XPI is then shipped with the agent and
# force-installed on every endpoint's Firefox — regardless of how the user
# installed Firefox.
#
# Prerequisites:
#   1. A free Mozilla add-on developer account:  https://addons.mozilla.org/
#   2. API credentials (JWT issuer + secret):
#        https://addons.mozilla.org/developers/addon/api/key/
#   3. Node.js + web-ext:   npm install -g web-ext
#
# Usage:
#   AMO_JWT_ISSUER="user:12345:67"  \
#   AMO_JWT_SECRET="abc...secret"    \
#   ./scripts/sign-firefox-extension.sh
#
# Output:
#   browser-extension/ai-spm-prompt-guard-signed.xpi
#
# The installer (scripts/install-agent.sh) auto-detects this file and deploys
# it to Firefox via enterprise policy. No per-user action required.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXT_SRC="${REPO_ROOT}/browser-extension"
OUT_XPI="${REPO_ROOT}/browser-extension/ai-spm-prompt-guard-signed.xpi"
WORK_DIR="$(mktemp -d)"

cleanup() { rm -rf "${WORK_DIR}"; }
trap cleanup EXIT

if [[ -z "${AMO_JWT_ISSUER:-}" || -z "${AMO_JWT_SECRET:-}" ]]; then
  echo "ERROR: set AMO_JWT_ISSUER and AMO_JWT_SECRET (get them from" >&2
  echo "       https://addons.mozilla.org/developers/addon/api/key/)." >&2
  exit 1
fi

if ! command -v web-ext >/dev/null 2>&1; then
  echo "ERROR: web-ext not found. Install with: npm install -g web-ext" >&2
  exit 1
fi

ext_id="$(python3 -c "import json;print(json.load(open('${EXT_SRC}/manifest.json'))['browser_specific_settings']['gecko']['id'])")"
echo "→ Signing Firefox extension (id=${ext_id}) via AMO unlisted channel..."

# web-ext sign downloads the Mozilla-signed XPI for the unlisted channel.
web-ext sign \
  --source-dir "${EXT_SRC}" \
  --artifacts-dir "${WORK_DIR}" \
  --channel unlisted \
  --api-key "${AMO_JWT_ISSUER}" \
  --api-secret "${AMO_JWT_SECRET}"

signed="$(find "${WORK_DIR}" -name '*.xpi' -print -quit)"
if [[ -z "${signed}" ]]; then
  echo "ERROR: signing produced no XPI. Check AMO submission status/logs." >&2
  exit 1
fi

cp "${signed}" "${OUT_XPI}"
echo "✓ Signed XPI written to ${OUT_XPI}"
echo "  Ship this file with the agent. Re-run scripts/install-agent.sh to deploy."
