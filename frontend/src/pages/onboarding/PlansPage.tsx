import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowRight, Check, Loader2, ShieldCheck } from "lucide-react";
import { ApiError, adminApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type PlanId = "starter" | "professional";

const PLANS = [
  {
    id: "starter" as const,
    name: "Starter",
    audience: "Small teams / pilot",
    price: "$1,500",
    agents: "Up to 25 protected endpoints",
    features: [
      "AI apps + ChatGPT / Claude / Gemini in the browser",
      "Essential sensitive-data masking & 7-day audit",
      "Standard policy & basic dashboard",
    ],
  },
  {
    id: "professional" as const,
    name: "Professional",
    audience: "Mid-size companies",
    price: "$4,500",
    agents: "Up to 150 protected endpoints",
    features: [
      "Everything in Starter",
      "Threat / jailbreak detection",
      "Advanced masking, topic blocking, multi-provider",
      "30-day audit retention",
    ],
    highlight: true,
  },
];

export function PlansPage() {
  const [selected, setSelected] = useState<PlanId>("professional");

  const mutation = useMutation({
    mutationFn: async (plan: PlanId) =>
      adminApi.checkout({
        plan,
        success_url: `${window.location.origin}/billing/success?plan=${plan}`,
        cancel_url: `${window.location.origin}/pricing?checkout=canceled`,
      }),
    onSuccess: (res) => {
      if (res.checkout_url) window.location.href = res.checkout_url;
    },
  });

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.status === 404
        ? "Billing is temporarily unavailable. Please try again in a few minutes, or contact support if this continues."
        : mutation.error.detail
      : mutation.error
        ? "Unable to start checkout. Please try again."
        : null;

  return (
    <div className="marketing-root relative min-h-full">
      <div className="mkt-atmosphere pointer-events-none fixed inset-0 opacity-30" aria-hidden />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(56rem 32rem at 50% -5%, rgba(45,212,191,0.14), transparent 55%)",
        }}
      />

      <header className="relative z-10 border-b border-white/10 bg-marketing-ink/80 backdrop-blur-md">
        <div className="mkt-shell flex h-[5rem] items-center justify-between">
          <Link to="/" className="flex items-center gap-3.5">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-teal-400/15 ring-1 ring-teal-400/35">
              <ShieldCheck className="h-6 w-6 text-teal-400" />
            </div>
            <span className="font-display text-2xl font-bold text-white">AI-SPM</span>
          </Link>
          <p className="hidden text-base font-medium text-slate-400 sm:block">
            Complete checkout to unlock your security console
          </p>
        </div>
      </header>

      <main className="relative z-10 mkt-shell py-14 sm:py-16">
        <div className="max-w-3xl">
          <p className="mkt-eyebrow">Choose your plan</p>
          <h1 className="mkt-h1 mt-4">Unlock your AI-SPM security console</h1>
          <p className="mkt-lead mt-5 text-slate-200">
            Capacity is priced by protected endpoints (agents), not seats. Your subscription must
            be active before the admin console opens.
          </p>
        </div>

        {errorMessage && (
          <div className="mt-8 flex max-w-3xl items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-5 py-4 text-[17px] text-rose-200">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          {PLANS.map((plan) => {
            const active = selected === plan.id;
            return (
              <button
                key={plan.id}
                type="button"
                onClick={() => setSelected(plan.id)}
                className={cn(
                  "mkt-panel relative p-8 text-left transition-all duration-200 sm:p-9",
                  active
                    ? "border-teal-400/50 ring-1 ring-teal-400/35 shadow-[0_0_48px_-16px_rgba(45,212,191,0.5)]"
                    : "hover:border-white/25",
                )}
              >
                {plan.highlight && !active && (
                  <span className="absolute right-7 top-7 rounded-full bg-teal-400/15 px-3 py-1 text-xs font-bold uppercase tracking-wider text-teal-300">
                    Popular
                  </span>
                )}
                {active && (
                  <span className="absolute right-7 top-7 grid h-8 w-8 place-items-center rounded-full bg-teal-400 text-marketing-ink">
                    <Check className="h-4 w-4" strokeWidth={3} />
                  </span>
                )}
                <p className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  {plan.audience}
                </p>
                <h2 className="mt-3 font-display text-4xl font-bold text-white">{plan.name}</h2>
                <p className="mt-3 text-lg text-slate-300">{plan.agents}</p>
                <p className="mt-7 font-display text-5xl font-bold text-teal-400">
                  {plan.price}
                  <span className="text-xl font-normal text-slate-500">/mo</span>
                </p>
                <ul className="mt-7 space-y-3.5">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-3 text-[17px] text-slate-200">
                      <Check className="mt-1 h-5 w-5 shrink-0 text-teal-400" />
                      {f}
                    </li>
                  ))}
                </ul>
              </button>
            );
          })}
        </div>

        <div className="mkt-panel mt-5 flex flex-col gap-5 p-7 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <div>
            <h3 className="font-display text-2xl font-semibold text-white">Enterprise</h3>
            <p className="mt-2 text-lg text-slate-400">
              Unlimited agents · $12,000/mo · custom SLA for large fleets
            </p>
          </div>
          <Link to="/contact-sales" className="mkt-btn-ghost shrink-0">
            Contact sales
            <ArrowRight className="h-5 w-5" />
          </Link>
        </div>

        <button
          type="button"
          onClick={() => mutation.mutate(selected)}
          className="mkt-btn-primary mt-10 w-full py-4 text-lg"
          disabled={mutation.isPending}
        >
          {mutation.isPending ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Starting checkout…
            </>
          ) : (
            <>
              Continue to checkout
              <ArrowRight className="h-5 w-5" />
            </>
          )}
        </button>

        <p className="mt-6 text-center text-lg text-slate-500">
          After payment succeeds you can open the console.{" "}
          <Link to="/pricing" className="font-medium text-teal-400 hover:text-teal-300">
            Compare all plans
          </Link>
        </p>
      </main>
    </div>
  );
}
