import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  ChevronRight,
  PauseCircle,
  RefreshCw,
  Search,
} from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MetricCard } from "@/components/ui/MetricCard";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { useTenants, queryKeys } from "@/hooks/queries";
import { platformApi, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { hasPermission } from "@/lib/jwt";
import { cn, formatDateTime } from "@/lib/utils";
import type { TenantListItem } from "@/types/api";

const PLAN_STYLES: Record<string, string> = {
  starter: "bg-ink-100 text-ink-600 ring-1 ring-ink-300",
  professional: "bg-brand-50 text-brand-700 ring-1 ring-brand-600/20",
  enterprise: "bg-teal-50 text-teal-800 ring-1 ring-teal-600/20",
  free: "bg-ink-100 text-ink-600 ring-1 ring-ink-300",
  pro: "bg-brand-50 text-brand-700 ring-1 ring-brand-600/20",
};

export function TenantsPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useTenants();
  const queryClient = useQueryClient();
  const permissions = useAuthStore((s) => s.permissions());
  const [query, setQuery] = useState("");

  const canSuspend = hasPermission(permissions, "tenants:suspend");
  const canActivate = hasPermission(permissions, "tenants:activate");

  const suspendMutation = useMutation({
    mutationFn: (orgId: string) =>
      platformApi.suspend(orgId, "Suspended from platform console"),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.tenants }),
  });

  const activateMutation = useMutation({
    mutationFn: (orgId: string) => platformApi.activate(orgId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.tenants }),
  });

  const tenants = data ?? [];

  const filtered = useMemo(
    () =>
      tenants.filter(
        (t) =>
          !query ||
          t.name.toLowerCase().includes(query.toLowerCase()) ||
          t.slug.toLowerCase().includes(query.toLowerCase()),
      ),
    [tenants, query],
  );

  const stats = useMemo(() => {
    return {
      total: tenants.length,
      active: tenants.filter((t) => t.status === "active").length,
      suspended: tenants.filter((t) => t.status === "suspended").length,
      agents: tenants.reduce((sum, t) => sum + (t.agent_count ?? 0), 0),
      paid: tenants.filter((t) =>
        ["active", "past_due"].includes(t.subscription_status ?? ""),
      ).length,
    };
  }, [tenants]);

  const pendingId =
    suspendMutation.isPending
      ? suspendMutation.variables
      : activateMutation.isPending
        ? activateMutation.variables
        : null;

  const actionError = (suspendMutation.error ?? activateMutation.error) as
    | unknown
    | null;

  const renderActions = (t: TenantListItem) => {
    const busy = pendingId === t.id;
    return (
      <div className="flex items-center justify-end gap-1">
        {t.status === "active" && canSuspend ? (
          <button
            className="btn-ghost px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50"
            disabled={busy}
            onClick={() => suspendMutation.mutate(t.id)}
          >
            <PauseCircle className="h-3.5 w-3.5" />
            {busy ? "Suspending…" : "Suspend"}
          </button>
        ) : null}
        {t.status !== "active" && canActivate ? (
          <button
            className="btn-ghost px-3 py-1.5 text-xs text-emerald-600 hover:bg-emerald-50"
            disabled={busy}
            onClick={() => activateMutation.mutate(t.id)}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            {busy ? "Activating…" : "Activate"}
          </button>
        ) : null}
        <Link
          to={`/platform/tenants/${t.id}`}
          className="btn-ghost px-3 py-1.5 text-xs text-ink-700"
        >
          Manage
          <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    );
  };

  return (
    <>
      <PageHeader
        title="Tenant Management"
        description="Provision, monitor subscriptions, and manage every organization on the AI-SPM platform."
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

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total Tenants"
          value={isLoading ? "—" : stats.total}
          icon={Building2}
          accent="brand"
          loading={isLoading}
        />
        <MetricCard
          label="Active orgs"
          value={isLoading ? "—" : stats.active}
          icon={CheckCircle2}
          accent="emerald"
          loading={isLoading}
        />
        <MetricCard
          label="Paid subscriptions"
          value={isLoading ? "—" : stats.paid}
          icon={CheckCircle2}
          accent="violet"
          loading={isLoading}
        />
        <MetricCard
          label="Total Agents"
          value={isLoading ? "—" : stats.agents}
          icon={Building2}
          accent={stats.suspended > 0 ? "rose" : "emerald"}
          loading={isLoading}
        />
      </div>

      {actionError && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {actionError instanceof ApiError
            ? actionError.detail
            : "Action failed. Please try again."}
        </div>
      )}

      <div className="mb-4 relative w-full max-w-xs">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
        <input
          className="input pl-9"
          placeholder="Search tenants…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <Spinner label="Loading tenants…" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Building2}
            title={tenants.length === 0 ? "No tenants yet" : "No matches"}
            description={
              tenants.length === 0
                ? "Tenants appear here as organizations sign up and are provisioned on the platform."
                : "Try a different search term."
            }
          />
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-200 bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
                  <th className="px-5 py-3 font-semibold">Organization</th>
                  <th className="px-5 py-3 font-semibold">Plan</th>
                  <th className="px-5 py-3 font-semibold">Subscription</th>
                  <th className="px-5 py-3 font-semibold whitespace-nowrap">
                    Period end
                  </th>
                  <th className="px-5 py-3 font-semibold">Org status</th>
                  <th className="px-5 py-3 font-semibold">Agents</th>
                  <th className="px-5 py-3 font-semibold whitespace-nowrap">
                    Created
                  </th>
                  <th className="px-5 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {filtered.map((t) => (
                  <tr key={t.id} className="transition-colors hover:bg-ink-50/60">
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/platform/tenants/${t.id}`}
                        className="flex items-center gap-3 hover:opacity-90"
                      >
                        <div className="grid h-9 w-9 place-items-center rounded-lg bg-ink-900 text-xs font-semibold text-white">
                          {t.name.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink-900">
                            {t.name}
                          </p>
                          <p className="truncate font-mono text-xs text-ink-400">
                            {t.slug}
                          </p>
                        </div>
                      </Link>
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={cn(
                          "badge capitalize",
                          PLAN_STYLES[t.plan] ?? PLAN_STYLES.free,
                        )}
                      >
                        {t.plan}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge
                        status={t.subscription_status ?? "incomplete"}
                      />
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-600">
                      {formatDateTime(
                        t.current_period_end ?? t.trial_ends_at ?? null,
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="px-5 py-3.5 font-medium text-ink-700">
                      {t.agent_count}
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-600">
                      {formatDateTime(t.created_at)}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {renderActions(t)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
