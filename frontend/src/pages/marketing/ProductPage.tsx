import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  FileSearch,
  LayoutDashboard,
  Network,
  Shield,
  ShieldAlert,
  Sliders,
} from "lucide-react";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";

const FEATURES = [
  {
    icon: Network,
    title: "Central protection for every prompt",
    body: "Outbound AI traffic from your organization is inspected before it reaches ChatGPT, Claude, Gemini, or other providers — under your policies.",
  },
  {
    icon: Shield,
    title: "Sensitive data detection & masking",
    body: "Automatically finds and masks SSNs, emails, cards, credentials, and more. You choose which categories to protect from the admin console.",
  },
  {
    icon: Sliders,
    title: "Policy controls",
    body: "Allow, block, or mask by model, provider, and topic. Changes apply across your fleet as soon as you save them.",
  },
  {
    icon: LayoutDashboard,
    title: "Admin console",
    body: "Live metrics, device status, and security events in one place — so IT can see posture across the organization at a glance.",
  },
  {
    icon: ShieldAlert,
    title: "Threat feed",
    body: "Detect jailbreak and prompt-injection attempts on Professional and Enterprise. Risky prompts can be blocked before they leave.",
  },
  {
    icon: FileSearch,
    title: "Masked audit log",
    body: "A searchable history of inspected prompts with sensitive values already masked. Retention and export follow your plan.",
  },
  {
    icon: Bot,
    title: "Endpoint agents",
    body: "One install per device protects AI apps and browser sessions for ChatGPT, Claude, and Gemini — no browser extension for employees to manage.",
  },
];

export function ProductPage() {
  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(56rem 32rem at 12% 0%, rgba(45,212,191,0.13), transparent 55%)",
          }}
        />
        <div className="mkt-shell relative py-16 lg:py-20">
          <div className="max-w-4xl">
            <p className="mkt-eyebrow">Product</p>
            <h1 className="mkt-h1 mt-4">Complete AI security posture for the enterprise.</h1>
            <p className="mkt-lead mt-6 max-w-3xl text-slate-200">
              AI-SPM inspects outbound AI traffic before it leaves your organization — masking
              sensitive data, enforcing policy, and auditing every interaction.
            </p>
          </div>

          <div className="mkt-panel mt-12 grid gap-8 p-8 sm:grid-cols-3 sm:p-10">
            {[
              { k: "Coverage", v: "Apps + web AI tools" },
              { k: "Controls", v: "Policy · Mask · Block" },
              { k: "Evidence", v: "Masked audit history" },
            ].map((item) => (
              <div key={item.k}>
                <p className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  {item.k}
                </p>
                <p className="mt-2 font-display text-2xl font-semibold text-white">{item.v}</p>
              </div>
            ))}
          </div>

          <div className="mt-8 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {FEATURES.map((feature) => (
              <article key={feature.title} className="mkt-panel-hover p-7 sm:p-8">
                <div className="mkt-icon-box mb-6">
                  <feature.icon className="h-5 w-5" />
                </div>
                <h2 className="font-display text-2xl font-semibold text-white">
                  {feature.title}
                </h2>
                <p className="mt-3 text-[17px] leading-relaxed text-slate-400">{feature.body}</p>
              </article>
            ))}
          </div>

          <div className="mkt-panel relative mt-12 overflow-hidden p-10 text-center sm:p-12">
            <div className="absolute inset-0 bg-gradient-to-br from-teal-400/10 via-transparent to-transparent" />
            <div className="relative">
              <p className="mx-auto max-w-3xl text-xl font-medium text-teal-100 sm:text-2xl">
                Sensitive company data never reaches ChatGPT, Claude, or Gemini unprotected.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-4">
                <Link to="/signup" className="mkt-btn-primary">
                  Get started
                  <ArrowRight className="h-5 w-5" />
                </Link>
                <Link to="/pricing" className="mkt-btn-ghost">
                  View pricing
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
