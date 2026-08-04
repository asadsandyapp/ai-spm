#!/usr/bin/env python3
"""End-to-end smoke test: the real agent-service binary against a live
AI-SPM backend (deploy/docker-compose.yml), not a mock.

Registers with the actual gateway (org token + mTLS cert issuance), waits
for the heartbeat to report connected via the local /status endpoint added
in agent-core/src/status.rs, submits a PII-bearing prompt through the
agent's local /inspect, and confirms the masked (never raw) event lands in
the backend's own audit log. Then restarts the same binary and confirms
re-registration does not create a duplicate fleet entry (idempotent by
hostname - see AGENTS.md's decision log).

Usage:
    python3 scripts/e2e-smoke-test.py --agent-service target/debug/agent-service \
        --gateway-url http://localhost:8090
"""

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEV_ADMIN_EMAIL = "admin@devcorp.io"
DEV_ADMIN_PASSWORD = "DevAdminPass123!"
# Matches backend/scripts/seed_dev_tenant.py's DEV_ORG_TOKEN - fixed dev value.
DEV_ORG_TOKEN = "dev-org-token-please-change-32chars-minimum"


def http_json(method, url, body=None, headers=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def wait_for_http_200(url, timeout=120):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as e:  # noqa: BLE001 - genuinely want to retry on anything here
            last_err = e
        time.sleep(2)
    raise SystemExit(f"timed out waiting for {url}: {last_err}")


def decode_jwt_org_id(token):
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    return payload["org_id"]


def agent_env(args, org_id):
    # Deliberately disables transparent/explicit MITM and system auto-config -
    # this test only needs registration + heartbeat + local_api, and running
    # those on a CI runner shouldn't touch iptables or install a CA into the
    # system trust store. Cert paths point at a temp dir so registration's
    # save_registration_certs() doesn't need root to write /etc/ai-spm/certs.
    return {
        **os.environ,
        "AISPM_GATEWAY_URL": args.gateway_url,
        "AISPM_ORG_TOKEN": DEV_ORG_TOKEN,
        "AISPM_ORG_ID": org_id,
        "AISPM_TRANSPARENT_ENABLED": "0",
        "AISPM_EXPLICIT_PROXY_ENABLED": "0",
        "AISPM_LOCAL_API_ENABLED": "1",
        "AISPM_LOCAL_API_LISTEN": args.local_api_listen,
        "AISPM_AUTO_CONFIGURE_ENDPOINT": "0",
        "AISPM_AUTO_CONFIGURE_NETWORK": "0",
        "AISPM_LOG_JSON": "false",
        "AISPM_MTLS_CERT": args.cert_dir + "/agent.crt",
        "AISPM_MTLS_KEY": args.cert_dir + "/agent.key",
        "AISPM_MTLS_CA": args.cert_dir + "/ca.crt",
    }


def wait_for_connected(status_url, proc, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"agent-service exited early with code {proc.returncode}")
        try:
            _, snapshot = http_json("GET", status_url)
            if snapshot.get("connected"):
                return
        except Exception:  # noqa: BLE001 - server may not be listening yet
            pass
        time.sleep(2)
    raise SystemExit(f"agent-service never reported connected:true on {status_url}")


def stop(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent-service",
        required=True,
        type=os.path.abspath,
        help="path to the built agent-service binary",
    )
    parser.add_argument("--gateway-url", default="http://localhost:8090")
    parser.add_argument("--local-api-listen", default="127.0.0.1:8092")
    parser.add_argument("--cert-dir", default="/tmp/aispm-e2e-certs")
    args = parser.parse_args()

    hostname = socket.gethostname()
    status_url = f"http://{args.local_api_listen}/status"
    inspect_url = f"http://{args.local_api_listen}/inspect"

    print(f"==> waiting for backend at {args.gateway_url}/health")
    wait_for_http_200(f"{args.gateway_url}/health")

    print("==> logging in as dev tenant admin")
    status, body = http_json(
        "POST",
        f"{args.gateway_url}/admin/v1/auth/login",
        {"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD},
    )
    assert status == 200, f"admin login failed: {status} {body}"
    admin_token = body["access_token"]
    org_id = decode_jwt_org_id(admin_token)
    print(f"    org_id = {org_id}, hostname = {hostname}")

    env = agent_env(args, org_id)

    print(f"==> starting agent-service ({args.agent_service})")
    proc = subprocess.Popen([args.agent_service], env=env)
    try:
        wait_for_connected(status_url, proc)
        print("    connected")

        print("==> submitting a PII-bearing prompt through the agent's local /inspect")
        raw_email = "jane.doe@example.com"
        raw_ssn = "123-45-6789"
        _, inspect_resp = http_json(
            "POST",
            inspect_url,
            {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": f"My email is {raw_email} and SSN is {raw_ssn}"}],
            },
        )
        assert inspect_resp["decision"] == "masked", f"expected masked, got {inspect_resp}"
        masked = inspect_resp["masked_messages"][0]["content"]
        assert raw_email not in masked, f"raw email leaked into masked content: {masked!r}"
        assert raw_ssn not in masked, f"raw SSN leaked into masked content: {masked!r}"
        print(f"    masked correctly: {masked!r}")

        print("==> confirming the masked event landed in the backend audit log (masked only, no raw PII)")
        _, audit = http_json(
            "GET",
            f"{args.gateway_url}/admin/v1/audit?limit=20",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        matches = [e for e in audit if e.get("hostname") == hostname]
        assert matches, f"no audit event found for hostname={hostname}"
        event = matches[0]
        assert event["masked_content"] == masked, "audit masked_content doesn't match what the agent returned"
        assert raw_email not in json.dumps(event), "raw email leaked into the audit record"
        assert raw_ssn not in json.dumps(event), "raw SSN leaked into the audit record"
        print(f"    audit event confirmed: {event['id']}")

        print("==> confirming the agent appears in the fleet")
        _, fleet = http_json(
            "GET",
            f"{args.gateway_url}/admin/v1/agents",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        fleet_matches = [a for a in fleet if a.get("hostname") == hostname]
        assert len(fleet_matches) == 1, f"expected exactly 1 fleet entry for {hostname}, got {len(fleet_matches)}"
        first_agent_id = fleet_matches[0]["id"]
    finally:
        stop(proc)

    print("==> restarting agent-service (simulates reinstall) - must not create a duplicate fleet entry")
    proc = subprocess.Popen([args.agent_service], env=env)
    try:
        wait_for_connected(status_url, proc)
        _, fleet = http_json(
            "GET",
            f"{args.gateway_url}/admin/v1/agents",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        fleet_matches = [a for a in fleet if a.get("hostname") == hostname]
        assert len(fleet_matches) == 1, (
            f"reinstall created a duplicate fleet entry for {hostname}: {fleet_matches}"
        )
        assert fleet_matches[0]["id"] == first_agent_id, "reinstall registered a different agent id for the same hostname"
        print(f"    confirmed idempotent: still 1 entry, same agent id ({first_agent_id})")
    finally:
        stop(proc)

    print("\nE2E SMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nE2E SMOKE TEST FAILED: {e}", file=sys.stderr)
        sys.exit(1)
