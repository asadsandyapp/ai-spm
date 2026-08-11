import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowUpRight, CreditCard, Loader2, Bot, Zap } from "lucide-react";
import { ApiError, adminApi } from "@/lib/api";
import { PageHeader, Spinner, ErrorState } from "@/components/ui/States";
import { titleCase } from "@/lib/utils";

export function BillingPage() {
  const billingQ = useQuery({
    queryKey: ["billing", "status"],
    queryFn: ({ signal }) => adminApi.billingStatus(signal),
  });

  const portalM = useMutation({
    mutationFn: () => adminApi.billingPortal(),
    onSuccess: (res) => {
      if (res.portal_url) window.location.href = res.portal_url;
    },
  });

  const data = billingQ.data;
  const usage = data?.usage;
  const entitlements = data?.entitlements as
    | { current_period_end?: string | null; max_agents_unlimited?: boolean }
    | undefined;
  const maxAgents = usage?.max_agents ?? 0;
  const agentsUsed = usage?.agent_count ?? 0;
  const promptsUsed = usage?.prompts_this_month ?? usage?.prompts_today ?? 0;
  const promptQuota = usage?.max_prompts_per_month ?? 0;
  const agentsUnlimited = Boolean(usage?.max_agents_unlimited);
  const promptsUnlimited = Boolean(usage?.prompts_unlimited);

  const agentPct =
    !agentsUnlimited && maxAgents > 0
      ? Math.min(100, Math.round((agentsUsed / maxAgents) * 100))
      : 0;
  const promptPct =
    !promptsUnlimited && promptQuota > 0
      ? Math.min(100, Math.round((promptsUsed / promptQuota) * 100))
      : 0;

  const portalError =
    portalM.error instanceof ApiError
      ? portalM.error.detail
      : portalM.error
        ? "Unable to open billing portal."
        : null;

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Billing & usage"
        description="Plan limits are based on protected endpoints (agents), not seats."
      />

      {billingQ.isLoading && <Spinner />}
      {billingQ.isError && (
        <ErrorState error={billingQ.error} onRetry={() => billingQ.refetch()} />
      )}

      {data && usage && (
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="card p-6 lg:col-span-2">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                  Current plan
                </p>
                <h2 className="mt-1 text-2xl font-semibold text-ink-900">
                  {titleCase(data.plan.replace(/_/g, " "))}
                </h2>
                <p className="mt-1 text-sm text-ink-500">
                  Status:{" "}
                  <span className="font-medium capitalize text-ink-700">{data.status}</span>
                  {entitlements?.current_period_end && (
                    <>
                      {" "}
                      · Renews{" "}
                      {new Date(entitlements.current_period_end).toLocaleDateString()}
                    </>
                  )}
                </p>
                {!data.console_access && (
                  <p className="mt-2 text-sm font-medium text-amber-700">
                    Complete checkout to unlock your AI-SPM security console.
                  </p>
                )}
              </div>
              <Link to="/onboarding/plans" className="btn-primary">
                Change plan
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>

            <div className="mt-8 grid gap-6 sm:grid-cols-2">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium text-ink-700">
                  <Bot className="h-4 w-4" />
                  Protected endpoints (agents)
                </div>
                <p className="mt-2 text-2xl font-semibold text-ink-900">
                  {agentsUsed}
                  <span className="text-base font-normal text-ink-500">
                    {" "}
                    / {agentsUnlimited ? "Unlimited" : maxAgents}
                  </span>
                </p>
                {!agentsUnlimited && (
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-ink-100">
                    <div
                      className="h-full rounded-full bg-brand-600 transition-all"
                      style={{ width: `${agentPct}%` }}
                    />
                  </div>
                )}
              </div>
              <div>
                <div className="flex items-center gap-2 text-sm font-medium text-ink-700">
                  <Zap className="h-4 w-4" />
                  Prompts this month
                </div>
                <p className="mt-2 text-2xl font-semibold text-ink-900">
                  {promptsUsed.toLocaleString()}
                  <span className="text-base font-normal text-ink-500">
                    {" "}
                    / {promptsUnlimited ? "Unlimited" : promptQuota.toLocaleString()}
                  </span>
                </p>
                {!promptsUnlimited && (
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-ink-100">
                    <div
                      className="h-full rounded-full bg-brand-600 transition-all"
                      style={{ width: `${promptPct}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center gap-2 text-sm font-semibold text-ink-900">
              <CreditCard className="h-4 w-4" />
              Payment & invoices
            </div>
            <p className="mt-2 text-sm text-ink-500">
              Update payment method, download invoices, or cancel via the Stripe customer portal.
            </p>
            {portalError && (
              <p className="mt-3 text-sm text-rose-600">{portalError}</p>
            )}
            <button
              type="button"
              className="btn-primary mt-6 w-full"
              disabled={portalM.isPending}
              onClick={() => portalM.mutate()}
            >
              {portalM.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Manage subscription"
              )}
            </button>
            <Link
              to="/contact-sales"
              className="mt-3 block text-center text-sm font-medium text-brand-600 hover:text-brand-700"
            >
              Need Enterprise? Contact sales →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
