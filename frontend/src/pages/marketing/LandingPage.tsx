import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  FileText,
  Lock,
  Server,
  Shield,
  Network,
} from "lucide-react";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";
import { ProtectionVisual } from "@/components/marketing/ProtectionVisual";

const PLANS = [
  {
    name: "Starter",
    price: "$1,500",
    agents: "Up to 25 agents",
    note: "Pilots & small teams",
    highlights: ["50k prompts / mo", "Essential masking", "7-day audit"],
  },
  {
    name: "Professional",
    price: "$4,500",
    agents: "Up to 150 agents",
    note: "Mid-size security orgs",
    featured: true,
    highlights: ["500k prompts / mo", "Threat detection", "30-day audit"],
  },
  {
    name: "Enterprise",
    price: "$12,000",
    agents: "Unlimited agents",
    note: "Large fleets & MSPs",
    highlights: ["Unlimited prompts", "Custom rules", "1-year audit + SLA"],
  },
] as const;

const PROTECTS = [
  { title: "Identity & national IDs", body: "SSN, CNIC, passport, driver’s license" },
  { title: "Contact & credentials", body: "Email, phone, passwords, API keys" },
  { title: "Financial data", body: "Cards, IBAN, account numbers" },
  { title: "Internal identifiers", body: "Project codes, employee IDs, tickets" },
  { title: "Threat patterns", body: "Jailbreak & prompt-injection attempts" },
  { title: "Policy violations", body: "Disallowed models, topics, providers" },
];

const STEPS = [
  {
    icon: Server,
    title: "Install",
    body: "One agent per endpoint — deploy with your existing IT tools or a guided installer. Protection starts automatically for AI apps and browser sessions.",
  },
  {
    icon: Eye,
    title: "Inspect",
    body: "Every outbound prompt is checked against your organization’s policies before it reaches an AI provider.",
  },
  {
    icon: Shield,
    title: "Mask or block",
    body: "Sensitive values are rewritten in real time — or the request is blocked. Providers never see raw company secrets.",
  },
  {
    icon: FileText,
    title: "Audit",
    body: "Security teams get a searchable history of inspected prompts with sensitive data already masked — not stored in the clear.",
  },
];

const IT_POINTS = [
  {
    icon: Network,
    title: "Works without extensions",
    body: "Employees keep using ChatGPT, Claude, and Gemini as usual",
  },
  {
    icon: Lock,
    title: "Trusted endpoints only",
    body: "Only devices you enroll can join your workspace",
  },
  {
    icon: Shield,
    title: "Org-isolated by design",
    body: "Your prompts and audit history stay in your organization",
  },
];

const TRUST = [
  "Protects AI apps & APIs",
  "ChatGPT · Claude · Gemini",
  "Sensitive data masking",
  "Org-isolated workspaces",
  "Masked audit history",
];

