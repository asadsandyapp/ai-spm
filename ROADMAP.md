# AI-SPM DLP Agent — SaaS Roadmap

Plan for evolving the DLP agent from a local endpoint tool into a commercial SaaS product.

**Model:** the agent stays on the endpoint (TLS interception, WebSocket DLP, and `[MASKED-X-NNN]` masking must happen on-device); the cloud side is a control plane — tenancy, policy management, event ingestion, dashboards, and billing. This is the same shape used by Netskope, Nightfall, and Prompt Security.

**Core differentiator (hold this line at every phase):** sensitive data never leaves the endpoint unmasked.

---

## Phase 0 — Finish and prove the core (now → ~1 month)

The agent is the product's moat; it must be trustworthy before anything is built on top.

- [x] **Real-traffic validation (ChatGPT)** — confirmed against real `chatgpt.com` traffic in both Firefox (anonymous web session, `/backend-anon/f/conversation`) and the ChatGPT Windows desktop app (`/backend-api/f/conversation`): interception, TLS/CA trust, and masking all hold on real typed messages. Also found and fixed a real bug this pass — real `wss://ws.chatgpt.com` negotiates permessage-deflate, which broke WS DLP outright until `Sec-WebSocket-Extensions` started getting stripped on upgrade. **Still open:** Claude.ai and Gemini have only had proxy-routing/CA-trust confirmed (clean CONNECT tunnels, no TLS errors), not an actual masked-message pass — don't claim those as fully validated yet.
- [x] **Stability hardening (partial)**
  - [ ] Proper `agentd stop` that restores proxy/PAC settings (a service `stop`/`uninstall` still leaves each user's `enable-proxy` HKCU state untouched - each user runs `disable-proxy` themselves; see README's Packaging section)
  - [x] Crash recovery that never leaves the machine with a broken proxy — `agentd` now runs as a real Windows Service (`AiSpmDlpAgent`, via `agentctl install --full`/the `.msi`) with SCM-native recovery actions. Verified for real: killing `agentd.exe` outright, SCM spawned a replacement process exactly 30s later per the configured recovery schedule, auto-start survives reboot (before any interactive logon), and `agentctl install --full` / `uninstall` were verified end-to-end via a real `msiexec /i` / `msiexec /x` cycle (service registration, Local Machine CA trust, Firefox trust, and clean removal all confirmed).
  - [ ] Fail-open behavior — a dead agent must never cut the user's internet (already true by design - the PAC fails open to `DIRECT` when `agentd` isn't serving it - but not re-verified as part of this pass; still worth an explicit test)
- [ ] **Config externalization** — move the 9 detection rules out of the binary into a signed local policy file. This is the seam the cloud will later push policies through; getting the format right now avoids a migration.

**Exit criteria:** a colleague can run it for a week without noticing it, and every masking event is correct against real AI-site traffic.

---

## Coverage — browsers & desktop applications

Interception is opt-in per client: a given app is only protected if it (a) routes through the PAC/proxy setting and (b) trusts the local CA. "Works in Chrome" is not the same as "covers all AI touchpoints on the endpoint" — today only Chrome/Edge-in-browser is actually verified against real traffic. This section tracks closing that gap in stages, from cheapest to most architectural.

### Now — folds into Phase 0's exit criteria

- [x] **Firefox CA trust automation** — `agentctl install-ca` now locates local Firefox installs (`%LOCALAPPDATA%\Mozilla Firefox`, both `Program Files` paths) and writes/merges `distribution\policies.json` with `Certificates.ImportEnterpriseRoots: true`, so Firefox trusts the same Root/CA stores Windows does (`crates/agent-ca/src/firefox.rs`, unit-tested). Per-user install needs no admin; machine-wide installs need `install-ca` run elevated (matches the "Machine-wide option" pattern below). **Real-browser validation done:** a machine-wide Firefox install (`Program Files`) required the elevated re-run, then produced clean `intercepting target domain` CONNECT tunnels for `claude.ai` (no TLS errors) and a real masked message on `chatgpt.com` — both PAC pickup and CA trust are confirmed working in Firefox, not just assumed.
- [x] **Verify desktop apps empirically, don't assume** — the ChatGPT Windows desktop app (ships as an MSIX package, `OpenAI.Codex`/`ChatGPT.exe`, Electron-based) is now confirmed via `Get-NetTCPConnection` (established connection to the proxy port) and the agentd log (`intercepting target domain` + a real `dlp match` on its `/backend-api/f/conversation` endpoint). **Still open:** this is one desktop app; Claude desktop and any other target desktop clients remain unverified.
- [x] **Machine-wide CA install** — `agentctl install --full` (and the `.msi`) now installs the CA into `Local Machine\Trusted Root` (elevated), covering every account on the box; verified via a real `msiexec /i`/`agentctl install --full` run followed by inspecting `Cert:\LocalMachine\Root`. **Still open:** the *proxy auto-config* half of "machine-wide" - `netsh winhttp set proxy` (or equivalent) for other user sessions and anything running as `SYSTEM`/a service - is unchanged; `agentctl enable-proxy` remains per-user `HKCU` only. Document as a deployment *choice* once built, not a silent upgrade to the default.
- [ ] **Coverage test matrix** — explicit list of every client in scope (Chrome, Edge, Firefox, Brave/Opera if applicable, ChatGPT desktop, Claude desktop, target IDE AI plugins), each run through the same real-traffic validation methodology used for ChatGPT-in-browser. Chrome/Edge, Firefox, and the ChatGPT desktop app are now validated against real ChatGPT traffic; Claude desktop, other browsers, and Claude.ai/Gemini masked-message passes are still open. Anything not on the list is assumed *unprotected*, not assumed covered.

### Phase 2 — alongside the macOS agent (same "broaden endpoint coverage" theme)

