# AI-SPM — Feature-Wise Sprint
---

## Sprint 1 — Company Onboarding & First Connected Device
**1 Aug – 14 Aug** · Labels: `SAAS`, `ONBOARDING`, `SUPER ADMIN`, `ENDPOINT AGENT`

| # | Key | Jira title | Description | Needs first |
|---|-----|------------|-------------|-------------|
| 1 | SPM-3 | Security service foundation (company data model, health checks) | Set up the central service that stores companies, users, devices and activity, with health checks so the team can confirm it is running. | — |
| 2 | SPM-SaaS-2 | Create company workspace, first admin user and install token | When a company joins, automatically create its private workspace, its first admin account and the install token used to connect devices. | SPM-3 |
| 3 | SPM-6 | Company admin login and secure session | A company admin can sign in with email and password, stay signed in securely, and sign out. | SPM-SaaS-2 |
| 4 | SPM-SaaS-7 | Company self-registration page (company name, admin email, password) | A new customer registers without contacting sales by entering their company name, admin email and password. | SPM-6 |
| 5 | SPM-SaaS-8 | Email verification and first-login welcome onboarding | The admin confirms their email address, then sees a short welcome guide explaining the first steps to protect their company. | SPM-SaaS-7 |
| 6 | SPM-5 | Public entry point with safe routing and request limits | Put all customer traffic behind a single protected entry point that limits abusive request volumes. | SPM-3 |
| 7 | SPM-SaaS-3 | Super Admin: list, suspend and reactivate customer companies | The Super Admin sees every customer company and can suspend or reactivate an account, for example for non-payment. | SPM-SaaS-2 |
| 8 | SPM-19a | Company's first AI protection policy (allow / mask / block) | The company admin chooses what happens when sensitive information is found in an AI prompt: allow it, mask it or block it. | SPM-6 |
| 9 | SPM-AGT-1 | Agent application skeleton that runs on a Linux machine | Build the endpoint application that runs on an employee computer, reads its configuration and stays running in the background. | — |
| 10 | SPM-AGT-2 | Device enrolment service: a device joins a company using its install token | The service accepts a device's install token, confirms which company it belongs to and issues its identity. | SPM-SaaS-2 |
| 11 | SPM-AGT-3 | Agent registers itself with the company install token | On first start the agent enrols itself with the company install token so it appears in that company's device list. | SPM-AGT-2 |
| 12 | SPM-AGT-4 | Agent reports it is alive so the company sees Online / Offline | The agent checks in regularly, and a device that stops checking in is shown as Offline in the console. | SPM-AGT-3 |
| 13 | SPM-AGT-5 | Agent sends a captured AI prompt for inspection and applies the decision | The agent sends an AI prompt for inspection and then allows, masks or blocks it according to the company policy. | SPM-19a |
| 14 | SPM-SaaS-4 | A registered company connects its first device end to end | Full journey check: a company registers, installs the agent on one machine and sees that device appear as Online. | SPM-AGT-4 |
| 15 | SPM-16a | First protected AI activity appears in the company audit log | After an employee sends an AI prompt, the company admin sees a record of it with sensitive values hidden. | SPM-AGT-5 |

**Sprint outcome:** A company signs up, verifies its email, logs in, sets one policy, installs the
agent on one Linux machine, sees that device as Online, and sees its first inspected AI prompt.

---

## Sprint 2 — Sensitive Data Protection & Full Linux Coverage
**15 Aug – 28 Aug** · Labels: `DATA MASKING`, `ENDPOINT AGENT`, `SAAS`

