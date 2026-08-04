import type { ReactNode } from "react";
import {
  Bot,
  Filter,
  HardDrive,
  ListFilter,
  Search,
  ShieldAlert,
  Tag,
  X,
} from "lucide-react";
import { cn, providerLabel, titleCase } from "@/lib/utils";

export type FeedFilterState = {
  search: string;
  eventType: string;
  provider: string;
  device: string;
  entity: string;
  severity?: string;
};

export const EMPTY_FEED_FILTERS: FeedFilterState = {
  search: "",
  eventType: "all",
  provider: "all",
  device: "all",
  entity: "all",
  severity: "all",
};

function uniqueSorted(values: Array<string | null | undefined>): string[] {
  return Array.from(
    new Set(
      values
        .map((v) => (v ?? "").trim())
        .filter((v) => v.length > 0 && v.toLowerCase() !== "unknown"),
    ),
  ).sort((a, b) => a.localeCompare(b));
}

export function collectFeedFilterOptions(
  rows: Array<{
    event_type?: string;
    provider?: string | null;
    hostname?: string | null;
    pii_entities?: string[];
    severity?: string;
  }>,
) {
  return {
    eventTypes: uniqueSorted(rows.map((r) => r.event_type)),
    providers: uniqueSorted(rows.map((r) => r.provider)),
    devices: uniqueSorted(rows.map((r) => r.hostname)),
    entities: uniqueSorted(rows.flatMap((r) => r.pii_entities ?? [])),
    severities: uniqueSorted(rows.map((r) => r.severity?.toLowerCase())),
  };
}

export function applyFeedFilters<
  T extends {
    event_type: string;
    provider: string | null;
    hostname: string | null;
    pii_entities?: string[];
    severity?: string;
    original_content?: string | null;
    masked_content?: string | null;
  },
