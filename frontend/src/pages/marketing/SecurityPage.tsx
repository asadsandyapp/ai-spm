import { Link } from "react-router-dom";
import { ArrowRight, Building2, KeyRound, Lock, ShieldAlert, ShieldCheck } from "lucide-react";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";

const PILLARS = [
  {
    icon: ShieldCheck,
    title: "Your data stays in your organization",
    body: "Every workspace is fully isolated. One company’s prompts, policies, and audit history can never be seen by another — even on the same platform.",
  },
  {
    icon: Building2,
    title: "Platform ops without content access",
    body: "Vendor administrators can manage accounts and billing, but they never see what employees typed or what was masked in your audit trail.",
  },
  {
    icon: KeyRound,
    title: "Trusted device enrollment",
    body: "Only endpoints you authorize can join your workspace. Each agent is bound to your organization so rogue devices cannot register or send traffic.",
  },
  {
    icon: Lock,
    title: "Masked records only",
    body: "Security teams get the visibility they need for investigations — without storing raw secrets, IDs, or credentials in the platform.",
  },
  {
    icon: ShieldAlert,
    title: "Safe by default when checks fail",
    body: "If detection cannot complete, the request is blocked and logged. Unpaid workspaces cannot enroll devices or send prompts until billing is active.",
  },
];

export function SecurityPage() {
  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(52rem 30rem at 88% 0%, rgba(45,212,191,0.12), transparent 55%)",
          }}
        />
        <div className="mkt-shell relative py-16 lg:py-20">
          <div className="max-w-4xl">
            <p className="mkt-eyebrow">Security</p>
            <h1 className="mkt-h1 mt-4">Built for teams who cannot afford leaks.</h1>
            <p className="mkt-lead mt-6 max-w-3xl text-slate-200">
              Strong workspace isolation, trusted endpoint enrollment, and masked audit trails —
              so sensitive company data never leaves your control unprotected.
            </p>
          </div>

          <div className="mt-12 grid gap-5 lg:grid-cols-2">
            {PILLARS.map((pillar, i) => (
              <article
                key={pillar.title}
                className={`mkt-panel-hover p-7 sm:p-9 ${i === 0 ? "lg:col-span-2" : ""}`}
              >
                <div className="flex gap-6">
                  <div className="mkt-icon-box shrink-0 !h-14 !w-14">
                    <pillar.icon className="h-6 w-6" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="font-display text-2xl font-semibold text-white sm:text-3xl">
                      {pillar.title}
                    </h2>
                    <p className="mt-4 text-[17px] leading-relaxed text-slate-400">{pillar.body}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>

          <div className="mt-12 flex flex-wrap gap-4">
            <Link to="/contact-sales" className="mkt-btn-primary">
              Talk to our team
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link to="/dpa" className="mkt-btn-ghost">
              View DPA
            </Link>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
