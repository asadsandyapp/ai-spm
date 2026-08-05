#!/usr/bin/env bash
# Sprint 1 exit demo: signup → verify → admin login → agent register → inspect prompt → audit.
# Requires API on BASE (default Kong http://localhost:8090 or uvicorn :8000).
set -euo pipefail

BASE="${AISPM_BASE_URL:-http://localhost:8090}"
EMAIL="${DEMO_EMAIL:-demo-$(date +%s)@example.com}"
PASSWORD="${DEMO_PASSWORD:-SecurePass123!}"
COMPANY="${DEMO_COMPANY:-Demo Corp $(date +%s)}"

echo "==> Health"
curl -sf "$BASE/health" | tee /tmp/aispm-health.json
echo
curl -sf "$BASE/ready" | tee /tmp/aispm-ready.json || echo "(ready optional if DB warming)"
echo

echo "==> Signup ($EMAIL)"
SIGNUP=$(curl -sf -X POST "$BASE/public/v1/signup" \
  -H "Content-Type: application/json" \
  -d "{\"company_name\":\"$COMPANY\",\"admin_email\":\"$EMAIL\",\"admin_password\":\"$PASSWORD\",\"admin_full_name\":\"Demo Admin\"}")
echo "$SIGNUP" | tee /tmp/aispm-signup.json
ORG_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['org_id'])" <<<"$SIGNUP")
VTOKEN=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('verification_token') or '')" <<<"$SIGNUP")
if [[ -z "$VTOKEN" ]]; then
  echo "No verification_token in response (production mode?). Check API logs." >&2
  exit 1
fi

echo "==> Verify email"
VERIFY=$(curl -sf "$BASE/public/v1/verify-email?token=$VTOKEN")
echo "$VERIFY" | tee /tmp/aispm-verify.json
ORG_TOKEN=$(python3 -c "import json,sys; print(json.load(sys.stdin)['org_token'])" <<<"$VERIFY")

echo "==> Admin login"
LOGIN=$(curl -sf -X POST "$BASE/admin/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
echo "$LOGIN" | tee /tmp/aispm-login.json
JWT=$(python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])" <<<"$LOGIN")

echo "==> Agent register"
REG=$(curl -sf -X POST "$BASE/agent/v1/register" \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: $ORG_ID" \
  -d "{\"org_token\":\"$ORG_TOKEN\",\"hostname\":\"demo-host\",\"agent_version\":\"0.1.0\",\"os_version\":\"linux\"}")
echo "$REG" | tee /tmp/aispm-register.json
AGENT_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$REG")
SESSION_TOKEN=$(python3 -c "import json,sys; print(json.load(sys.stdin)['session_token'])" <<<"$REG")

echo "==> Prompt inspect_only (PII email)"
# Every /agent/v1/* call other than /register requires the per-agent session
# token issued at registration (Bearer), not just the X-Org-ID/X-Agent-ID
# pair — see tenant/middleware.py::_verify_agent_session_token.
PROMPT=$(curl -sf -X POST "$BASE/agent/v1/prompt" \
  -H "Content-Type: application/json" \
  -H "X-Org-ID: $ORG_ID" \
  -H "X-Agent-ID: $AGENT_ID" \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -d "{\"inspect_only\":true,\"provider\":\"openai\",\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\"Contact jane@acme.com about payroll\"}]}")
echo "$PROMPT" | tee /tmp/aispm-prompt.json

echo "==> Admin audit (first page)"
curl -sf "$BASE/admin/v1/audit?limit=5" \
  -H "Authorization: Bearer $JWT" | tee /tmp/aispm-audit.json
echo

echo "OK — Sprint 1 exit path complete"
echo "  ORG_ID=$ORG_ID"
echo "  AGENT_ID=$AGENT_ID"
echo "  AISPM_ORG_TOKEN=(from verify — store securely)"
