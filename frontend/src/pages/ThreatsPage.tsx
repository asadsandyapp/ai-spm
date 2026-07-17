import { useMemo, useState } from "react";
import { RefreshCw, ShieldAlert } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { useThreats } from "@/hooks/queries";
import { useDashboardWebSocket } from "@/hooks/useDashboardWebSocket";
import { cn, formatDateTime, providerLabel } from "@/lib/utils";

const LIMITS = [25, 50, 100];

export function ThreatsPage() {
  useDashboardWebSocket();
  const [limit, setLimit] = useState(50);
  const { data, isLoading, isError, error, refetch, isFetching } =
    useThreats(limit);

  const threats = data ?? [];

  const severityCounts = useMemo(() => {
    const counts = { high: 0, medium: 0, other: 0 };
    for (const t of threats) {
      const s = t.severity.toLowerCase();
      if (s === "high") counts.high++;
      else if (s === "medium") counts.medium++;
      else counts.other++;
    }
    return counts;
  }, [threats]);

  return (
    <>
      <PageHeader
        title="Threat Feed"
        description="Real-time stream of blocked prompts, policy violations, and detected threats."
        actions={
          <button
            className="btn-ghost"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw
              className={cn("h-4 w-4", isFetching && "animate-spin")}
            />
            Refresh
          </button>
        }
      />

      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <div className="card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
            High Severity
          </p>
          <p className="mt-1 text-2xl font-semibold text-rose-600">
            {severityCounts.high}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
            Medium Severity
          </p>
          <p className="mt-1 text-2xl font-semibold text-amber-600">
            {severityCounts.medium}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
            Total Events
          </p>
          <p className="mt-1 text-2xl font-semibold text-ink-900">
            {threats.length}
          </p>
        </div>
      </div>

      <div className="mb-4 flex justify-end">
        <div className="inline-flex items-center gap-2 text-sm text-ink-500">
          <span>Show</span>
          <div className="inline-flex rounded-lg border border-ink-200 bg-white p-1">
            {LIMITS.map((l) => (
              <button
                key={l}
                onClick={() => setLimit(l)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-sm font-medium transition-colors",
                  limit === l
                    ? "bg-ink-900 text-white"
                    : "text-ink-500 hover:text-ink-900",
                )}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <Spinner label="Loading threat feed…" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : threats.length === 0 ? (
          <EmptyState
            icon={ShieldAlert}
            title="No threats detected"
            description="Threat events will appear here when prompts are blocked or policy violations occur."
          />
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-200 bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
                  <th className="px-5 py-3 font-semibold">Severity</th>
                  <th className="px-5 py-3 font-semibold">Event Type</th>
                  <th className="px-5 py-3 font-semibold">Details</th>
                  <th className="px-5 py-3 font-semibold">AI Agent</th>
                  <th className="px-5 py-3 font-semibold">Device</th>
                  <th className="px-5 py-3 font-semibold whitespace-nowrap">
                    Timestamp
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {threats.map((t) => (
                  <tr key={t.id} className="transition-colors hover:bg-ink-50/60">
                    <td className="px-5 py-3.5">
                      <StatusBadge status={t.severity} />
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={t.event_type} />
                    </td>
                    <td className="px-5 py-3.5 max-w-md">
                      <p className="truncate text-ink-700">
                        {t.masked_content || (
                          <span className="text-ink-400">No content captured</span>
                        )}
                      </p>
                    </td>
                    <td className="px-5 py-3.5">
                      {providerLabel(t.provider) ? (
                        <span className="text-ink-700">
                          {providerLabel(t.provider)}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      {t.hostname ? (
                        <span className="text-ink-700">{t.hostname}</span>
                      ) : t.agent_id ? (
                        <span className="font-mono text-xs text-ink-500">
                          {t.agent_id.slice(0, 8)}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-600">
                      {formatDateTime(t.created_at)}
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