| # | Key | Jira title | Description | Needs first |
|---|-----|------------|-------------|-------------|
| 1 | SPM-13 | Detect common sensitive data (emails, names, cards, passwords, addresses) | Recognise everyday personal and company information inside AI prompts so it can be protected. | SPM-16a |
| 2 | SPM-14 | Detect IDs (CNIC, SSN, IBAN, phone, passport) | Recognise national and financial identity numbers used by customers in different countries. | SPM-13 |
| 3 | SPM-16b | Mask sensitive data in AI requests and responses, store masked records only | Replace sensitive values before the prompt reaches the AI provider, and keep only the masked version in company records. | SPM-14 |
| 4 | SPM-MASK-1 | Company admin chooses which sensitive data types to protect | The admin turns individual data categories on or off to match the company's own privacy rules. | SPM-16b |
| 5 | SPM-SaaS-9 | Subscription plans page (Free / Pro / Enterprise) | Show the available plans with what each one includes so a customer can pick the right one. | SPM-SaaS-7 |
| 6 | SPM-SaaS-10 | Apply plan limits (maximum devices, monthly prompt quota) | Enforce the device count and monthly usage allowed by the company's plan. | SPM-SaaS-9 |
| 7 | SPM-AGT-L0 | Install the company security certificate so traffic can be inspected safely | Install and trust the security certificate on the employee machine so protected traffic can be checked without breaking the browser. | SPM-AGT-3 |
| 8 | SPM-AGT-L1 | Linux: protect AI apps, developer tools and API traffic | Protect AI usage coming from installed applications, developer tools and scripts on Linux machines. | SPM-AGT-L0 |
| 9 | SPM-AGT-L2 | Linux: protect ChatGPT / Claude / Gemini websites | Protect what employees type into the ChatGPT, Claude and Gemini websites in their browser. | SPM-AGT-L1 |
| 10 | SPM-AGT-L5 | Send protected AI website activity to the company console | Website AI activity is reported to the company console so admins see it alongside application activity. | SPM-AGT-L2 |
| 11 | SPM-AGT-L3 | Linux: one-command install that starts protection automatically | IT installs the agent with a single command, and protection starts automatically and restarts with the machine. | SPM-AGT-L2 |
| 12 | SPM-AGT-L4 | Linux: reinstall without duplicate devices or wasted licences | Reinstalling on the same machine updates the existing device instead of creating a duplicate and consuming another licence. | SPM-AGT-L3 |
| 13 | SPM-INT-2 | Sensitive data typed into ChatGPT on Linux is masked before it leaves the machine | End-to-end check that real sensitive information typed into an AI website never reaches the provider. | SPM-16b, SPM-AGT-L2 |
| 14 | SPM-INT-3 | A company that reaches its device limit cannot enrol more machines | End-to-end check that plan limits are enforced when IT tries to install beyond the purchased device count. | SPM-SaaS-10, SPM-AGT-L4 |

**Sprint outcome:** A company decides what sensitive data to protect, installs the agent on Linux
machines with one command, and employee AI website and AI application activity is masked.

---

## Sprint 3 — Company Console & Deployment Experience
**29 Aug – 11 Sep** · Labels: `ADMIN DASHBOARD`, `AGENT UX`, `SAAS`, `SUPER ADMIN`

| # | Key | Jira title | Description | Needs first |
|---|-----|------------|-------------|-------------|
| 1 | SPM-21 | Company security overview (protected prompts, masked data, blocked activity) | A dashboard showing how much AI activity was protected, what was masked, what was blocked and how this changes over time. | SPM-16b |
| 2 | SPM-DASH-1 | Company device fleet: Online / Offline / revoke access | List every company device with its status, and let the admin revoke a machine that should no longer be protected or trusted. | SPM-AGT-4 |
| 3 | SPM-SaaS-5 | Company install credentials: view, copy and rotate | The admin views and copies the install token for new devices, and rotates it if it may have been shared or leaked. | SPM-SaaS-2 |
| 4 | SPM-SaaS-11 | Company settings (profile, preferences, protection configuration) | One place for the admin to manage company details, preferences and protection configuration. | SPM-MASK-1 |
| 5 | SPM-SaaS-12 | Company plan and usage page (plan, quota used, quota remaining) | The admin sees the current plan, how many devices and prompts have been used, and how much allowance is left. | SPM-SaaS-10 |
| 6 | SPM-SaaS-13 | Super Admin customer overview (companies, plans, usage, status, fleet size) | The Super Admin reviews all customers in one view with their plan, usage, account status and number of protected devices. | SPM-SaaS-3, SPM-SaaS-12 |
| 7 | SPM-UX-3 | Every install binds to its company so activity is attributed correctly | A device installed from a company's package reports only into that company, so activity is never attributed to the wrong customer. | SPM-SaaS-5 |
| 8 | SPM-UX-2 | Download agent page with a company-specific Linux package and steps | The admin downloads an installer already tied to their company, with clear installation instructions. | SPM-UX-3 |
| 9 | SPM-UX-1 | Guided deploy wizard: choose the operating system, install, confirm Online | A step-by-step wizard walks the admin through choosing an operating system, installing the agent and confirming the device is protected. | SPM-UX-2, SPM-DASH-1 |
| 10 | SPM-UX-4 | Device status for employees: Active / Disconnected / Blocked | Employees can see on their own machine whether protection is Active, Disconnected or Blocked. | SPM-AGT-4 |