- [ ] **Env-var proxy injection** (`HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`) for CLI tools and SDKs that check environment variables instead of the OS proxy setting. Partial win only — helps tools already written to respect these vars, and requires a fresh process (sometimes a logoff) to pick up the change.
- [ ] **Per-runtime CA bundle injection** for known tools that bundle their own trust store and ignore the OS entirely (`REQUESTS_CA_BUNDLE` for Python/`certifi`, `NODE_EXTRA_CA_CERTS` for Node). Targeted, not general — only covers an explicit "supported tools" list and breaks silently on tool updates or anything not on that list.

### Future / big bet — network-level interception

- [ ] **Evaluate a WFP callout driver (or equivalent)** to intercept target-domain traffic at the network stack regardless of whether the sending process honors WinINet/system proxy settings. This is how CASB competitors (Netskope, Zscaler) guarantee coverage without depending on every current and future AI client cooperating. Large lift — kernel driver, SNI-based routing, driver code signing/distribution — treat as its own milestone, not a bullet inside Phase 0–3.
- [ ] **Decide the policy for certificate-pinned apps** — no proxy-based approach (PAC, WinHTTP, or the WFP driver above) can MITM an app that pins its TLS certs; it will break the connection outright rather than bypass silently. Options: detect-and-alert on pinning failures without reading content, or cover those specific apps with a different control (clipboard/keyboard-level DLP) instead of TLS interception. Make this decision explicitly rather than leaving it implicit.

---

## Phase 1 — Single-tenant "cloud-managed agent" (months 1–3)

Build the smallest possible cloud side, used only by BlockApt internally. Developed **compose-first**: the entire control plane runs locally in Docker, and the same images later deploy to real cloud infrastructure — nothing is throwaway.

- [ ] **Docker-based local dev stack** — `docker compose up` brings up the full "cloud" on a laptop:
  - [ ] Control-plane API container (enrollment, policy sync, event ingestion) on `localhost:9000`
  - [ ] Postgres container (device registry, policies, events)
  - [ ] Dashboard container (web UI)
  - [ ] Host-side `agentd` points at `http://localhost:9000` as its control-plane URL (the agent itself stays on the host — it must set PAC, install the CA, and intercept host traffic; ensure loopback bypasses the PAC so the agent never intercepts its own control-plane traffic)
  - [ ] Later additions as needed: MinIO for agent update artifacts, message queue if event volume grows
- [ ] **Control-plane API** — small backend with tenant/device registry, policy store, and event ingestion. Agent enrolls with a token, pulls policy on a schedule, reports detection events (metadata only — rule hit, site, timestamp, masked-token ID; never raw content).
- [ ] **Agent "phone home" module** — enrollment, policy sync, heartbeat, event upload with offline buffering.
- [ ] **Basic dashboard** — event feed, per-device status, policy editor for the rule set.
- [ ] **Auto-update channel** — signed agent updates; a fleet cannot run on manual installs.

**Exit criteria:** BlockApt's own machines run the agent managed entirely from the dashboard — the dogfooding deployment and first demo.

---

## Phase 2 — Multi-tenant SaaS MVP (months 3–6)

Turn the internal tool into something a design-partner customer can use.

- [ ] **Multi-tenancy** — org isolation in the data model, per-tenant policies and API keys, admin/viewer roles. Test isolation early using the Docker dev stack: two fake orgs with two enrolled agents to catch data-model mistakes before real customers.
- [ ] **Onboarding flow** — self-serve org creation, agent installer download with embedded enrollment token, deployment guide (MSI/Intune for fleets).
- [ ] **Alerting** — email/Slack/webhook on policy violations; this is what security teams actually buy.
- [ ] **macOS agent** — start the port; realistic pilots have mixed fleets and this is the longest-lead item, so it starts here even though it lands later.
- [ ] **Design partners** — 2–3 friendly companies running free pilots in exchange for feedback. Their asks define Phase 3 priorities.

**Exit criteria:** an outside org can sign up, deploy to 20+ endpoints, and manage policy without hands-on help.

---

## Phase 3 — Enterprise readiness (months 6–12)

What converts pilots into paid contracts.

- [ ] **SSO/SAML + SCIM** — non-negotiable for enterprise security buyers.
- [ ] **Audit trail & reporting** — exportable compliance reports, SIEM integration (syslog/Splunk connector).
- [ ] **SOC 2 Type I** — start early; the audit takes months and the control plane must be designed for it (least privilege, logging, encryption at rest).
- [ ] **Billing** — per-endpoint/per-seat pricing; Stripe or invoicing for enterprise.
- [ ] **Policy depth** — per-group policies, allow/block/mask actions per rule, custom regex/ML rules per tenant.

---

## Ongoing principles

1. **Data never leaves the endpoint unmasked** — the architectural line that differentiates this from cloud-proxy competitors (Netskope, Zscaler).
2. **Validate against real traffic at every phase** — every new AI site or protocol change (e.g. ChatGPT WS format shifts) gets a real-browser regression pass, not just synthetic tests.
3. **The agent stays thin** — enforcement only; all intelligence, policy logic, and reporting lives in the cloud where iteration doesn't require redeploying binaries.
4. **Coverage is per-client, not assumed** — a browser/app is only "covered" once it's been run through the [coverage test matrix](#coverage--browsers--desktop-applications) against real traffic; anything untested is treated as unprotected in customer-facing claims.

## Critical path

Phase 0 gates everything: all later phases build on an agent proven against real traffic. The first design artifact worth speccing in Phase 1 is the agent↔cloud protocol (enrollment, policy sync, event schema). The [browser & desktop app coverage matrix](#coverage--browsers--desktop-applications) should be filled in before any customer-facing coverage claim is made.