export function LandingPage() {
  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(90rem 52rem at 88% -5%, rgba(45,212,191,0.16), transparent 52%), radial-gradient(60rem 44rem at -5% 90%, rgba(14,165,233,0.09), transparent 48%)",
          }}
        />

        <div className="mkt-shell relative grid items-center gap-12 py-16 lg:grid-cols-[1.15fr_0.95fr] lg:gap-14 lg:py-20 xl:gap-16">
          <div className="animate-fade-in min-w-0">
            <p className="mkt-eyebrow">AI Security Posture Management</p>
            <h1 className="mkt-h1 mt-5 max-w-[16ch]">
              Mask sensitive data before it reaches AI.
            </h1>
            <p className="mkt-lead mt-7 max-w-xl text-slate-200">
              One agent install per endpoint. Protect ChatGPT, Claude, Gemini, and AI APIs with
              central policy, sensitive-data masking, threat controls, and masked audit for IT.
            </p>
            <p className="mt-6 max-w-xl border-l-[3px] border-teal-400 pl-5 text-lg font-medium leading-snug text-teal-100 sm:text-xl">
              Sensitive company data never reaches ChatGPT, Claude, or Gemini unprotected.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link to="/signup" className="mkt-btn-primary">
                Start protecting AI
                <ArrowRight className="h-5 w-5" />
              </Link>
              <Link to="/pricing" className="mkt-btn-ghost">
                See pricing
              </Link>
            </div>
          </div>

          <div className="relative min-w-0 w-full">
            <ProtectionVisual />
          </div>
        </div>

        <div className="relative border-t border-white/10 bg-black/25">
          <div className="mkt-shell flex flex-wrap items-center gap-x-8 gap-y-3 py-5">
            <span className="text-sm font-semibold uppercase tracking-wider text-slate-500">
              Built for
            </span>
            {TRUST.map((item) => (
              <span key={item} className="text-[15px] font-medium text-slate-300">
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-white/10 bg-[#090e1a]">
        <div className="mkt-shell grid gap-10 py-16 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:gap-20 lg:py-20">
          <div>
            <p className="mkt-eyebrow">The problem</p>
            <h2 className="mkt-h2 mt-4">Employees paste secrets into AI every day.</h2>
          </div>
          <p className="mkt-body text-slate-300">
            Emails, SSNs, card numbers, and internal identifiers can flow straight to third-party
            AI tools unless you stop them first. AI-SPM inspects and masks sensitive content before
            any prompt leaves your organization — in apps and in the browser.
          </p>
        </div>
      </section>

      <section className="border-b border-white/10">
        <div className="mkt-section">
          <div className="mb-10 flex flex-col gap-4 lg:mb-12 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <p className="mkt-eyebrow">How it works</p>
              <h2 className="mkt-h2 mt-4">Install → Inspect → Mask → Audit</h2>
            </div>
            <p className="max-w-md text-lg text-slate-400 lg:text-right">
              One control plane for every managed endpoint — without a browser extension.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {STEPS.map((step, i) => (
              <article key={step.title} className="mkt-panel-hover p-7 sm:p-8">
                <div className="mb-6 flex items-center justify-between gap-3">
                  <div className="mkt-icon-box">
                    <step.icon className="h-5 w-5" />
                  </div>
                  <span className="font-display text-4xl font-bold tabular-nums text-white/15">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                </div>
                <h3 className="font-display text-2xl font-semibold text-white">{step.title}</h3>
                <p className="mt-3 text-[17px] leading-relaxed text-slate-400">{step.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-white/10 bg-[#090e1a]">
        <div className="mkt-section">
          <div className="mb-10 max-w-3xl">
            <p className="mkt-eyebrow">What we protect</p>
            <h2 className="mkt-h2 mt-4">Sensitive data and threats — before they leave.</h2>
            <p className="mkt-body mt-5">
              Turn detection categories on or off for your organization. Block risky prompts, mask
              regulated data, and enforce which AI models and providers are allowed — from one
              console.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PROTECTS.map((item) => (
              <div key={item.title} className="mkt-panel-hover flex gap-4 p-6 sm:p-7">
                <CheckCircle2 className="mt-1 h-6 w-6 shrink-0 text-teal-400" />
                <div>
                  <p className="text-xl font-semibold text-white">{item.title}</p>
                  <p className="mt-2 text-[17px] text-slate-400">{item.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-white/10">
        <div className="mkt-section">
          <div className="mkt-panel grid overflow-hidden lg:grid-cols-[1.4fr_1fr]">
            <div className="relative border-b border-white/10 p-8 sm:p-10 lg:border-b-0 lg:border-r lg:p-12">
              <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-teal-400/10 blur-3xl" />
              <div className="relative">
                <p className="mkt-eyebrow">For IT & security teams</p>
                <h2 className="mkt-h2 mt-4">
                  Enterprise deployment without browser extensions.
                </h2>
                <p className="mkt-body mt-5 max-w-xl">
                  Roll out with your existing device management, or use the sealed installer. See
                  fleet status, manage policies, review threats, and export records for compliance
                  — all inside your own isolated workspace.
                </p>
                <Link to="/product" className="mkt-btn-ghost mt-9 inline-flex">
                  Explore features
                  <ArrowRight className="h-5 w-5" />
                </Link>
              </div>
            </div>
            <div className="flex flex-col justify-center gap-4 bg-black/25 p-7 sm:p-9">
              {IT_POINTS.map((p) => (
                <div
                  key={p.title}
                  className="flex items-start gap-4 rounded-xl border border-white/10 bg-white/[0.04] p-5"
                >
                  <div className="mkt-icon-box !h-12 !w-12">
                    <p.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-white">{p.title}</p>
                    <p className="mt-1 text-[16px] text-slate-400">{p.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-white/10 bg-[#090e1a]">
        <div className="mkt-section">
          <div className="mb-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="mkt-eyebrow">Plans</p>
              <h2 className="mkt-h2 mt-4">Priced by protected endpoints, not seats.</h2>
            </div>
            <Link to="/pricing" className="mkt-btn-primary inline-flex self-start sm:self-auto">
              Compare plans
              <ArrowRight className="h-5 w-5" />
            </Link>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`mkt-panel-hover p-8 ${
                  "featured" in plan && plan.featured
                    ? "border-teal-400/35 ring-1 ring-teal-400/25"
                    : ""
                }`}
              >
                <p className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  {plan.note}
                </p>
                <h3 className="mt-3 font-display text-3xl font-semibold text-white">
                  {plan.name}
                </h3>
                <p className="mt-6 font-display text-5xl font-bold text-teal-400">
                  {plan.price}
                  <span className="text-xl font-normal text-slate-500">/mo</span>
                </p>
                <p className="mt-3 text-lg text-slate-300">{plan.agents}</p>
                <ul className="mt-6 space-y-2.5 border-t border-white/10 pt-6">
                  {plan.highlights.map((item) => (
                    <li key={item} className="flex items-center gap-2.5 text-[15px] text-slate-300">
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-teal-400" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mkt-shell py-16 text-center sm:py-20">
          <h2 className="mkt-h2 mx-auto max-w-4xl">
            Ready to govern AI across your organization?
          </h2>
          <p className="mkt-lead mx-auto mt-5 max-w-2xl text-slate-300">
            Create a workspace, choose a plan, install agents, and see masked audit events from
            day one.
          </p>
          <div className="mt-10 flex flex-wrap justify-center gap-4">
            <Link to="/signup" className="mkt-btn-primary">
              Start protecting AI
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link to="/contact-sales" className="mkt-btn-ghost">
              Contact sales
            </Link>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
