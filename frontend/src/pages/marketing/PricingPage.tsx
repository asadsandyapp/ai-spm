import { Link } from "react-router-dom";
import { Check, Minus, ArrowRight } from "lucide-react";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";
import { cn } from "@/lib/utils";

type FeatureValue = boolean | string;

interface PlanColumn {
  id: string;
  name: string;
  audience: string;
  price: string;
  agents: string;
  prompts: string;
  highlights: string[];
  cta: { label: string; to: string; primary?: boolean };
  highlight?: boolean;
}

interface FeatureRow {
  label: string;
  starter: FeatureValue;
  pro: FeatureValue;
  enterprise: FeatureValue;
}

const PLANS: PlanColumn[] = [
  {
    id: "starter",
    name: "Starter",
    audience: "Small teams / pilot",
    price: "$1,500",
    agents: "Up to 25 protected endpoints",
    prompts: "50,000 prompts / month",
    highlights: [
      "Essential sensitive-data masking",
      "AI apps + browser AI protection",
      "Standard policy controls",
      "7-day masked audit history",
      "Email support",
    ],
    cta: { label: "Get started", to: "/signup", primary: true },
  },
  {
    id: "professional",
    name: "Professional",
    audience: "Mid-size companies",
    price: "$4,500",
    agents: "Up to 150 protected endpoints",
    prompts: "500,000 prompts / month",
    highlights: [
      "Advanced masking + custom rules",
      "Threat / jailbreak detection",
      "Multi-provider AI coverage",
      "30-day audit retention",
      "Analytics dashboard",
      "Business-hours support",
    ],
    cta: { label: "Get started", to: "/signup", primary: true },
    highlight: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    audience: "Large enterprises & MSPs",
    price: "$12,000",
    agents: "Unlimited protected endpoints",
    prompts: "Unlimited prompts / month",
    highlights: [
      "Full masking + custom rules",
      "Threat / jailbreak detection",
      "High-availability multi-provider",
      "1-year audit retention + export",
      "Custom dashboards",
      "24/7 support with SLA",
    ],
    cta: { label: "Contact sales", to: "/contact-sales" },
  },
];

const FEATURES: FeatureRow[] = [
  { label: "Protected endpoints (agents)", starter: "25", pro: "150", enterprise: "Unlimited" },
  { label: "Monthly prompt quota", starter: "50,000", pro: "500,000", enterprise: "Unlimited" },
  { label: "AI provider coverage", starter: "Single provider", pro: "Multi-provider", enterprise: "Multi + HA" },
  { label: "Sensitive data masking", starter: "Essential", pro: "Advanced + custom", enterprise: "Full + custom rules" },
  { label: "Policy controls", starter: "Standard", pro: "Advanced + topics", enterprise: "Granular + API" },
  { label: "Dashboard", starter: "Basic metrics", pro: "Analytics + builder", enterprise: "Custom dashboards" },
  { label: "Threat / jailbreak detection", starter: false, pro: true, enterprise: true },
  { label: "Audit retention", starter: "7 days", pro: "30 days", enterprise: "1 year + export" },
  { label: "AI API protection", starter: true, pro: true, enterprise: true },
  { label: "Browser AI tool protection", starter: true, pro: true, enterprise: true },
  { label: "Guided endpoint installer", starter: true, pro: true, enterprise: true },
  { label: "Support", starter: "Email", pro: "Business hours", enterprise: "24/7 + SLA" },
];

function CellValue({ value }: { value: FeatureValue }) {
  if (value === true) {
    return (
      <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-teal-400/10">
        <Check className="h-5 w-5 text-teal-400" aria-label="Included" />
      </span>
    );
  }
  if (value === false) {
    return <Minus className="mx-auto h-5 w-5 text-slate-600" aria-label="Not included" />;
  }
  return <span className="text-[17px] font-medium text-slate-100">{value}</span>;
}

