import { useMemo, useState } from "react";
import { Download, FileClock, RefreshCw } from "lucide-react";
import {
  applyFeedFilters,
  collectFeedFilterOptions,
  EMPTY_FEED_FILTERS,
  FeedFilters,
  type FeedFilterState,
} from "@/components/ui/FeedFilters";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DetectedCell, PromptCell } from "@/components/ui/TableCells";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { useAudit, useExportAudit } from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { cn, formatDateTime, providerLabel } from "@/lib/utils";

const LIMITS = [50, 100, 200];
const EXPORT_DAYS = [30, 90, 180, 365];

export function AuditPage() {
  const [limit, setLimit] = useState(50);
  const [filters, setFilters] = useState<FeedFilterState>(EMPTY_FEED_FILTERS);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set());
  const { data, isLoading, isError, error, refetch, isFetching } =
    useAudit(limit);
  const exportM = useExportAudit();
  const [exportDays, setExportDays] = useState(90);
  const [exportError, setExportError] = useState<string | null>(null);

  function toggleRowExpand(id: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const events = data ?? [];
  const options = useMemo(() => collectFeedFilterOptions(events), [events]);
  const filtered = useMemo(
    () => applyFeedFilters(events, filters),
    [events, filters],
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
        title="Audit Log"
        description="Complete prompt history with original and masked content for compliance review across ChatGPT, Claude, and Gemini."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-2 rounded-xl bg-white p-1 ring-1 ring-ink-200">
              <label className="pl-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-400">
                Export
              </label>
              <select
                className="rounded-lg border-0 bg-transparent py-1.5 pr-8 text-sm font-medium text-ink-800 focus:outline-none focus:ring-0"
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
            </div>
            <button
              className="btn-primary"
              onClick={handleExport}
              disabled={exportM.isPending}
            >
              <Download className="h-4 w-4" />
              {exportM.isPending ? "Exporting…" : "Export CSV"}
            </button>
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
          </div>
        }
      />

      {exportError && (
        <p className="mb-4 text-sm text-rose-600" role="alert">
          {exportError}
        </p>
      )}

      <FeedFilters
        filters={filters}
        onChange={setFilters}
        options={options}
        resultCount={filtered.length}
        totalCount={events.length}
        searchPlaceholder="Search audit by prompt text, device, or entity…"
        limitControl={limitControl}
      />

      <div className="overflow-hidden rounded-2xl border border-ink-200/80 bg-white shadow-elevated">
        {isLoading ? (
          <Spinner label="Loading audit events…" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : events.length === 0 ? (
          <EmptyState
            icon={FileClock}
            title="No audit events"
            description="Audit events will appear here as agents submit prompts and policies are evaluated."
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={FileClock}
            title="No matching audit events"
            description="Try clearing filters or broadening your search."
          />
        ) : (
          <div className="w-full">
            <table className="w-full table-fixed text-left text-sm">
              <colgroup>
                <col className="w-[10%]" />
                <col className="w-[24%]" />
                <col className="w-[24%]" />
                <col className="w-[14%]" />
                <col className="w-[8%]" />
                <col className="w-[10%]" />
                <col className="w-[10%]" />
              </colgroup>
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-ink-200 bg-ink-50/95 text-[11px] uppercase tracking-[0.08em] text-ink-500 backdrop-blur">
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
                {filtered.map((e) => {
                  const expanded = expandedRows.has(e.id);
                  const onToggleExpand = () => toggleRowExpand(e.id);
                  return (
                  <tr
                    key={e.id}
                    className="align-top transition-colors hover:bg-brand-50/30"
                  >
                    <td className="px-3 py-3.5">
                      <StatusBadge status={e.event_type} />
                    </td>
                    <td className="px-3 py-3.5">
                      <PromptCell
                        text={e.original_content}
                        expanded={expanded}
                        onToggleExpand={onToggleExpand}
                      />
                    </td>
                    <td className="px-3 py-3.5">
                      <PromptCell
                        text={e.masked_content}
                        empty="No content captured"
                        expanded={expanded}
                        onToggleExpand={onToggleExpand}
                      />
                    </td>
                    <td className="px-3 py-3.5">
                      <DetectedCell
                        entities={e.pii_entities}
                        hitCount={e.pii_hit_count}
                        expanded={expanded}
                        onToggleExpand={onToggleExpand}
                      />
                    </td>
                    <td className="px-3 py-3.5">
                      {providerLabel(e.provider) ? (
                        <span className="break-words text-[13px] font-medium text-ink-800">
                          {providerLabel(e.provider)}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      {e.hostname ? (
                        <span className="break-all text-[12px] text-ink-700">
                          {e.hostname}
                        </span>
                      ) : e.agent_id ? (
                        <span className="break-all font-mono text-xs text-ink-500">
                          {e.agent_id}
                        </span>
                      ) : (
                        <span className="text-ink-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      <span className="break-words text-[12px] tabular-nums text-ink-600">
                        {formatDateTime(e.created_at)}
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
