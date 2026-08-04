import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Info,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import {
  applyFeedFilters,
  collectFeedFilterOptions,
  EMPTY_FEED_FILTERS,
  FeedFilters,
  type FeedFilterState,
} from "@/components/ui/FeedFilters";
import { MetricCard } from "@/components/ui/MetricCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DetectedCell, PromptCell } from "@/components/ui/TableCells";
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
  const [filters, setFilters] = useState<FeedFilterState>(EMPTY_FEED_FILTERS);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set());
  const { data, isLoading, isError, error, refetch, isFetching } =
    useThreats(limit);

  function toggleRowExpand(id: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const threats = data ?? [];

  const severityCounts = useMemo(() => {
    const counts = { high: 0, medium: 0, low: 0 };
    for (const t of threats) {
      const s = t.severity.toLowerCase();
      if (s === "high") counts.high++;
      else if (s === "medium") counts.medium++;
      else if (s === "low") counts.low++;
    }
    return counts;
  }, [threats]);

  const options = useMemo(() => collectFeedFilterOptions(threats), [threats]);

  const filtered = useMemo(
    () => applyFeedFilters(threats, filters),
    [threats, filters],
  );

  const limitControl = (
    <div className="inline-flex items-center gap-2 text-sm text-ink-500">
      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-400">
        Rows
      </span>
      <div className="inline-flex rounded-lg bg-white p-0.5 ring-1 ring-ink-200">
        {LIMITS.map((l) => (
          <button
            key={l}
            type="button"
            onClick={() => setLimit(l)}
            className={cn(
              "rounded-md px-2.5 py-1 text-sm font-semibold tabular-nums transition-colors",
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
  );

  return (
    <>
      <PageHeader
        title="Threat Feed"
        description="Security-relevant events with original and masked prompts for investigation. Clean traffic stays in Audit Log only."
        actions={
          <button
            className="btn-ghost ring-1 ring-ink-200"
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

      <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <button
          type="button"
          className={cn(
            "text-left transition-shadow",
            filters.severity === "high" && "rounded-xl ring-2 ring-rose-400/50",
          )}
          onClick={() => setFilters((f) => ({ ...f, severity: "high" }))}
        >
          <MetricCard
            label="High severity"
            value={severityCounts.high}
            icon={AlertTriangle}
            accent="rose"
            hint="Critical PII, threats, fail-closed"
          />
        </button>
        <button
          type="button"
          className={cn(
            "text-left transition-shadow",
            filters.severity === "medium" &&
              "rounded-xl ring-2 ring-amber-400/50",
          )}
          onClick={() => setFilters((f) => ({ ...f, severity: "medium" }))}
        >
          <MetricCard
            label="Medium severity"
            value={severityCounts.medium}
            icon={ShieldAlert}
            accent="amber"
            hint="Standard PII & policy findings"
          />
        </button>
        <button
          type="button"
          className={cn(
            "text-left transition-shadow",
            filters.severity === "low" && "rounded-xl ring-2 ring-brand-400/50",
          )}
          onClick={() => setFilters((f) => ({ ...f, severity: "low" }))}
        >
          <MetricCard
            label="Low severity"
            value={severityCounts.low}
            icon={Info}
            accent="brand"
            hint="Soft / contextual attributes"
          />
        </button>
        <button
          type="button"
          className={cn(
            "text-left transition-shadow",
            filters.severity === "all" && "rounded-xl ring-2 ring-ink-400/40",
          )}
          onClick={() => setFilters((f) => ({ ...f, severity: "all" }))}
        >
          <MetricCard
            label="Total events"
            value={threats.length}
            icon={ShieldCheck}
            accent="emerald"
            hint="Loaded in this view"
          />
        </button>
      </div>

      <FeedFilters
        filters={filters}
        onChange={setFilters}
        options={options}
        showSeverity
        severityCounts={{
          high: severityCounts.high,
          medium: severityCounts.medium,
          low: severityCounts.low,
          total: threats.length,
        }}
        resultCount={filtered.length}
        totalCount={threats.length}
        searchPlaceholder="Search threats by prompt text, device, or entity…"
        limitControl={limitControl}
      />

      <div className="overflow-hidden rounded-2xl border border-ink-200/80 bg-white shadow-elevated">
        {isLoading ? (
          <Spinner label="Loading threat feed…" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : threats.length === 0 ? (
          <EmptyState
            icon={ShieldAlert}
            title="No threats detected"
            description="PII detections and security blocks will appear here. Clean prompts are in Audit Log only."
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={ShieldAlert}
            title="No matching threats"
            description="Try clearing filters or broadening your search."
          />
        ) : (
          <div className="w-full">
            <table className="w-full table-fixed text-left text-sm">
              <colgroup>
                <col className="w-[7%]" />
                <col className="w-[10%]" />
                <col className="w-[22%]" />
                <col className="w-[22%]" />
                <col className="w-[15%]" />
                <col className="w-[7%]" />
                <col className="w-[9%]" />
                <col className="w-[8%]" />
              </colgroup>
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-ink-200 bg-ink-50/95 text-[11px] uppercase tracking-[0.08em] text-ink-500 backdrop-blur">
                  <th className="px-3 py-3.5 font-semibold">Severity</th>
                  <th className="px-3 py-3.5 font-semibold">Event</th>
                  <th className="px-3 py-3.5 font-semibold">Original</th>
                  <th className="px-3 py-3.5 font-semibold">Masked</th>
                  <th className="px-3 py-3.5 font-semibold">Detected</th>
                  <th className="px-3 py-3.5 font-semibold">Agent</th>
                  <th className="px-3 py-3.5 font-semibold">Device</th>
                  <th className="px-3 py-3.5 font-semibold">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {filtered.map((t) => {
                  const expanded = expandedRows.has(t.id);
                  const onToggleExpand = () => toggleRowExpand(t.id);
                  return (
                  <tr
                    key={t.id}
                    className="align-top transition-colors hover:bg-brand-50/30"
                  >
                    <td className="px-3 py-3.5">
                      <StatusBadge status={t.severity} />
                    </td>
                    <td className="px-3 py-3.5">
                      <StatusBadge status={t.event_type} />
                    </td>
                    <td className="px-3 py-3.5">
                      <PromptCell
                        text={t.original_content}
                        expanded={expanded}
                        onToggleExpand={onToggleExpand}
                      />
                    </td>
                    <td className="px-3 py-3.5">
                      <PromptCell
                        text={t.masked_content}
                        empty="No content captured"
                        expanded={expanded}
                        onToggleExpand={onToggleExpand}
                      />
                    </td>
                    <td className="px-3 py-3.5">
                      <DetectedCell
                        entities={t.pii_entities}
                        hitCount={t.pii_hit_count}
                        expanded={expanded}
                        onToggleExpand={onToggleExpand}
                      />
                    </td>
                    <td className="px-3 py-3.5">
                      {providerLabel(t.provider) ? (
                        <span className="break-words text-[13px] font-medium text-ink-800">
                          {providerLabel(t.provider)}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      {t.hostname ? (
                        <span className="break-all text-[12px] text-ink-700">
                          {t.hostname}
                        </span>
                      ) : t.agent_id ? (
                        <span className="break-all font-mono text-xs text-ink-500">
                          {t.agent_id}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      <span className="break-words text-[12px] tabular-nums text-ink-600">
                        {formatDateTime(t.created_at)}
                      </span>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
