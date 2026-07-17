# AI-SPM — 8-Week Client Delivery Plan (4 × 2-Week Sprints)

> **Start:** 1 August · **End:** 25 September · **Architecture:** [`AGENTS.md`](../AGENTS.md)  
> **For client / Jira:** all items are delivery work for the sprint.  
> **Order:** module + technical dependency flow (foundation → security → agent/extension → UI/OS).  
> **After Sprint 4:** testing, load/fuzz, docs handover, and go/no-go (separate phase — not in these 4 sprints).

---

## Contents

1. [Sprint 1 — Core Gateway, SaaS & Security Base](#sprint-1--core-gateway-saas--security-base)
2. [Sprint 2 — PII Masking, Linux Agent & Browser Extensions](#sprint-2--pii-masking-linux-agent--browser-extensions)
3. [Sprint 3 — Admin Dashboard, Policy UX & Agent Deploy UX](#sprint-3--admin-dashboard-policy-ux--agent-deploy-ux)
4. [Sprint 4 — Windows/macOS Installers & Threat Shielding](#sprint-4--windowsmacos-installers--threat-shielding)
5. [After Sprint 4 — Test, Harden & Launch](#after-sprint-4--test-harden--launch-separate-phase)
6. [Out of scope](#out-of-scope-later-backlog)
7. [Module flow](#module-flow)
8. [Jira sprint setup](#jira-sprint-setup-copy)
9. [Full task inventory (all keys)](#full-task-inventory-all-keys)

---

## Sprint 1 — Core Gateway, SaaS & Security Base

**1 Aug – 14 Aug** · **2 weeks** · **13 work items** · Labels: `CORE GATEWAY` · `SAAS`  
**Status: IMPLEMENTED** (enterprise base per [`AGENTS.md`](../AGENTS.md))

| Key | Task | Status |
|-----|------|--------|
| SPM-3 | Scaffold Base FastAPI Application and Core Middleware | Done |
| SPM-5 | Configure Kong API Edge (routing, rate limit, correlation) | Done |
| SPM-6 | Implement Gateway Security, JWT Resolution, and Rate Limiting | Done |
| SPM-SaaS-1 | Multi-tenant schema, RLS, and TenantContext middleware | Done |
| SPM-SaaS-2 | Public signup, email verification flow, and org provisioning | Done |
| SPM-SaaS-3 | Platform admin API (tenants list / suspend / activate / usage) | Done |
| SPM-SaaS-4 | Agent APIs: register, heartbeat, prompt (`inspect_only`) | Done |
| SPM-7a | OpenAI-compatible LLM adapter (first provider) | Done |
| SPM-19a | Policy evaluation engine (models / topics / providers) + Redis cache | Done |
| SPM-16a | Prompt pipeline skeleton (policy → threat → PII → audit) | Done |
| SPM-8 | Establish Automated CI Validation Pipeline | Done |
| SPM-25 | Multi-Service Docker Compose (Postgres, Redis, API, Kong) | Done |
| SPM-ARCH-1 | Freeze architecture doc: agent + extension + gateway (AGENTS.md) | Done |

**Sprint 1 exit (demo):** signup → admin login → agent registers → sample prompt audited; Tenant A isolated from Tenant B.

```bash
make up && make migrate && make seed   # or Compose seeds on api start
make demo-sprint1                      # BASE defaults to http://localhost:8090
make test-security                     # cross-tenant isolation gate
```

Dev shortcuts: `make seed` prints `admin@devcorp.io` + `AISPM_ORG_TOKEN`. Non-production signup returns `verification_token`; verify returns `org_token` once.

---

## Sprint 2 — PII Masking, Linux Agent & Browser Extensions

**15 Aug – 28 Aug** · **2 weeks** · **13 work items** · Labels: `DATA MASKING` · `ENDPOINT AGENT` · `BROWSER EXTENSION`

| Key | Task |
|-----|------|
| SPM-13 | Integrate NLP PII Detection Engine (Presidio + spaCy / regex fallback) |
| SPM-14 | Regionalized recognizers (CNIC, IBAN, bank account, email, phone, card, SSN) |
| SPM-15 | Token-preserving masking + custom company-secrets rules |
| SPM-16b | Bidirectional pipeline (request + response PII/threat scan, masked audit only) |
| SPM-MASK-1 | Masking configuration (entity types / confidence) — API + basic admin UI |
| SPM-AGT-L1 | Linux agent: transparent MITM for API hosts + CF passthrough list |
| SPM-AGT-L2 | Linux agent: local_api `:8092` (inspect + CRX/updates.xml) |
| SPM-AGT-L3 | Linux install: systemd, CA trust, iptables/QUIC block (`install-agent.sh`) |
| SPM-AGT-L4 | Idempotent agent register by hostname + retry/heartbeat re-register |
| SPM-EXT-1 | Chrome/Edge managed extension (forcelist + external_crx + updates.xml) |
| SPM-EXT-2 | Firefox managed extension (policies + AMO-signed XPI staging) |
| SPM-EXT-3 | Extension content hooks for ChatGPT / Claude / Gemini web UIs |
| SPM-18 | PII accuracy spot-check report (labelled sample set) |

**Sprint 2 exit (demo):** install Linux agent → open ChatGPT/Claude/Gemini → PII masked → audit shows masked event; API host MITM works.

---

## Sprint 3 — Admin Dashboard, Policy UX & Agent Deploy UX

**29 Aug – 11 Sep** · **2 weeks** · **15 work items** · Labels: `ADMIN DASHBOARD` · `AGENT UX` · `SAAS`

| Key | Task |
|-----|------|
| SPM-21 | Audit log viewer + analytical / metrics dashboards |
| SPM-DASH-1 | Agent fleet panel (online / offline / revoke / delete) |
| SPM-20 | Frontend workspace & visual policy rule builder |
| SPM-POL-1 | Default role packs (HR / Finance / Developers) + RBAC gates in UI |
| SPM-POL-2 | File-upload / topic restriction rules in policy engine + UI |
| SPM-DASH-2 | User management UI (invite, roles, suspend) |
| SPM-22 | Real-time violation alerts (WebSocket + email/Slack hooks) |
| SPM-SaaS-5 | Org token management UI (view / rotate / copy for install) |
| SPM-UX-1 | Admin “Deploy agent” wizard (OS picker + token + verify agent online) |
| SPM-UX-2 | Download / install portal page (Linux package + install commands) |
| SPM-UX-3 | Token-based install identity (org token bind + audit attribution) |
| SPM-UX-4 | Agent tray UI — Protected / Disconnected / Blocked (Linux first) |
| SPM-UX-5 | Tray: last decision, open dashboard, reconnect / block notification |
| SPM-7b | Multi-provider adapters: Anthropic + Gemini (Bedrock stub OK) |
| SPM-23a | Frontend component tests + critical path Playwright smoke |

**Sprint 3 exit (demo):** admin builds policy visually → deploy wizard issues token → agent online in fleet → live threat/audit feed; tray shows Protected.

---

## Sprint 4 — Windows/macOS Installers & Threat Shielding

**12 Sep – 25 Sep** · **2 weeks** · **11 work items** · Labels: `WINDOWS` · `MACOS` · `THREAT SHIELDING`

| Key | Task |
|-----|------|
| SPM-WIN-1 | Windows Service packaging (SCM) |
| SPM-WIN-2 | WiX MSI silent install (GPO / Intune ready) |
| SPM-WIN-3 | Windows MITM CA trust + interception mode (WFP or documented proxy) |
| SPM-WIN-4 | Windows extension policy reconcile (Chrome/Edge/Firefox) |
| SPM-WIN-5 | Authenticode signing + tray on Windows |
| SPM-MAC-1 | macOS agent daemon + config paths |
| SPM-MAC-2 | macOS pkg / MDM installer + CA trust |
| SPM-MAC-3 | macOS Chrome/Firefox extension reconcile (same CRX/XPI) |
| SPM-24 | Advanced threat shielding (jailbreak/injection score 0–100 + threshold) |
| SPM-THR-1 | Threat regression suite (signature / Garak sample set) |
| SPM-MAC-4 | *(Stretch)* Safari Web Extension + MDM AlwaysOn — only if Sprint 4 ahead |

**Sprint 4 exit (demo):** Windows MSI + Linux install; macOS agent install path; threat block demo on sample jailbreak/injection.

---

## After Sprint 4 — Test, Harden & Launch (separate phase)

> **Not part of the 8-week / 4-sprint delivery board.** Schedule after 25 Sep.

| Key | Task |
|-----|------|
| SPM-26 | Load / stress tests (gateway P95 target) |
| SPM-27 | Security fuzzing / cross-tenant pen-test pass |
| SPM-8b | CI coverage gate + full-stack Docker smoke on merge |
| SPM-DOC-1 | Operator runbook + admin manual + deploy guide |
| SPM-LIVE-1 | Production secrets checklist (Vault/K8s) + Kong mTLS hardening |
| SPM-LIVE-2 | UAT: Windows/Linux/macOS install → mask web UIs → audit → go/no-go |
| SPM-AGT-L-upd | Full MinIO MSI/pkg auto-update fleet |
| SPM-MAC-Safari | Safari extension full enterprise MDM (if not done as Sprint 4 stretch) |

---

## Out of scope (later backlog)

| Key | Task | Why deferred |
|-----|------|--------------|
| SPM-Kafka | Kafka / Flink streaming | Not needed at MVP scale |
| SPM-Neo4j | Graph analytics | Audit SQL sufficient |
| SPM-ISO / GDPR-cert | Formal certifications | Legal workstream |

---

## Module flow

```text
Sprint 1  Gateway + SaaS + APIs
    ↓
Sprint 2  Masking + Linux agent + Extensions
    ↓
Sprint 3  Admin UI + Deploy/Token UX + Tray
    ↓
Sprint 4  Windows/macOS + Threat shielding
    ↓
After    Test + docs + UAT + go/no-go
```

---

## Jira sprint setup (copy)

| Sprint | Dates | Work items | Name |
|--------|-------|------------|------|
| Sprint 1 | 1 Aug – 14 Aug | 13 | Core Gateway, SaaS & Security Base |
| Sprint 2 | 15 Aug – 28 Aug | 13 | PII Masking, Linux Agent & Extensions |
| Sprint 3 | 29 Aug – 11 Sep | 15 | Admin Dashboard, Policy & Agent Deploy UX |
| Sprint 4 | 12 Sep – 25 Sep | 11 | Windows/macOS Installers & Threat Shielding |
| (Later) | After 25 Sep | 8 | Test, Harden & Launch |

**Total in 4 sprints:** 52 work items (plus 1 stretch in Sprint 4).

Create labels: `CORE GATEWAY`, `SAAS`, `DATA MASKING`, `ENDPOINT AGENT`, `BROWSER EXTENSION`, `ADMIN DASHBOARD`, `AGENT UX`, `WINDOWS`, `MACOS`, `THREAT SHIELDING`.

---

## Full task inventory (all keys)

### Sprint 1 (13)

`SPM-3`, `SPM-5`, `SPM-6`, `SPM-SaaS-1`, `SPM-SaaS-2`, `SPM-SaaS-3`, `SPM-SaaS-4`, `SPM-7a`, `SPM-19a`, `SPM-16a`, `SPM-8`, `SPM-25`, `SPM-ARCH-1`

### Sprint 2 (13)

`SPM-13`, `SPM-14`, `SPM-15`, `SPM-16b`, `SPM-MASK-1`, `SPM-AGT-L1`, `SPM-AGT-L2`, `SPM-AGT-L3`, `SPM-AGT-L4`, `SPM-EXT-1`, `SPM-EXT-2`, `SPM-EXT-3`, `SPM-18`

### Sprint 3 (15)

`SPM-21`, `SPM-DASH-1`, `SPM-20`, `SPM-POL-1`, `SPM-POL-2`, `SPM-DASH-2`, `SPM-22`, `SPM-SaaS-5`, `SPM-UX-1`, `SPM-UX-2`, `SPM-UX-3`, `SPM-UX-4`, `SPM-UX-5`, `SPM-7b`, `SPM-23a`

### Sprint 4 (11)

`SPM-WIN-1`, `SPM-WIN-2`, `SPM-WIN-3`, `SPM-WIN-4`, `SPM-WIN-5`, `SPM-MAC-1`, `SPM-MAC-2`, `SPM-MAC-3`, `SPM-24`, `SPM-THR-1`, `SPM-MAC-4` (stretch)

### After Sprint 4 (8)

`SPM-26`, `SPM-27`, `SPM-8b`, `SPM-DOC-1`, `SPM-LIVE-1`, `SPM-LIVE-2`, `SPM-AGT-L-upd`, `SPM-MAC-Safari`

---

*Client-facing plan. Testing and launch are a follow-on phase after the four delivery sprints.*
