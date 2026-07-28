# SPM Proxy

Mask emails in AI prompts before they reach the upstream service.

Two modes:

| Mode | Use case |
|------|----------|
| **MITM proxy** (no extension) | Intercept **chatgpt.com in the browser** |
| **Rust reverse proxy** (`POST /proxy`) | Apps/scripts you control |

---

## ChatGPT Web UI (no extension) — MITM proxy

This is what you need for **chatgpt.com in the browser**. The Rust `/proxy` endpoint does **not** see browser traffic.

```
Browser → HTTPS → MITM proxy (decrypt) → mask emails → chatgpt.com
```

### 1. Install mitmproxy (use a venv — Ubuntu blocks system pip)

```bash
cd /home/lenovo/Pictures/SPM
python3 -m venv .venv
.venv/bin/pip install mitmproxy
```

### 2. Start the MITM proxy

```bash
bash scripts/start-mitm.sh
```

Default listen port: `8800` (override with `MITM_PORT=9090`).

### 3. Trust the CA certificate (required)

mitmproxy generates a CA on first run. Without trusting it, HTTPS interception fails.

```bash
bash scripts/trust-ca-linux.sh
```

Restart the browser after this step.

### 4. Point the browser at the proxy

**GNOME (system proxy):**

```bash
bash scripts/set-proxy-linux.sh
```

**Or manually in browser settings:**

- HTTP proxy: `127.0.0.1:8800`
- HTTPS proxy: `127.0.0.1:8800`

### 5. Test

1. Open https://chatgpt.com
2. Send: `my email is test@gmail.com`
3. mitmproxy terminal shows: `Masked 1 email(s) in POST ...`
4. ChatGPT receives `[EMAIL_REDACTED]` instead of the real address

### Disable when done

```bash
bash scripts/unset-proxy-linux.sh
```

### Windows (same idea as your other machine)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install mitmproxy
.\.venv\Scripts\mitmdump -s scripts\chatgpt_mitm.py --listen-port 8800
```

Then: install `~\.mitmproxy\mitmproxy-ca-cert.p12` into **Trusted Root Certification Authorities**, and set Windows proxy to `127.0.0.1:8800` (Settings → Network → Proxy).

---

## Rust reverse proxy (`POST /proxy`)

For API clients you control — **not** chatgpt.com in the browser.

```
Client  →  POST /proxy  →  Mask emails  →  Upstream AI  →  Response
```

## Requirements

- Rust (latest stable)
- An upstream HTTP endpoint that accepts JSON `{"prompt": "..."}`

## Build

```bash
cargo build
```

Release build:

```bash
cargo build --release
```

## Run

Set the upstream URL, then start the proxy:

```bash
export UPSTREAM_URL=http://localhost:8080/chat
cargo run
```

Optional: change the listen address (default `0.0.0.0:3000`):

```bash
export LISTEN_ADDR=0.0.0.0:3000
```

Optional: adjust log level:

```bash
export RUST_LOG=info
```

## Example request

```bash
curl -X POST http://localhost:3000/proxy \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Send the report to john.doe@gmail.com"}'
```

The proxy forwards this to the upstream service:

```json
{
  "prompt": "Send the report to [EMAIL_REDACTED]"
}
```

## Example response

The proxy returns whatever the upstream service responds with (status, headers, and body are passed through unchanged). For example, if the upstream returns:

```json
{
  "reply": "I will send the report shortly."
}
```

the client receives that same response.

## Error responses

| Status | Condition |
|--------|-----------|
| `400`  | Invalid JSON in request body |
| `500`  | Internal proxy error (e.g. failed to read upstream body) |
| `502`  | Upstream service unavailable |

## Project structure

```
src/
  main.rs     — entry point, router, server bootstrap
  config.rs   — environment-based configuration
  models.rs   — request/response types
  masker.rs   — email detection and redaction
  proxy.rs    — POST /proxy handler and upstream forwarding
```

## Extending

Additional maskers (phone numbers, credit cards, etc.) can be added in `masker.rs` and composed in `proxy.rs` without changing the overall architecture.

## Tests

```bash
cargo test
```
