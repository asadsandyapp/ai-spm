#!/usr/bin/env python3
"""End-to-end smoke test for a built agentd binary.

Starts agentd against the given config, sends real HTTP traffic through its
proxy port, and checks that the block/mask/pass-through behavior documented
in README.md's Testing section actually holds - the same check that's been
run by hand before every release (see logs/elevated-verify.out), now
automated so CI catches a regression in the actual proxy path instead of
only the unit tests.

With --no-launch, doesn't spawn agentd itself - just runs the same checks
against whatever is already listening on --proxy-port. That's the mode the
installer smoke test jobs use: after installing the real .msi/.deb, the
service is already running under its own installed config, so there's
nothing to launch and no config path to know about.
"""
import argparse
import http.client
import http.server
import os
import socket
import subprocess
import sys
import threading
import time

MOCK_HOST = "127.0.0.1"
MOCK_PORT = 9000


class RecordingHandler(http.server.BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        RecordingHandler.received.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # keep CI output focused on this script's own assertions


def wait_for_port(host, port, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.3)
    raise TimeoutError(f"nothing listening on {host}:{port} after {timeout}s")


def proxy_post(proxy_host, proxy_port, path, body: bytes):
    conn = http.client.HTTPConnection(proxy_host, proxy_port, timeout=10)
    try:
        conn.request(
            "POST",
            f"http://{MOCK_HOST}:{MOCK_PORT}{path}",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agentd", help="path to the agentd binary (omit with --no-launch)")
    parser.add_argument("--config", help="path to config.toml (omit with --no-launch)")
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="don't spawn agentd - assume it's already running (e.g. as an installed service)",
    )
    parser.add_argument("--proxy-host", default="127.0.0.1")
    parser.add_argument("--proxy-port", type=int, default=8443)
    args = parser.parse_args()

    if not args.no_launch and (not args.agentd or not args.config):
        parser.error("--agentd and --config are required unless --no-launch is set")

    server = http.server.HTTPServer((MOCK_HOST, MOCK_PORT), RecordingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    agentd = None
    if not args.no_launch:
        # Relative paths passed straight to CreateProcess don't reliably
        # resolve on Windows (observed: os.path.exists() finds it,
        # subprocess.Popen() doesn't) - absolute paths sidestep that.
        agentd = subprocess.Popen(
            [os.path.abspath(args.agentd), "--config", os.path.abspath(args.config)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    failures = []
    try:
        wait_for_port(args.proxy_host, args.proxy_port)

        # 1. A hardcoded secret (AWS key) must be blocked outright - the
        #    mock server must never see it.
        status = proxy_post(
            args.proxy_host, args.proxy_port, "/blocked",
            b'{"messages":[{"role":"user","content":"key AKIAABCDEFGHIJKLMNOP"}]}',
        )
        if status != 403:
            failures.append(f"block case: expected HTTP 403, got {status}")
        if any(b"AKIAABCDEFGHIJKLMNOP" in r for r in RecordingHandler.received):
            failures.append("block case: secret reached the upstream mock server")

        # 2. A masked-category value (email) must pass through rewritten -
        #    the raw value must never reach the upstream.
        before = len(RecordingHandler.received)
        status = proxy_post(
            args.proxy_host, args.proxy_port, "/masked",
            b'{"messages":[{"role":"user","content":"contact me at test@example.com"}]}',
        )
        if status != 200:
            failures.append(f"mask case: expected HTTP 200, got {status}")
        if len(RecordingHandler.received) != before + 1:
            failures.append("mask case: mock server did not receive the forwarded (masked) request")
        else:
            forwarded = RecordingHandler.received[-1]
            if b"test@example.com" in forwarded:
                failures.append("mask case: raw email reached the upstream mock server unmasked")
            if b"MASKED-EMAIL" not in forwarded:
                failures.append("mask case: forwarded body doesn't contain the expected mask token")

        # 3b. An RSA-format private key (not the PKCS#8 header the
        #     private_key_block rule originally matched exclusively) must
        #     also be blocked outright.
        status = proxy_post(
            args.proxy_host, args.proxy_port, "/blocked-rsa-key",
            b'{"messages":[{"role":"user","content":"-----BEGIN RSA PRIVATE KEY-----\\nMIIBOgIBAAJBAK...\\n-----END RSA PRIVATE KEY-----"}]}',
        )
        if status != 403:
            failures.append(f"RSA private key block case: expected HTTP 403, got {status}")
        if any(b"BEGIN RSA PRIVATE KEY" in r for r in RecordingHandler.received):
            failures.append("RSA private key block case: key material reached the upstream mock server")

        # 3. Clean content must pass through untouched.
        before = len(RecordingHandler.received)
        status = proxy_post(
            args.proxy_host, args.proxy_port, "/clean",
            b'{"messages":[{"role":"user","content":"hello, how are you?"}]}',
        )
        if status != 200:
            failures.append(f"clean case: expected HTTP 200, got {status}")
        if len(RecordingHandler.received) != before + 1 or b"hello, how are you?" not in RecordingHandler.received[-1]:
            failures.append("clean case: mock server did not receive the unmodified request")

    finally:
        if agentd is not None:
            agentd.terminate()
            try:
                agentd.wait(timeout=10)
            except subprocess.TimeoutExpired:
                agentd.kill()
            output = agentd.stdout.read() if agentd.stdout else ""
            if failures and output:
                print("--- agentd output ---")
                print(output)

    if failures:
        print("SMOKE TEST FAILED:")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)

    print(
        f"Smoke test passed: block, mask, and pass-through all verified end-to-end "
        f"through the real proxy ({len(RecordingHandler.received)} requests reached the mock server)."
    )


if __name__ == "__main__":
    main()
