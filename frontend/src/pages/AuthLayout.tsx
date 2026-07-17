import type { ReactNode } from "react";
import { ShieldCheck, Activity, Lock, Network } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

const HIGHLIGHTS = [
  {
    icon: Activity,
    title: "Real-time fleet visibility",
    body: "Monitor every AI agent, endpoint, and prompt across your organization.",
  },
  {
    icon: Lock,
    title: "Policy enforcement",
    body: "Block PII leakage and risky prompts before they ever reach an LLM.",
  },
  {
    icon: Network,
    title: "Tenant-isolated by design",
    body: "Defense-in-depth isolation with per-tenant RLS and immutable audit trails.",
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
    <div className="grid min-h-full lg:grid-cols-2">
      {/* Brand / marketing panel */}
      <div className="relative hidden overflow-hidden bg-ink-900 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "radial-gradient(60rem 60rem at 15% -10%, rgba(52,102,255,0.28), transparent 55%), radial-gradient(50rem 50rem at 110% 110%, rgba(22,51,225,0.22), transparent 50%)",
          }}
        />
        <div className="relative">
          <Logo variant="light" />
        </div>

        <div className="relative max-w-md">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full bg-white/5 px-3 py-1.5 text-xs font-medium text-brand-200 ring-1 ring-inset ring-white/10">
            <ShieldCheck className="h-3.5 w-3.5" />
            AI Security Posture Management
          </div>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-white">
            Govern every AI interaction across your enterprise.
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-ink-300">
            AI-SPM gives security teams continuous posture management for AI
            agents — with policy enforcement, PII masking, and a complete audit
            trail.
          </p>

          <ul className="mt-10 space-y-5">
            {HIGHLIGHTS.map((h) => (
              <li key={h.title} className="flex gap-3.5">
                <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/5 text-brand-300 ring-1 ring-inset ring-white/10">
                  <h.icon className="h-[18px] w-[18px]" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{h.title}</p>
                  <p className="mt-0.5 text-sm text-ink-400">{h.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-ink-500">
          © {new Date().getFullYear()} AI-SPM. Proprietary — all rights reserved.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center bg-ink-50 px-6 py-12">
        <div className="w-full max-w-sm animate-fade-in">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <p className="text-xs font-semibold uppercase tracking-wider text-brand-600">
            {eyebrow}
          </p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink-900">
            {title}
          </h1>
          <p className="mt-1.5 text-sm text-ink-500">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  );
}
