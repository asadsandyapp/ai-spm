import { useMemo, useState } from "react";
import { Download, FileClock, RefreshCw } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { useAudit, useExportAudit } from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { cn, formatDateTime, providerLabel, titleCase } from "@/lib/utils";

const LIMITS = [50, 100, 200];
const EXPORT_DAYS = [30, 90, 180, 365];

export function AuditPage() {
  const [limit, setLimit] = useState(50);
  const { data, isLoading, isError, error, refetch, isFetching } =
    useAudit(limit);
  const exportM = useExportAudit();
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [exportDays, setExportDays] = useState(90);
  const [exportError, setExportError] = useState<string | null>(null);

  const events = data ?? [];

  const eventTypes = useMemo(
    () => Array.from(new Set(events.map((e) => e.event_type))).sort(),
    [events],
  );

  const filtered = useMemo(
    () =>
      typeFilter === "all"
        ? events
        : events.filter((e) => e.event_type === typeFilter),
    [events, typeFilter],
  );

  async function handleExport() {
    setExportError(null);
    try {
      const blob = await exportM.mutateAsync(exportDays);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_export_${exportDays}d.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(
        err instanceof ApiError ? err.detail : "Export failed.",
      );
    }
  }

  return (
    <>
      <PageHeader
        title="Audit Log"
        description="Immutable record of AI prompts, policy decisions, and security events."
        actions={
          <div className="flex items-center gap-2">
            <select
              className="input max-w-[120px] py-2"
              value={exportDays}
              onChange={(e) => setExportDays(Number(e.target.value))}
              aria-label="Export window"
            >
              {EXPORT_DAYS.map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
            <button
              className="btn-primary"
              onClick={handleExport}
              disabled={exportM.isPending}
            >
              <Download className="h-4 w-4" />
              {exportM.isPending ? "Exporting…" : "Export CSV"}
            </button>
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
          </div>
        }
      />

      {exportError && (
        <p className="mb-4 text-sm text-rose-600" role="alert">
          {exportError}
        </p>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          className="input max-w-[220px]"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="all">All event types</option>
          {eventTypes.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </select>

        <div className="ml-auto inline-flex items-center gap-2 text-sm text-ink-500">
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
          <Spinner label="Loading audit events…" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={FileClock}
            title="No audit events"
            description="Audit events will appear here as agents submit prompts and policies are evaluated."
          />
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-200 bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
                  <th className="px-5 py-3 font-semibold">Event</th>
                  <th className="px-5 py-3 font-semibold">Details</th>
                  <th className="px-5 py-3 font-semibold">AI Agent</th>
                  <th className="px-5 py-3 font-semibold">Device</th>
                  <th className="px-5 py-3 font-semibold whitespace-nowrap">
                    Timestamp
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {filtered.map((e) => (
                  <tr key={e.id} className="transition-colors hover:bg-ink-50/60">
                    <td className="px-5 py-3.5">
                      <StatusBadge status={e.event_type} />
                    </td>
                    <td className="px-5 py-3.5 max-w-md">
                      <p className="truncate text-ink-700">
                        {e.masked_content || (
                          <span className="text-ink-400">
                            No content captured
                          </span>
                        )}
                      </p>
                    </td>
                    <td className="px-5 py-3.5">
                      {providerLabel(e.provider) ? (
                        <span className="text-ink-700">
                          {providerLabel(e.provider)}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      {e.hostname ? (
                        <span className="text-ink-700">{e.hostname}</span>
                      ) : e.agent_id ? (
                        <span className="font-mono text-xs text-ink-500">
                          {e.agent_id.slice(0, 8)}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-600">
                      {formatDateTime(e.created_at)}
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