export function PricingPage() {
  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(64rem 36rem at 50% 0%, rgba(45,212,191,0.13), transparent 55%)",
          }}
        />
        <div className="mkt-shell relative py-16 lg:py-20">
          <div className="max-w-4xl">
            <p className="mkt-eyebrow">Pricing</p>
            <h1 className="mkt-h1 mt-4">Plans built for endpoint scale.</h1>
            <p className="mkt-lead mt-6 max-w-3xl text-slate-200">
              Billed monthly. Capacity is measured in protected endpoints (agents) — never users or
              seats.
            </p>
          </div>

          <div className="mt-12 grid items-stretch gap-5 lg:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.id}
                className={cn(
                  "mkt-panel-hover relative flex flex-col p-8 sm:p-9",
                  plan.highlight && "border-teal-400/40 ring-1 ring-teal-400/25",
                )}
              >
                {plan.highlight && (
                  <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 rounded-full bg-teal-400 px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-marketing-ink">
                    Recommended
                  </span>
                )}
                <p className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  {plan.audience}
                </p>
                <h2 className="mt-3 font-display text-4xl font-bold text-white">{plan.name}</h2>
                <p className="mt-3 text-lg text-slate-300">{plan.agents}</p>

                <p className="mt-7 font-display text-5xl font-bold text-teal-400 sm:text-[3.25rem]">
                  {plan.price}
                  <span className="text-xl font-normal text-slate-500">/mo</span>
                </p>
                <p className="mt-2 text-[15px] font-medium text-slate-400">{plan.prompts}</p>

                <ul className="mt-8 flex-1 space-y-3.5 border-t border-white/10 pt-7">
                  {plan.highlights.map((item) => (
                    <li key={item} className="flex items-start gap-3 text-[16px] leading-snug text-slate-200">
                      <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-teal-400/15">
                        <Check className="h-3.5 w-3.5 text-teal-400" strokeWidth={2.75} />
                      </span>
                      {item}
                    </li>
                  ))}
                </ul>

                <Link
                  to={plan.cta.to}
                  className={cn(
                    "mt-9 w-full",
                    plan.cta.primary ? "mkt-btn-primary" : "mkt-btn-ghost",
                  )}
                >
                  {plan.cta.label}
                  <ArrowRight className="h-5 w-5" />
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#090e1a]">
        <div className="mkt-shell py-16 lg:py-20">
          <div className="mkt-panel overflow-hidden">
            <div className="border-b border-white/10 px-7 py-7 sm:px-10">
              <h2 className="font-display text-3xl font-semibold text-white">
                Full capability matrix
              </h2>
              <p className="mt-3 text-lg text-slate-400">
                Compare every capability side by side. Your console matches the plan you choose.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-white/10 bg-white/[0.03]">
                    <th className="px-7 py-5 text-sm font-semibold uppercase tracking-wider text-slate-400 sm:px-10">
                      Capability
                    </th>
                    {PLANS.map((plan) => (
                      <th
                        key={plan.id}
                        className={cn(
                          "px-4 py-5 text-center text-lg font-semibold text-white",
                          plan.highlight && "bg-teal-400/[0.05]",
                        )}
                      >
                        {plan.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {FEATURES.map((row, i) => (
                    <tr
                      key={row.label}
                      className={cn(
                        "border-b border-white/[0.05]",
                        i % 2 === 0 ? "bg-transparent" : "bg-white/[0.02]",
                      )}
                    >
                      <td className="px-7 py-5 text-[17px] text-slate-200 sm:px-10">{row.label}</td>
                      <td className="px-4 py-5 text-center">
                        <CellValue value={row.starter} />
                      </td>
                      <td
                        className={cn(
                          "px-4 py-5 text-center",
                          PLANS[1].highlight && "bg-teal-400/[0.03]",
                        )}
                      >
                        <CellValue value={row.pro} />
                      </td>
                      <td className="px-4 py-5 text-center">
                        <CellValue value={row.enterprise} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="mt-10 text-center text-lg text-slate-400">
            Need a custom quote for large agent fleets?{" "}
            <Link to="/contact-sales" className="font-semibold text-teal-400 hover:text-teal-300">
              Contact sales →
            </Link>
          </p>
        </div>
      </section>
    </MarketingLayout>
  );
}