>(rows: T[], filters: FeedFilterState): T[] {
  const q = filters.search.trim().toLowerCase();
  return rows.filter((row) => {
    if (
      filters.severity &&
      filters.severity !== "all" &&
      (row.severity ?? "").toLowerCase() !== filters.severity.toLowerCase()
    ) {
      return false;
    }
    if (filters.eventType !== "all" && row.event_type !== filters.eventType) {
      return false;
    }
    if (filters.provider !== "all" && (row.provider ?? "") !== filters.provider) {
      return false;
    }
    if (filters.device !== "all" && (row.hostname ?? "") !== filters.device) {
      return false;
    }
    if (
      filters.entity !== "all" &&
      !(row.pii_entities ?? []).includes(filters.entity)
    ) {
      return false;
    }
    if (q) {
      const hay = [
        row.original_content ?? "",
        row.masked_content ?? "",
        row.hostname ?? "",
        row.provider ?? "",
        row.event_type,
        ...(row.pii_entities ?? []),
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

type Chip = { key: keyof FeedFilterState; label: string; value: string };

function activeChips(
  filters: FeedFilterState,
  includeSeverity: boolean,
): Chip[] {
  const chips: Chip[] = [];
  if (includeSeverity && filters.severity && filters.severity !== "all") {
    chips.push({
      key: "severity",
      label: "Severity",
      value: titleCase(filters.severity),
    });
  }
  if (filters.eventType !== "all") {
    chips.push({
      key: "eventType",
      label: "Event",
      value: titleCase(filters.eventType),
    });
  }
  if (filters.provider !== "all") {
    chips.push({
      key: "provider",
      label: "AI Agent",
      value: providerLabel(filters.provider) ?? titleCase(filters.provider),
    });
  }
  if (filters.device !== "all") {
    chips.push({ key: "device", label: "Device", value: filters.device });
  }
  if (filters.entity !== "all") {
    chips.push({ key: "entity", label: "Detected", value: filters.entity });
  }
  if (filters.search.trim()) {
    chips.push({
      key: "search",
      label: "Search",
      value: filters.search.trim(),
    });
  }
  return chips;
}

function FilterField({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Search;
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-500">
        <Icon className="h-3.5 w-3.5 text-ink-400" />
        {label}
      </span>
      {children}
    </label>
  );
}

type FeedFiltersProps = {
  filters: FeedFilterState;
  onChange: (next: FeedFilterState) => void;
  options: {
    eventTypes: string[];
    providers: string[];
    devices: string[];
    entities: string[];
    severities?: string[];
  };
  showSeverity?: boolean;
  severityCounts?: { high: number; medium: number; low: number; total: number };
  resultCount: number;
  totalCount: number;
  searchPlaceholder?: string;
  limitControl?: ReactNode;
};

export function FeedFilters({
  filters,
  onChange,
  options,
  showSeverity = false,
  severityCounts,
  resultCount,
  totalCount,
  searchPlaceholder = "Search prompts, devices, entities…",
  limitControl,
}: FeedFiltersProps) {
  const chips = activeChips(filters, showSeverity);
  const set = (patch: Partial<FeedFilterState>) =>
    onChange({ ...filters, ...patch });

  const clearChip = (key: keyof FeedFilterState) => {
    if (key === "search") set({ search: "" });
    else if (key === "severity") set({ severity: "all" });
    else set({ [key]: "all" } as Partial<FeedFilterState>);
  };

  return (
    <section className="mb-5 animate-fade-in overflow-hidden rounded-2xl border border-ink-200/80 bg-white shadow-elevated">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 bg-gradient-to-r from-ink-50/90 via-white to-brand-50/40 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-white shadow-sm">
            <Filter className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-semibold text-ink-900">Smart filters</p>
            <p className="text-xs text-ink-500">
              Narrow the feed by severity, detection type, agent, or device
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-ink-500">
          <span className="rounded-full bg-white px-2.5 py-1 font-medium text-ink-700 ring-1 ring-ink-200">
            {resultCount === totalCount
              ? `${totalCount} events`
              : `${resultCount} of ${totalCount}`}
          </span>
          {chips.length > 0 && (
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium text-ink-600 ring-1 ring-ink-200 transition-colors hover:bg-ink-50 hover:text-ink-900"
              onClick={() =>
                onChange({
                  ...EMPTY_FEED_FILTERS,
                  severity: showSeverity ? "all" : filters.severity,
                })
              }
            >
              <X className="h-3.5 w-3.5" />
              Reset all
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4 p-4 sm:p-5">
        {showSeverity && (
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-500">
              Severity
            </p>
            <div className="inline-flex flex-wrap rounded-xl bg-ink-100/80 p-1 ring-1 ring-ink-200/70">
              {(
                [
                  {
                    value: "all",
                    label: "All",
                    count: severityCounts?.total,
                    active: "bg-ink-900 text-white shadow-sm",
                  },
                  {
                    value: "high",
                    label: "High",
                    count: severityCounts?.high,
                    active: "bg-rose-600 text-white shadow-sm",
                  },
                  {
                    value: "medium",
                    label: "Medium",
                    count: severityCounts?.medium,
                    active: "bg-amber-500 text-white shadow-sm",
                  },
                  {
                    value: "low",
                    label: "Low",
                    count: severityCounts?.low,
                    active: "bg-brand-600 text-white shadow-sm",
                  },
                ] as const
              ).map((item) => {
                const selected = (filters.severity ?? "all") === item.value;
                return (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => set({ severity: item.value })}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-all",
                      selected
                        ? item.active
                        : "text-ink-600 hover:bg-white/80 hover:text-ink-900",
                    )}
                  >
                    {item.label}
                    {typeof item.count === "number" && (
                      <span
                        className={cn(
                          "rounded-md px-1.5 py-0.5 text-[11px] font-bold tabular-nums",
                          selected ? "bg-white/20" : "bg-white text-ink-500",
                        )}
                      >
                        {item.count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="relative">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input
            type="search"
            className="input border-ink-200 bg-ink-50/40 py-3 pl-10 text-[15px] shadow-none focus:bg-white"
            placeholder={searchPlaceholder}
            value={filters.search}
            onChange={(e) => set({ search: e.target.value })}
            aria-label="Search events"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <FilterField icon={ListFilter} label="Event type">
            <select
              className="input border-ink-200 bg-ink-50/30 py-2.5 shadow-none focus:bg-white"
              value={filters.eventType}
              onChange={(e) => set({ eventType: e.target.value })}
            >
              <option value="all">All event types</option>
              {options.eventTypes.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </select>
          </FilterField>

          <FilterField icon={Bot} label="AI agent">
            <select
              className="input border-ink-200 bg-ink-50/30 py-2.5 shadow-none focus:bg-white"
              value={filters.provider}
              onChange={(e) => set({ provider: e.target.value })}
            >
              <option value="all">All AI agents</option>
              {options.providers.map((p) => (
                <option key={p} value={p}>
                  {providerLabel(p) ?? titleCase(p)}
                </option>
              ))}
            </select>
          </FilterField>

          <FilterField icon={HardDrive} label="Device">
            <select
              className="input border-ink-200 bg-ink-50/30 py-2.5 shadow-none focus:bg-white"
              value={filters.device}
              onChange={(e) => set({ device: e.target.value })}
            >
              <option value="all">All devices</option>
              {options.devices.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </FilterField>

          <FilterField icon={Tag} label="Detected entity">
            <select
              className="input border-ink-200 bg-ink-50/30 py-2.5 shadow-none focus:bg-white"
              value={filters.entity}
              onChange={(e) => set({ entity: e.target.value })}
            >
              <option value="all">All detections</option>
              {options.entities.map((ent) => (
                <option key={ent} value={ent}>
                  {ent}
                </option>
              ))}
            </select>
          </FilterField>
        </div>

        {chips.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-t border-ink-100 pt-4">
            <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-[0.08em] text-ink-400">
              <ShieldAlert className="h-3.5 w-3.5" />
              Active
            </span>
            {chips.map((chip) => (
              <button
                key={`${chip.key}-${chip.value}`}
                type="button"
                onClick={() => clearChip(chip.key)}
                className="group inline-flex max-w-full items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800 ring-1 ring-brand-200 transition-colors hover:bg-brand-100"
                title={`Remove ${chip.label} filter`}
              >
                <span className="text-brand-500">{chip.label}:</span>
                <span className="truncate">{chip.value}</span>
                <X className="h-3 w-3 opacity-60 group-hover:opacity-100" />
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-100 bg-ink-50/50 px-4 py-3 sm:px-5">
        <p className="text-sm text-ink-600">
          Showing{" "}
          <span className="font-semibold tabular-nums text-ink-900">
            {resultCount}
          </span>
          {resultCount !== totalCount && (
            <>
              {" "}
              of{" "}
              <span className="font-semibold tabular-nums text-ink-900">
                {totalCount}
              </span>
            </>
          )}{" "}
          events
        </p>
        {limitControl}
      </div>
    </section>
  );
}