**Sprint outcome:** Company admins and Super Admin run the service day to day — monitor security,
manage devices, deploy agents and track plan usage — without developer assistance.

---

## Sprint 4 — Windows Protection, Threat Defence & Paid Plans
**12 Sep – 25 Sep** · Labels: `WINDOWS`, `THREAT SHIELDING`, `SAAS`, `BILLING`

| # | Key | Jira title | Description | Needs first |
|---|-----|------------|-------------|-------------|
| 1 | SPM-SaaS-16 | Password reset and account recovery | An admin who forgets their password can securely regain access without contacting support. | SPM-6 |
| 2 | SPM-THR-1 | Detect dangerous AI prompts (jailbreak, prompt injection, policy violations) | Identify prompts that try to bypass AI safety controls or break company rules, and act on them. | SPM-16b |
| 3 | SPM-SaaS-14 | Buy a paid plan: checkout | A customer upgrades from the plans page, pays, and their new plan limits apply automatically. | SPM-SaaS-10 |
| 4 | SPM-SaaS-17 | Super Admin billing view (paid plans, failed payments, plan status) | The Super Admin reviews paid subscriptions, plan status and failed payments across all customers. | SPM-SaaS-14 |
| 5 | SPM-SaaS-15 | Contact sales / Enterprise request form | A larger prospect submits their requirements so the sales team can follow up. | SPM-SaaS-9 |
| 6 | SPM-WIN-1 | Windows: always-on protection that starts with the computer | The agent runs on Windows automatically from start-up and keeps running in the background without user action. | SPM-AGT-L1 |
| 7 | SPM-WIN-3 | Windows: security certificate trust and AI application traffic protection | Trust the security certificate on Windows and protect AI usage from installed applications and developer tools. | SPM-WIN-1 |
| 8 | SPM-WIN-4 | Windows: protect ChatGPT / Claude / Gemini websites | Protect what employees type into AI websites from Windows browsers. | SPM-WIN-3 |
| 9 | SPM-WIN-2 | Windows: silent enterprise rollout via MSI, Group Policy or Intune | IT deploys the agent to many Windows machines at once, with no prompts for the employee. | SPM-WIN-4 |
| 10 | SPM-WIN-5 | Windows: signed installer and tray app showing protection status | Ship a trusted signed installer and a small status indicator so employees can confirm protection is active. | SPM-WIN-2 |
| 11 | SPM-DASH-2 | Single console view across Linux and Windows devices | The admin manages and monitors Linux and Windows machines together in one console. | SPM-WIN-1 |

**Sprint outcome:** The product serves Linux and Windows customers, blocks malicious AI prompts,
and sells itself through self-service paid plans and enterprise enquiries.

---

## Dependency Map Across Sprints

```
Sprint 1  Company workspace + install token ──► Agent enrolment ──► Device Online ──► First audit record
             │                                                                             │
Sprint 2     └► Sensitive data rules ──────────► Agent masks Linux traffic ─────────────────┘
                                                        │
Sprint 3  Dashboards + fleet + install credential ──────┴► Download package ──► Deploy wizard
                                                                                    │
Sprint 4  Paid plans + threat detection ──────────────► Windows agent ──────────────┴► One console
```

---

## Feature Coverage Summary

| Area | Sprint 1 | Sprint 2 | Sprint 3 | Sprint 4 |
|------|----------|----------|----------|----------|
| Super Admin | List, suspend, activate companies | — | Customer overview and usage | Billing and subscription view |
| Company admin | Signup, login, first policy, first audit record | Choose protected data types, view plans | Dashboard, fleet, settings, usage, deploy wizard | Password recovery, cross-platform console |
| SaaS platform | Data isolation, company workspace | Plans and limits | Install credentials, usage tracking | Checkout, subscriptions, enterprise enquiries |
| Linux agent | Skeleton, enrolment, heartbeat, first inspection | Certificate trust, API and website protection, install, reinstall | Company-bound package, status indicator | Shared engine reused by Windows |
| Windows agent | — | — | — | Service, interception, websites, MSI, signed installer |
| Security engine | First inspection and audit entry | Sensitive data detection and masking | Security metrics | Threat detection |
