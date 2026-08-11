import type { ReactNode } from "react";
import { ShieldCheck, Activity, Lock, Network } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

const HIGHLIGHTS = [
  {
    icon: Activity,
    title: "Real-time fleet visibility",
    body: "See every protected endpoint, prompt decision, and policy hit in one place.",
  },
  {
    icon: Lock,
    title: "Policy before the provider",
    body: "Mask or block sensitive content before it leaves your controlled path.",
  },
  {
    icon: Network,
    title: "Organization isolation",
    body: "Prompts, policies, and audit history stay inside your company workspace.",
  },
];

interface AuthLayoutProps {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: ReactNode;
}

export function AuthLayout({
  eyebrow,
  title,
  subtitle,
  children,
}: AuthLayoutProps) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1.08fr_0.92fr]">
      {/* Brand plane */}
      <div className="relative hidden overflow-hidden bg-[#050910] lg:flex lg:flex-col lg:justify-between lg:px-14 lg:py-12 xl:px-16">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(56rem 42rem at 8% -8%, rgba(45,212,191,0.22), transparent 58%), radial-gradient(42rem 38rem at 95% 90%, rgba(14,165,233,0.14), transparent 52%), linear-gradient(160deg, rgba(255,255,255,0.03), transparent 40%)",
          }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(148,163,184,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.07) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
            maskImage:
              "radial-gradient(ellipse 80% 70% at 30% 40%, black, transparent)",
          }}
        />

        <div className="relative">
          <Logo variant="light" />
        </div>

        <div className="relative max-w-xl">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full bg-teal-400/10 px-3.5 py-1.5 text-sm font-medium text-teal-200 ring-1 ring-inset ring-teal-400/25">
            <ShieldCheck className="h-4 w-4" />
            Enterprise AI security
          </div>
          <h2 className="font-display text-[2.65rem] font-bold leading-[1.12] tracking-tight text-white xl:text-5xl">
            Govern every AI interaction across your enterprise.
          </h2>
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-slate-300">
            Continuous posture management for AI tools — policy enforcement, PII
            masking, and a complete masked audit trail for your security team.
          </p>

          <ul className="mt-12 space-y-5">
            {HIGHLIGHTS.map((h) => (
              <li
                key={h.title}
                className="flex gap-4 rounded-2xl border border-white/5 bg-white/[0.03] p-4 backdrop-blur-sm"
              >
                <div className="mt-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-teal-400/10 text-teal-300 ring-1 ring-inset ring-teal-400/25">
                  <h.icon className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-base font-semibold text-white">{h.title}</p>
                  <p className="mt-1 text-[15px] leading-relaxed text-slate-400">
                    {h.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-slate-500">
          <span>Encrypted sessions</span>
          <span className="h-1 w-1 rounded-full bg-slate-600" />
          <span>Role-based access</span>
          <span className="h-1 w-1 rounded-full bg-slate-600" />
          <span>Tenant isolation</span>
        </div>
      </div>

      {/* Form plane */}
      <div className="relative flex items-center justify-center overflow-hidden bg-[#f4f6f9] px-5 py-12 sm:px-10">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(36rem 28rem at 100% 0%, rgba(14,165,233,0.08), transparent 55%), radial-gradient(28rem 24rem at 0% 100%, rgba(45,212,191,0.06), transparent 50%)",
          }}
        />
        <div className="relative w-full max-w-[26rem] animate-fade-in">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>

          <div className="rounded-2xl border border-ink-200/80 bg-white p-7 shadow-[0_24px_60px_-28px_rgba(15,23,42,0.28)] sm:p-9">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand-600">
              {eyebrow}
            </p>
            <h1 className="mt-2.5 font-display text-3xl font-semibold tracking-tight text-ink-900 sm:text-[2.05rem]">
              {title}
            </h1>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-500 sm:text-base">
              {subtitle}
            </p>
            <div className="mt-8">{children}</div>
          </div>

          <p className="mt-6 text-center text-xs text-ink-400 lg:hidden">
            © {new Date().getFullYear()} AI-SPM. Proprietary.
          </p>
        </div>
      </div>
    </div>
  );
}
