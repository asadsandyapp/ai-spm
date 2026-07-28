# AI-SPM — Jira Sprint Backlog

**Duration:** 8 weeks · 4 × 2-week sprints · **1 Aug – 25 Sep**  
**Architecture:** Multi-tenant SaaS + endpoint agent + gateway (no browser extension)

Use **#** for Jira sort order. Use **Key** in issue description for traceability.

---

## Sprint 1 — Tenant Onboarding Foundation  
**1 Aug – 14 Aug** · Labels: `SAAS`, `ONBOARDING` · **12 items**

| # | Key | Jira title |
|---|-----|------------|
| 1 | SPM-3 | Security gateway backend foundation |
| 2 | SPM-5 | Public gateway routing and rate limits (Kong) |
| 3 | SPM-25 | Local staging environment (Docker Compose) |
| 4 | SPM-SaaS-1 | Multi-company data isolation (tenant boundaries) |
| 5 | SPM-6 | Admin login and secure session (JWT) |
| 6 | SPM-SaaS-2 | Company registration backend (create org + admin user) |
| 7 | SPM-SaaS-7 | Company signup page (org name, admin email, password) |
| 8 | SPM-SaaS-8 | Email verification + first-login welcome onboarding |
| 9 | SPM-SaaS-3 | Vendor console: list / suspend / activate customer companies |
| 10 | SPM-19a | Organisation policy rules (first version) |
| 11 | SPM-16a | First prompt inspection + audit log entry |
| 12 | SPM-SaaS-4 | Endpoint agent onboarding (register, heartbeat, inspect prompt) |

---

## Sprint 2 — Data Protection & Linux Agent  
**15 Aug – 28 Aug** · Labels: `DATA MASKING`, `ENDPOINT AGENT`, `SAAS` · **13 items**

| # | Key | Jira title |
|---|-----|------------|
| 1 | SPM-13 | PII detection engine (emails, cards, IDs, names, …) |
| 2 | SPM-14 | Regional ID formats (CNIC, IBAN, SSN, phone, …) |
| 3 | SPM-15 | Smart masking + custom company secret patterns |
| 4 | SPM-16b | Inspect AI requests and responses (masked audit only) |
| 5 | SPM-MASK-1 | Admin: choose which PII types to mask |
| 7 | SPM-AGT-L1 | Linux agent: protect AI API traffic (transparent MITM) |
| 8 | SPM-AGT-L2 | Linux agent: protect ChatGPT / Claude / Gemini web UIs |
| 9 | SPM-AGT-L3 | One-click Linux install (systemd, CA trust, network rules) |
| 10 | SPM-AGT-L4 | Agent reinstall without duplicate fleet entries |
| 11 | SPM-AGT-L5 | Web UI activity audit (mitmproxy → agent → dashboard) |
| 12 | SPM-SaaS-9 | Pricing & plans page (Free / Pro / Enterprise) |
| 13 | SPM-SaaS-10 | Plan limits (max agents, prompt quotas) |



---

## Sprint 3 — Admin Console, Deploy & Tenant Settings  
**29 Aug – 11 Sep** · Labels: `ADMIN DASHBOARD`, `AGENT UX`, `SAAS` · **15 items**

| # | Key | Jira title |
|---|-----|------------|
| 1 | SPM-20 | Visual policy builder (no code) |
| 2 | SPM-POL-1 | Role packs for HR, Finance, Developers |
| 3 | SPM-21 | Dashboard: audit log + security metrics |
| 4 | SPM-DASH-1 | Agent fleet: online / offline / revoke |
| 5 | SPM-SaaS-5 | Org install token: view, rotate, copy |
| 6 | SPM-SaaS-11 | Company settings (profile, departments) |
| 7 | SPM-SaaS-12 | Billing & usage page (current plan, quota s) |
| 8 | SPM-SaaS-13 | Vendor platform UI (tenants, usage, suspend) |
| 9 | SPM-UX-1 | Deploy agent wizard (pick OS, verify online) |
| 10 | SPM-UX-2 | Download agent page (Linux package + steps) |
| 11 | SPM-UX-3 | Install binds to company token (audit attribution) |
| 12 | SPM-UX-4 | Agent tray: Protected / Disconnected / Blocked |
| 13 | SPM-UX-5 | Tray: last decision, open dashboard, alerts |
| 14 | SPM-7b | Add Claude and Gemini as AI providers |
| 15 | SPM-23a | End-to-end smoke test (signup → dashboard) |


## Sprint 4 — Windows/macOS Agents, Payments & Threat Protection  
**12 Sep – 25 Sep** · Labels: `WINDOWS`, `MACOS`, `THREAT SHIELDING`, `SAAS` · **13 items**

| # | Key | Jira title |
|---|-----|------------|
| 1 | SPM-WIN-1 | Windows agent Windows Service |
| 2 | SPM-WIN-2 | Windows MSI silent install (GPO / Intune) |
| 3 | SPM-WIN-3 | Windows certificate trust + traffic interception |
| 4 | SPM-WIN-4 | Windows web UI protection (system proxy path) |
| 5 | SPM-WIN-5 | Windows signed installer + tray app |
| 6 | SPM-MAC-1 | macOS background agent |
| 7 | SPM-MAC-2 | macOS pkg / MDM installer + CA trust |
| 8 | SPM-MAC-3 | macOS web UI protection (system proxy path) |
| 9 | SPM-24 | Block jailbreak and prompt-injection attacks |
| 10 | SPM-THR-1 | Threat detection test suite |
| 11 | SPM-SaaS-14 | Paid plans: Stripe checkout + subscription webhooks |
| 12 | SPM-SaaS-15 | Contact sales / Enterprise request form |
| 13 | SPM-SaaS-16 | Password reset and account recovery |


---

## After Sprint 4 (separate phase) · **9 items**

| # | Key | Jira title |
|---|-----|------------|
| 1 | SPM-8b | CI coverage gate + full-stack smoke |
| 2 | SPM-26 | Load and performance testing |
| 3 | SPM-27 | Security pen-test (cross-tenant isolation) |
| 4 | SPM-DOC-1 | Operator runbook + admin guide |
| 5 | SPM-LIVE-1 | Production secrets and gateway hardening |
| 6 | SPM-LIVE-2 | UAT go/no-go (signup → pay → agent → audit) |
| 7 | SPM-AGT-L-upd | Fleet auto-update for agents |
| 8 | SPM-SaaS-17 | Trial expiry and payment reminder emails |
| 9 | SPM-SaaS-18 | GDPR self-serve export / delete |

---

## Jira sprint setup (copy)

| Sprint | Dates | Items | Name |
|--------|-------|------:|------|
| Sprint 1 | 1 Aug – 14 Aug | 12 | Tenant Onboarding Foundation |
| Sprint 2 | 15 Aug – 28 Aug | 13 | Data Protection & Linux Agent |
| Sprint 3 | 29 Aug – 11 Sep | 15 | Admin Console, Deploy & Tenant Settings |
| Sprint 4 | 12 Sep – 25 Sep | 13 | Windows/macOS Agents, Payments & Threat Protection |
| After | Post 25 Sep | 9 | Test, Harden & Launch |

**Labels:** `SAAS`, `ONBOARDING`, `DATA MASKING`, `ENDPOINT AGENT`, `ADMIN DASHBOARD`, `AGENT UX`, `WINDOWS`, `MACOS`, `THREAT SHIELDING`

**Out of scope:** Browser extensions, Kafka, Neo4j, formal certifications.
