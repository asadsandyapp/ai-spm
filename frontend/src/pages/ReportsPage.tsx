import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Ban,
  BarChart3,
  Bot,
  Download,
  FileClock,
  Filter,
  HardDrive,
  ListFilter,
  Percent,
  RefreshCw,
  ScanEye,
  Server,
  ShieldAlert,
  ShieldCheck,
  Tag,
  TrendingUp,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { MetricCard } from "@/components/ui/MetricCard";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui/States";
import { useExportAudit, useReportSummary, useThreats } from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { cn, formatDateTime, providerLabel, titleCase } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import type { ReportNamedCount, ReportQuery } from "@/types/api";

const PERIODS = [7, 30, 90, 180] as const;
const CHART_COLORS = [
  "#3466ff",
  "#059669",
  "#d97706",
  "#e11d48",
  "#0f766e",
  "#4338ca",
  "#b45309",
  "#be123c",
];

type ReportFilters = {
  eventType: string;
  provider: string;
  device: string;
  entity: string;
};

const EMPTY_FILTERS: ReportFilters = {
  eventType: "all",
  provider: "all",
  device: "all",
  entity: "all",
};

function scoreAccent(score: number): "emerald" | "amber" | "rose" {
  if (score >= 80) return "emerald";
  if (score >= 60) return "amber";
  return "rose";
}

function formatShortDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function ChartCard({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("card p-5", className)}>
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function BreakdownTable({
  title,
  rows,
  labelHeader,
  empty,
  formatName,
}: {
  title: string;
  rows: ReportNamedCount[];
  labelHeader: string;
  empty: string;
  formatName?: (name: string) => string;
}) {
  const total = rows.reduce((sum, r) => sum + r.count, 0);
  return (
    <section className="card overflow-hidden">
      <div className="border-b border-ink-100 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
      </div>
      {rows.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-ink-400">{empty}</p>
      ) : (
        <div className="overflow-x-hidden">
          <table className="w-full table-fixed text-left text-sm">
            <thead>
              <tr className="border-b border-ink-100 text-[11px] uppercase tracking-[0.08em] text-ink-500">
                <th className="px-5 py-2.5 font-semibold">{labelHeader}</th>
                <th className="w-20 px-3 py-2.5 font-semibold">Count</th>
                <th className="w-24 px-5 py-2.5 font-semibold">Share</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-50">
              {rows.map((row) => {
                const pct = total > 0 ? Math.round((row.count / total) * 100) : 0;
                return (
                  <tr key={row.name}>
                    <td className="truncate px-5 py-2.5 font-medium text-ink-800">
                      {formatName ? formatName(row.name) : row.name}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums text-ink-700">
                      {row.count.toLocaleString()}
                    </td>
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                          <div
                            className="h-full rounded-full bg-brand-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="w-8 text-right text-[11px] tabular-nums text-ink-500">
                          {pct}%
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ReportsPage() {
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30);
  const [filters, setFilters] = useState<ReportFilters>(EMPTY_FILTERS);
  const [exportError, setExportError] = useState<string | null>(null);
  const permissions = useAuthStore((s) => s.permissions());
  const canExport =
    permissions.includes("audit:export") || permissions.includes("audit:*");

  const query: ReportQuery = useMemo(
    () => ({
      days,
      event_type: filters.eventType === "all" ? undefined : filters.eventType,
      provider: filters.provider === "all" ? undefined : filters.provider,
      device: filters.device === "all" ? undefined : filters.device,
      entity: filters.entity === "all" ? undefined : filters.entity,
    }),
    [days, filters],
  );

  const reportQ = useReportSummary(query);
  const threatsQ = useThreats(8);
  const exportM = useExportAudit();
  const report = reportQ.data;

  const options = report?.filter_options ?? {
    event_types: [],
    providers: [],
    devices: [],
    entities: [],
  };

  const dailySeries = useMemo(
    () =>
      (report?.daily_activity ?? []).map((p) => ({
        ...p,
        label: formatShortDate(p.date),
      })),
    [report?.daily_activity],
  );

  const eventPie = useMemo(
    () =>
      (report?.by_event_type ?? []).map((r) => ({
        name: titleCase(r.name),
        value: r.count,
        raw: r.name,
      })),
    [report?.by_event_type],
  );

  const providerBars = useMemo(
    () =>
      (report?.by_provider ?? []).map((r) => ({
        name: providerLabel(r.name) ?? titleCase(r.name),
        count: r.count,
      })),
    [report?.by_provider],
  );

  const entityBars = useMemo(
    () =>
      (report?.by_entity ?? []).slice(0, 10).map((r) => ({
        name: r.name,
        count: r.count,
      })),
    [report?.by_entity],
  );

  const activeFilterCount = [
    filters.eventType !== "all",
    filters.provider !== "all",
    filters.device !== "all",
    filters.entity !== "all",
  ].filter(Boolean).length;

  async function handleExport() {
    setExportError(null);
    try {
      const blob = await exportM.mutateAsync(days);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `aispm_report_${days}d.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.detail : "Export failed.");
    }
  }

  if (reportQ.isError && !report) {
    return (
      <>
        <PageHeader title="Security Reports" />
        <div className="card">
          <ErrorState error={reportQ.error} onRetry={() => reportQ.refetch()} />
        </div>
      </>
    );
  }

  const loading = reportQ.isLoading && !report;
  const score = report?.security_score ?? 0;
  const onlinePct =
    report && report.agents_total > 0
      ? Math.round((report.agents_online / report.agents_total) * 100)
      : 0;

  return (
    <>
      <PageHeader
        title="Security Reports"
        description="Enterprise posture analytics across prompts, threats, PII, agents, and AI providers."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => reportQ.refetch()}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-ink-600 ring-1 ring-ink-200 transition hover:bg-ink-50"
            >
              <RefreshCw
                className={cn("h-3.5 w-3.5", reportQ.isFetching && "animate-spin")}
              />
              Refresh
            </button>
            {canExport && (
              <button
                type="button"
                onClick={handleExport}
                disabled={exportM.isPending}
                className="inline-flex items-center gap-1.5 rounded-lg bg-ink-900 px-3 py-2 text-sm font-semibold text-white transition hover:bg-ink-800 disabled:opacity-60"
              >
                <Download className="h-3.5 w-3.5" />
                {exportM.isPending ? "Exporting…" : "Export CSV"}
              </button>
            )}
          </div>
        }
      />

      {exportError && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm text-rose-700">
          {exportError}
        </div>
      )}

      {/* Period + filters */}
      <section className="card mb-6 p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-ink-400" />
            <h2 className="text-sm font-semibold text-ink-900">Report filters</h2>
            {activeFilterCount > 0 && (
              <span className="rounded-md bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-700 ring-1 ring-brand-200">
                {activeFilterCount} active
              </span>
            )}
          </div>
          <div className="inline-flex rounded-lg bg-ink-50 p-0.5 ring-1 ring-ink-200">
            {PERIODS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setDays(p)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-semibold tabular-nums transition-colors",
                  days === p
                    ? "bg-white text-ink-900 shadow-sm"
                    : "text-ink-500 hover:text-ink-800",
                )}
              >
                {p}d
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className="block min-w-0">
            <span className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-500">
              <ListFilter className="h-3.5 w-3.5 text-ink-400" />
              Event type
            </span>
            <select
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              value={filters.eventType}
              onChange={(e) =>
                setFilters((f) => ({ ...f, eventType: e.target.value }))
              }
            >
              <option value="all">All events</option>
              {options.event_types.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </select>
          </label>

          <label className="block min-w-0">
            <span className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-500">
              <Bot className="h-3.5 w-3.5 text-ink-400" />
              AI agent
            </span>
            <select
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              value={filters.provider}
              onChange={(e) =>
                setFilters((f) => ({ ...f, provider: e.target.value }))
              }
            >
              <option value="all">All agents</option>
              {options.providers.map((p) => (
                <option key={p} value={p}>
                  {providerLabel(p) ?? titleCase(p)}
                </option>
              ))}
            </select>
          </label>

          <label className="block min-w-0">
            <span className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-500">
              <HardDrive className="h-3.5 w-3.5 text-ink-400" />
              Device
            </span>
            <select
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              value={filters.device}
              onChange={(e) =>
                setFilters((f) => ({ ...f, device: e.target.value }))
              }
            >
              <option value="all">All devices</option>
              {options.devices.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>

          <label className="block min-w-0">
            <span className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-500">
              <Tag className="h-3.5 w-3.5 text-ink-400" />
              Detected entity
            </span>
            <select
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              value={filters.entity}
              onChange={(e) =>
                setFilters((f) => ({ ...f, entity: e.target.value }))
              }
            >
              <option value="all">All entities</option>
              {options.entities.map((ent) => (
                <option key={ent} value={ent}>
                  {ent}
                </option>
              ))}
            </select>
          </label>
        </div>

        {activeFilterCount > 0 && (
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              className="inline-flex items-center gap-1 text-xs font-semibold text-ink-500 hover:text-ink-800"
              onClick={() => setFilters(EMPTY_FILTERS)}
            >
              <X className="h-3.5 w-3.5" />
              Clear filters
            </button>
          </div>
        )}

        {report && (
          <p className="mt-3 text-xs text-ink-400">
            Window {formatDateTime(report.period_start)} →{" "}
            {formatDateTime(report.period_end)}
            {reportQ.isFetching && !reportQ.isLoading ? " · Updating…" : null}
          </p>
        )}
      </section>

      {loading ? (
        <div className="flex justify-center py-24">
          <Spinner />
        </div>
      ) : !report ? (
        <div className="card">
          <EmptyState
            icon={BarChart3}
            title="No reportable activity"
            description="No audited prompt or security events match this window and filters."
          />
        </div>
      ) : (
        <>
          {/* KPI strip */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Security Score"
              value={score}
              icon={ShieldCheck}
              accent={scoreAccent(score)}
              hint={`Rolling ${days}-day posture`}
            />
            <MetricCard
              label="Total Events"
              value={report.total_events.toLocaleString()}
              icon={Activity}
              accent="brand"
              hint={`${report.avg_daily_events}/day average`}
            />
            <MetricCard
              label="Prompts Inspected"
              value={report.prompts.toLocaleString()}
              icon={FileClock}
              accent="violet"
              hint={`${report.blocks.toLocaleString()} blocked`}
            />
            <MetricCard
              label="Threats"
              value={report.threats.toLocaleString()}
              icon={ShieldAlert}
              accent={report.threats > 0 ? "rose" : "emerald"}
              hint={`${report.policy_violations} policy violations`}
            />
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="PII Detections"
              value={report.pii_detections.toLocaleString()}
              icon={ScanEye}
              accent="amber"
              hint={`${report.pii_rate_pct}% of prompts`}
            />
            <MetricCard
              label="Block Rate"
              value={`${report.block_rate_pct}%`}
              icon={Percent}
              accent={report.block_rate_pct > 10 ? "rose" : "emerald"}
              hint={`${report.prompt_blocked} hard blocks`}
            />
            <MetricCard
              label="Fleet Online"
              value={`${report.agents_online}/${report.agents_total}`}
              icon={Server}
              accent="brand"
              hint={`${onlinePct}% coverage · ${report.agents_offline} offline`}
              trend={{
                value: `${report.agents_pending} pending`,
                direction: "flat",
              }}
            />
            <MetricCard
              label="Active Policies"
              value={report.policies_active}
              icon={Ban}
              accent="violet"
              hint={`Peak day ${report.peak_day_count} events`}
            />
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Blocks"
              value={report.blocks.toLocaleString()}
              icon={Ban}
              accent="rose"
              hint="Policy + threat + blocked"
            />
            <MetricCard
              label="Policy Violations"
              value={report.policy_violations.toLocaleString()}
              icon={ListFilter}
              accent="amber"
              hint="Governance denials"
            />
            <MetricCard
              label="Agents Revoked"
              value={report.agents_revoked}
              icon={Server}
              accent={report.agents_revoked > 0 ? "rose" : "emerald"}
              hint="Removed from fleet"
            />
            <MetricCard
              label="Peak Day Volume"
              value={report.peak_day_count.toLocaleString()}
              icon={TrendingUp}
              accent="brand"
              hint={
                report.peak_day
                  ? formatShortDate(report.peak_day)
                  : "No peak day"
              }
            />
          </div>

          {report.total_events === 0 ? (
            <div className="card mt-6">
              <EmptyState
                icon={BarChart3}
                title="No events in this window"
                description="KPIs above still reflect fleet posture. Try a wider period or clear filters."
              />
            </div>
          ) : (
            <>
          {/* Charts */}
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <ChartCard
              title="Activity trend"
              subtitle={`Daily volume over ${days} days`}
              className="lg:col-span-2"
            >
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={dailySeries}
                    margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="rptTotal" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3466ff" stopOpacity={0.28} />
                        <stop offset="95%" stopColor="#3466ff" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="rptPii" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#d97706" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#d97706" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="rptBlocks" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#e11d48" stopOpacity={0.22} />
                        <stop offset="95%" stopColor="#e11d48" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#eceef2"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11, fill: "#66748f" }}
                      interval="preserveStartEnd"
                      minTickGap={28}
                    />
                    <YAxis
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11, fill: "#66748f" }}
                      width={36}
                    />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 10,
                        border: "1px solid #e5e7eb",
                        fontSize: 12,
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="total"
                      name="Total"
                      stroke="#3466ff"
                      fill="url(#rptTotal)"
                      strokeWidth={2}
                    />
                    <Area
                      type="monotone"
                      dataKey="pii"
                      name="PII"
                      stroke="#d97706"
                      fill="url(#rptPii)"
                      strokeWidth={1.5}
                    />
                    <Area
                      type="monotone"
                      dataKey="blocks"
                      name="Blocks"
                      stroke="#e11d48"
                      fill="url(#rptBlocks)"
                      strokeWidth={1.5}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="Event mix" subtitle="Share by event type">
              <div className="h-72">
                {eventPie.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-ink-400">
                    No event data
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={eventPie}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={58}
                        outerRadius={90}
                        paddingAngle={2}
                      >
                        {eventPie.map((_, i) => (
                          <Cell
                            key={eventPie[i]?.raw ?? i}
                            fill={CHART_COLORS[i % CHART_COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          borderRadius: 10,
                          border: "1px solid #e5e7eb",
                          fontSize: 12,
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </div>
              <ul className="mt-1 space-y-1.5">
                {eventPie.slice(0, 5).map((item, i) => (
                  <li
                    key={item.raw}
                    className="flex items-center justify-between text-xs text-ink-600"
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{
                          background: CHART_COLORS[i % CHART_COLORS.length],
                        }}
                      />
                      {item.name}
                    </span>
                    <span className="font-semibold tabular-nums text-ink-800">
                      {item.value.toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            </ChartCard>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <ChartCard title="AI agents" subtitle="Events by provider">
              <div className="h-64">
                {providerBars.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-ink-400">
                    No provider attribution in this window
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={providerBars}
                      layout="vertical"
                      margin={{ top: 4, right: 12, left: 8, bottom: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#eceef2"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        allowDecimals={false}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 11, fill: "#66748f" }}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={88}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 11, fill: "#66748f" }}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: 10,
                          border: "1px solid #e5e7eb",
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="count" name="Events" fill="#3466ff" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>

            <ChartCard title="Detected entities" subtitle="Top PII / secret types">
              <div className="h-64">
                {entityBars.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-ink-400">
                    No entity detections in this window
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={entityBars}
                      layout="vertical"
                      margin={{ top: 4, right: 12, left: 8, bottom: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#eceef2"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        allowDecimals={false}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 11, fill: "#66748f" }}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={110}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 10, fill: "#66748f" }}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: 10,
                          border: "1px solid #e5e7eb",
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="count" name="Hits" fill="#d97706" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>
          </div>

          {/* Breakdown tables */}
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <BreakdownTable
              title="By device"
              labelHeader="Hostname"
              rows={report.by_device}
              empty="No device attribution"
            />
            <BreakdownTable
              title="By source"
              labelHeader="Path"
              rows={report.by_source}
              empty="No source metadata"
              formatName={(n) => titleCase(n)}
            />
            <BreakdownTable
              title="By event type"
              labelHeader="Event"
              rows={report.by_event_type}
              empty="No events"
              formatName={(n) => titleCase(n)}
            />
          </div>

          {/* Recent threats sample */}
          <section className="card mt-6 overflow-hidden">
            <div className="flex items-center justify-between border-b border-ink-100 px-5 py-3.5">
              <div>
                <h2 className="text-sm font-semibold text-ink-900">
                  Recent security events
                </h2>
                <p className="text-xs text-ink-500">
                  Latest high-signal items from the threat feed
                </p>
              </div>
              <Link
                to="/threats"
                className="text-xs font-semibold text-brand-700 hover:text-brand-800"
              >
                Open threat feed
              </Link>
            </div>
            {threatsQ.isLoading ? (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            ) : (threatsQ.data ?? []).length === 0 ? (
              <p className="px-5 py-8 text-center text-sm text-ink-400">
                No recent threat events
              </p>
            ) : (
              <table className="w-full table-fixed text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-100 text-[11px] uppercase tracking-[0.08em] text-ink-500">
                    <th className="w-[18%] px-5 py-2.5 font-semibold">Event</th>
                    <th className="px-3 py-2.5 font-semibold">Summary</th>
                    <th className="w-[14%] px-3 py-2.5 font-semibold">Agent</th>
                    <th className="w-[18%] px-5 py-2.5 font-semibold">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-50">
                  {(threatsQ.data ?? []).map((t) => (
                    <tr key={t.id} className="align-top">
                      <td className="px-5 py-3 text-[13px] font-medium text-ink-800">
                        {titleCase(t.event_type)}
                      </td>
                      <td className="px-3 py-3">
                        <p className="line-clamp-2 text-[13px] text-ink-600">
                          {t.masked_content || "—"}
                        </p>
                      </td>
                      <td className="px-3 py-3 text-[12px] text-ink-700">
                        {providerLabel(t.provider) ?? "—"}
                      </td>
                      <td className="px-5 py-3 text-[12px] tabular-nums text-ink-500">
                        {formatDateTime(t.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
            </>
          )}
        </>
      )}
    </>
  );
}
