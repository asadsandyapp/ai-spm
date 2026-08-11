import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  CreditCard,
  PauseCircle,
  RefreshCw,
} from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { useTenant, queryKeys } from "@/hooks/queries";
import { platformApi, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { hasPermission } from "@/lib/jwt";
import { cn, formatDateTime, titleCase } from "@/lib/utils";

const PLAN_STYLES: Record<string, string> = {
  starter: "bg-ink-100 text-ink-600 ring-1 ring-ink-300",
  professional: "bg-brand-50 text-brand-700 ring-1 ring-brand-600/20",
  enterprise: "bg-teal-50 text-teal-800 ring-1 ring-teal-600/20",
};

const PLANS = ["starter", "professional", "enterprise"] as const;
const SUB_STATUSES = [
  "active",
  "trialing",
  "past_due",
  "suspended",
  "canceled",
  "incomplete",
] as const;

function Field({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
        {label}
      </p>
      <p className="mt-1 text-sm font-medium text-ink-900">{value ?? "—"}</p>
    </div>
  );
}

export function TenantDetailPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { data, isLoading, isError, error, refetch, isFetching } =
    useTenant(orgId);
  const qc = useQueryClient();
  const permissions = useAuthStore((s) => s.permissions());
  const canBilling = hasPermission(permissions, "billing:write");
  const canSuspend = hasPermission(permissions, "tenants:suspend");
  const canActivate = hasPermission(permissions, "tenants:activate");

  const [plan, setPlan] = useState("starter");
  const [subStatus, setSubStatus] = useState("active");
  const [maxAgents, setMaxAgents] = useState("");
  const [maxPrompts, setMaxPrompts] = useState("");
  const [formMsg, setFormMsg] = useState<string | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setPlan(data.plan || "starter");
    setSubStatus(data.subscription_status || "active");
    setMaxAgents(
      data.max_agents != null && data.max_agents >= 0
        ? String(data.max_agents)
        : "",
    );
    setMaxPrompts(
      data.max_prompts_per_day != null
        ? String(data.max_prompts_per_day)
        : "",
    );
  }, [data]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.tenants });
    if (orgId) {
      void qc.invalidateQueries({ queryKey: queryKeys.tenant(orgId) });
    }
  };

  const suspendM = useMutation({
    mutationFn: () =>
      platformApi.suspend(orgId!, "Suspended from platform console"),
    onSuccess: invalidate,
  });

  const activateM = useMutation({
    mutationFn: () => platformApi.activate(orgId!),
    onSuccess: invalidate,
  });

  const assignM = useMutation({
    mutationFn: () =>
      platformApi.assignPlan(orgId!, {
        plan,
        status: subStatus,
        activate: subStatus === "active",
        max_agents: maxAgents === "" ? undefined : Number(maxAgents),
        max_prompts_per_day:
          maxPrompts === "" ? undefined : Number(maxPrompts),
      }),
    onSuccess: () => {
      setFormErr(null);
      setFormMsg("Subscription updated.");
      invalidate();
    },
    onError: (err) => {
      setFormMsg(null);
      setFormErr(
        err instanceof ApiError ? err.detail : "Unable to update subscription.",
      );
    },
  });

  const actionError = suspendM.error ?? activateM.error;

  const periodLabel = useMemo(() => {
    if (!data) return "—";
    if (data.trial_ends_at) {
      return `Trial ends ${formatDateTime(data.trial_ends_at)}`;
    }
    if (data.current_period_end) {
      return data.cancel_at_period_end
        ? `Cancels ${formatDateTime(data.current_period_end)}`
        : `Renews ${formatDateTime(data.current_period_end)}`;
    }
    if (data.expires_at) return `Expires ${formatDateTime(data.expires_at)}`;
    return "No period end on file";
  }, [data]);

  if (!orgId) {
    return <ErrorState error={new Error("Missing tenant id")} />;
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-4">
        <Link
          to="/platform/tenants"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-500 hover:text-ink-800"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to tenants
        </Link>
      </div>

      <PageHeader
        title={data?.name ?? "Tenant"}
        description={
          data
            ? `${data.slug} · Created ${formatDateTime(data.created_at)}`
            : "Subscription, usage, and lifecycle controls."
        }
        actions={
          <button
            className="btn-ghost"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            Refresh
          </button>
        }
      />

      {isLoading && <Spinner />}
      {isError && <ErrorState error={error} onRetry={() => refetch()} />}

      {actionError ? (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {actionError instanceof ApiError
            ? actionError.detail
            : "Action failed."}
        </div>
      ) : null}

      {data && (
        <div className="mt-6 space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="card p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                Organization
              </p>
              <div className="mt-2 flex items-center gap-2">
                <StatusBadge status={data.status} />
              </div>
            </div>
            <div className="card p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                Plan
              </p>
              <span
                className={cn(
                  "badge mt-2 capitalize",
                  PLAN_STYLES[data.plan] ?? PLAN_STYLES.starter,
                )}
              >
                {data.plan}
              </span>
            </div>
            <div className="card p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                Subscription
              </p>
              <div className="mt-2">
                <StatusBadge
                  status={data.subscription_status ?? "incomplete"}
                />
              </div>
            </div>
            <div className="card p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                Billing period
              </p>
              <p className="mt-2 text-sm font-medium text-ink-800">
                {periodLabel}
              </p>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="card space-y-5 p-6 lg:col-span-2">
              <div className="flex items-center gap-2">
                <CreditCard className="h-5 w-5 text-brand-600" />
                <h2 className="text-lg font-semibold text-ink-900">
                  Subscription & payment
                </h2>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Subscription status"
                  value={titleCase(
                    (data.subscription_status ?? "—").replace(/_/g, " "),
                  )}
                />
                <Field
                  label="Billing interval"
                  value={titleCase(data.billing_interval ?? "month")}
                />
                <Field
                  label="Current period end"
                  value={formatDateTime(data.current_period_end)}
                />
                <Field
                  label="Trial ends"
                  value={formatDateTime(data.trial_ends_at)}
                />
                <Field
                  label="Expires"
                  value={formatDateTime(data.expires_at)}
                />
                <Field
                  label="Past due since"
                  value={formatDateTime(data.past_due_since)}
                />
                <Field
                  label="Cancel at period end"
                  value={data.cancel_at_period_end ? "Yes" : "No"}
                />
                <Field
                  label="Stripe customer"
                  value={
                    data.stripe_customer_id ??
                    (data.has_stripe_customer ? "Linked" : "Not linked")
                  }
                />
                <Field
                  label="Stripe subscription"
                  value={data.stripe_subscription_id ?? "—"}
                />
                <Field
                  label="Onboarding"
                  value={
                    data.onboarding_step
                      ? titleCase(data.onboarding_step.replace(/_/g, " "))
                      : "—"
                  }
                />
              </div>
            </div>

            <div className="card space-y-5 p-6">
              <h2 className="text-lg font-semibold text-ink-900">Usage</h2>
              <div className="space-y-4">
                <Field
                  label="Agents"
                  value={`${data.agent_count} / ${
                    data.max_agents == null || data.max_agents < 0
                      ? "Unlimited"
                      : data.max_agents
                  }`}
                />
                <Field label="Prompts today" value={data.prompts_today} />
                <Field
                  label="Daily prompt limit"
                  value={
                    data.max_prompts_per_day < 0
                      ? "Unlimited"
                      : data.max_prompts_per_day
                  }
                />
                {data.max_prompts_per_month != null && (
                  <Field
                    label="Monthly prompt limit"
                    value={
                      data.max_prompts_per_month < 0
                        ? "Unlimited"
                        : data.max_prompts_per_month
                    }
                  />
                )}
                {data.audit_retention_days != null && (
                  <Field
                    label="Audit retention (days)"
                    value={data.audit_retention_days}
                  />
                )}
              </div>

              <div className="flex flex-wrap gap-2 border-t border-ink-100 pt-4">
                {data.status === "active" && canSuspend && (
                  <button
                    className="btn-ghost px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50"
                    disabled={suspendM.isPending}
                    onClick={() => suspendM.mutate()}
                  >
                    <PauseCircle className="h-3.5 w-3.5" />
                    {suspendM.isPending ? "Suspending…" : "Suspend tenant"}
                  </button>
                )}
                {data.status !== "active" && canActivate && (
                  <button
                    className="btn-ghost px-3 py-1.5 text-xs text-emerald-600 hover:bg-emerald-50"
                    disabled={activateM.isPending}
                    onClick={() => activateM.mutate()}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {activateM.isPending ? "Activating…" : "Activate tenant"}
                  </button>
                )}
              </div>
            </div>
          </div>

          {canBilling && (
            <form
              className="card p-6"
              onSubmit={(e) => {
                e.preventDefault();
                setFormMsg(null);
                setFormErr(null);
                assignM.mutate();
              }}
            >
              <h2 className="text-lg font-semibold text-ink-900">
                Manage subscription
              </h2>
              <p className="mt-1 text-sm text-ink-500">
                Assign plan and agent/prompt quota overrides. Limits are based
                on protected endpoints (agents), not seats.
              </p>
              <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <label className="label" htmlFor="plan">
                    Plan
                  </label>
                  <select
                    id="plan"
                    className="input"
                    value={plan}
                    onChange={(e) => setPlan(e.target.value)}
                  >
                    {PLANS.map((p) => (
                      <option key={p} value={p}>
                        {titleCase(p)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="sub-status">
                    Subscription status
                  </label>
                  <select
                    id="sub-status"
                    className="input"
                    value={subStatus}
                    onChange={(e) => setSubStatus(e.target.value)}
                  >
                    {SUB_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {titleCase(s.replace(/_/g, " "))}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="max-agents">
                    Max agents
                  </label>
                  <input
                    id="max-agents"
                    className="input"
                    type="number"
                    min={0}
                    placeholder="Keep current"
                    value={maxAgents}
                    onChange={(e) => setMaxAgents(e.target.value)}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="max-prompts">
                    Max prompts / day
                  </label>
                  <input
                    id="max-prompts"
                    className="input"
                    type="number"
                    min={0}
                    placeholder="Keep current"
                    value={maxPrompts}
                    onChange={(e) => setMaxPrompts(e.target.value)}
                  />
                </div>
              </div>
              {formErr && (
                <p className="mt-3 text-sm text-rose-600">{formErr}</p>
              )}
              {formMsg && (
                <p className="mt-3 text-sm text-emerald-700">{formMsg}</p>
              )}
              <button
                type="submit"
                className="btn-primary mt-5"
                disabled={assignM.isPending}
              >
                {assignM.isPending ? "Saving…" : "Save subscription"}
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
