import { useMemo, useState } from "react";
import { Search, Shield } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { usePiiDetections, useUpdatePiiDetection } from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import type { PiiDetectionPolicy } from "@/types/api";

function DetectionCard({
  detection,
  onToggle,
  busy,
}: {
  detection: PiiDetectionPolicy;
  onToggle: (id: string, enabled: boolean) => void;
  busy: boolean;
}) {
  return (
    <article className="card flex flex-col p-5 transition-shadow hover:shadow-elevated">
      <div className="flex items-start justify-between gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-50 text-brand-600">
          <Shield className="h-5 w-5" />
        </div>
        <StatusBadge status={detection.enabled ? "active" : "inactive"} />
      </div>

      <div className="mt-4 flex-1">
        <h3 className="font-semibold text-ink-900">{detection.name}</h3>
        <p className="mt-1 text-xs font-medium uppercase tracking-wide text-ink-400">
          {detection.category}
        </p>
        <p className="mt-1.5 line-clamp-2 text-sm text-ink-500">
          {detection.description}
        </p>
        <p className="mt-2 font-mono text-xs text-ink-400">
          Mask → {detection.mask}
        </p>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-ink-100 pt-3">
        <div className="text-xs text-ink-500">
          <span className="font-medium text-emerald-700">Enforced when on</span>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-700">
          <span className="text-xs text-ink-500">
            {detection.enabled ? "On" : "Off"}
          </span>
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
            checked={detection.enabled}
            disabled={busy}
            onChange={(e) => onToggle(detection.id, e.target.checked)}
            aria-label={`Toggle ${detection.name}`}
          />
        </label>
      </div>
    </article>
  );
}

function sortActiveFirst(rows: PiiDetectionPolicy[]): PiiDetectionPolicy[] {
  return [...rows].sort((a, b) => {
    if (a.enabled === b.enabled) return a.name.localeCompare(b.name);
    return a.enabled ? -1 : 1;
  });
}

export function PoliciesPage() {
  const {
    data: detections,
    isLoading,
    isError,
    error,
    refetch,
  } = usePiiDetections();
  const updateDetection = useUpdatePiiDetection();

  const [toggleError, setToggleError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">(
    "all",
  );

  const all = detections ?? [];

  const activeCount = all.filter((d) => d.enabled).length;
  const inactiveCount = all.length - activeCount;

  const filteredByCategory = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = all;
    if (statusFilter === "active") rows = rows.filter((d) => d.enabled);
    if (statusFilter === "inactive") rows = rows.filter((d) => !d.enabled);
    if (q) {
      rows = rows.filter((d) => {
        const hay = `${d.name} ${d.category} ${d.description} ${d.id} ${d.mask}`.toLowerCase();
        return hay.includes(q);
      });
    }

    const map = new Map<string, PiiDetectionPolicy[]>();
    for (const row of rows) {
      const list = map.get(row.category) ?? [];
      list.push(row);
      map.set(row.category, list);
    }
    return Array.from(map.entries()).map(
      ([category, list]) => [category, sortActiveFirst(list)] as const,
    );
  }, [all, search, statusFilter]);

  const visibleCount = filteredByCategory.reduce(
    (n, [, list]) => n + list.length,
    0,
  );

  async function handleToggle(id: string, enabled: boolean) {
    setToggleError(null);
    setBusyId(id);
    try {
      await updateDetection.mutateAsync({ id, body: { enabled } });
    } catch (err) {
      setToggleError(
        err instanceof ApiError ? err.detail : "Failed to update detection.",
      );
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Policies"
        description="Each PII type is its own policy. Turn detections on/off — agents sync all active enforceable policies and mask matching data before prompts leave the endpoint."
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <div className="card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-400">
            Active
          </p>
          <p className="mt-1 text-2xl font-semibold text-emerald-700">
            {activeCount}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-400">
            Inactive
          </p>
          <p className="mt-1 text-2xl font-semibold text-ink-600">
            {inactiveCount}
          </p>
        </div>
      </div>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input
            type="search"
            className="input pl-9"
            placeholder="Search policies (email, SSN, phone…)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search policies"
          />
        </div>
        <div className="flex gap-2">
          {(
            [
              ["all", "All"],
              ["active", "Active"],
              ["inactive", "Inactive"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={
                statusFilter === value
                  ? "btn-primary"
                  : "btn-ghost ring-1 ring-ink-200"
              }
              onClick={() => setStatusFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {toggleError && (
        <p className="mb-3 text-sm text-rose-600" role="alert">
          {toggleError}
        </p>
      )}

      {isLoading ? (
        <div className="card">
          <Spinner label="Loading detection policies…" />
        </div>
      ) : isError ? (
        <div className="card">
          <ErrorState error={error} onRetry={() => refetch()} />
        </div>
      ) : visibleCount === 0 ? (
        <div className="card">
          <EmptyState
            icon={Shield}
            title="No matching policies"
            description="Try a different search or status filter."
          />
        </div>
      ) : (
        <div className="space-y-8">
          {filteredByCategory.map(([category, rows]) => (
            <div key={category}>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-500">
                {category}
                <span className="ml-2 font-normal normal-case text-ink-400">
                  ({rows.filter((r) => r.enabled).length} active ·{" "}
                  {rows.filter((r) => !r.enabled).length} inactive)
                </span>
              </h3>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {rows.map((d) => (
                  <DetectionCard
                    key={d.id}
                    detection={d}
                    onToggle={handleToggle}
                    busy={busyId === d.id}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
