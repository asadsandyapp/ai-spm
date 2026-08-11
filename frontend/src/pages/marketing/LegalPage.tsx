import { Link } from "react-router-dom";
import { MarketingLayout } from "@/components/marketing/MarketingLayout";

type LegalKind = "terms" | "privacy" | "dpa";

interface LegalPageProps {
  kind: LegalKind;
}

const META: Record<
  LegalKind,
  { title: string; updated: string; intro: string; sections: { heading: string; body: string }[] }
> = {
  terms: {
    title: "Terms of Service",
    updated: "August 2026",
    intro:
      "These Terms of Service govern your use of the AI-SPM platform. By creating an account or using our services, you agree to these terms.",
    sections: [
      {
        heading: "1. Service description",
        body: "AI-SPM provides AI Security Posture Management software including endpoint agents, a tenant-isolated security gateway, policy enforcement, PII masking, and audit logging. The service is provided on a subscription basis priced by protected endpoints (agents).",
      },
      {
        heading: "2. Acceptable use",
        body: "You may use AI-SPM only for lawful enterprise security purposes within your organization. You are responsible for ensuring agent deployment complies with applicable laws and internal policies. You may not attempt to bypass tenant isolation, access other organizations' data, or reverse-engineer the service.",
      },
      {
        heading: "3. Subscription & billing",
        body: "Plans are billed monthly based on the number of protected endpoints enrolled. Overages or plan changes are subject to the pricing published on our website. Enterprise agreements may include custom terms negotiated separately.",
      },
      {
        heading: "4. Data & confidentiality",
        body: "We process masked audit data and tenant metadata as described in our Privacy Policy and DPA. Raw PII from employee prompts is masked before storage. You retain ownership of your organization's data.",
      },
      {
        heading: "5. Limitation of liability",
        body: "AI-SPM is provided as a security control layer. While we block requests when detection cannot complete safely, you acknowledge that no security product can guarantee complete prevention of all data leakage scenarios. Liability is limited to fees paid in the preceding twelve months.",
      },
      {
        heading: "6. Contact",
        body: "Questions about these terms may be directed to legal@aispm.io or via our contact sales form.",
      },
    ],
  },
  privacy: {
    title: "Privacy Policy",
    updated: "August 2026",
    intro:
      "This Privacy Policy describes how AI-SPM collects, uses, and protects information when you use our platform and website.",
    sections: [
      {
        heading: "1. Information we collect",
        body: "Account information (name, email, organization), billing metadata via Stripe, agent fleet telemetry (hostname, status, version), and masked audit events from inspected AI traffic. We do not intentionally store raw PII from employee prompts in audit logs.",
      },
      {
        heading: "2. How we use information",
        body: "To provide the security service, enforce plan limits, improve product reliability, communicate service updates, and comply with legal obligations.",
      },
      {
        heading: "3. Sharing",
        body: "We share data with subprocessors necessary to operate the service (e.g., cloud hosting, Stripe for payments, email delivery). We do not sell personal information.",
      },
      {
        heading: "4. Retention",
        body: "Audit retention follows your subscription plan (7 / 30 / 365 days). Account data is retained while your organization is active and deleted upon verified GDPR erase requests subject to legal holds.",
      },
      {
        heading: "5. Contact",
        body: "Privacy inquiries: privacy@aispm.io.",
      },
    ],
  },
  dpa: {
    title: "Data Processing Addendum",
    updated: "August 2026",
    intro:
      "This DPA outlines the roles of AI-SPM as a processor and the customer as controller for personal data processed through the platform.",
    sections: [
      {
        heading: "1. Scope",
        body: "Applies to personal data processed on behalf of the customer in connection with AI-SPM services, including masked audit content and user account data.",
      },
      {
        heading: "2. Security measures",
        body: "Includes organization isolation, trusted endpoint enrollment, encryption in transit, access controls, and blocking when detection cannot complete safely.",
      },
      {
        heading: "3. Subprocessors",
        body: "A current list of subprocessors is available on request. Customers will be notified of material changes as required by applicable law.",
      },
      {
        heading: "4. Assistance",
        body: "AI-SPM will assist with data subject requests, DPIAs, and breach notifications consistent with the customer's instructions and applicable regulations.",
      },
    ],
  },
};

export function LegalPage({ kind }: LegalPageProps) {
  const doc = META[kind];

  return (
    <MarketingLayout>
      <section className="mkt-page-hero">
        <div className="mkt-shell py-16 lg:py-20">
          <div className="mkt-panel mx-auto max-w-4xl p-8 sm:p-12 lg:p-14">
            <p className="text-sm font-semibold uppercase tracking-wider text-slate-500">
              Last updated · {doc.updated}
            </p>
            <h1 className="mt-4 font-display text-4xl font-bold text-white sm:text-5xl lg:text-6xl">
              {doc.title}
            </h1>
            <p className="mt-6 text-xl leading-relaxed text-slate-300">{doc.intro}</p>

            <div className="mt-12 space-y-10">
              {doc.sections.map((section) => (
                <section key={section.heading}>
                  <h2 className="font-display text-2xl font-semibold text-white sm:text-3xl">
                    {section.heading}
                  </h2>
                  <p className="mt-4 text-lg leading-relaxed text-slate-400">{section.body}</p>
                </section>
              ))}
            </div>

            <div className="mkt-divider mt-14" />
            <p className="pt-7 text-lg text-slate-500">
              Questions?{" "}
              <Link to="/contact-sales" className="font-medium text-teal-400 hover:text-teal-300">
                Contact us
              </Link>
            </p>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
}
